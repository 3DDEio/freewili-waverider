"""FreeWili Foxhunt runtime."""

from __future__ import annotations

import argparse
from collections import deque
import json
import logging
import queue
import signal
import threading
import time
from pathlib import Path
from typing import Any

from .bridge_recovery import release_initial_shell_route
from .display import DisplayUnavailable, NullDisplay, create_display
from .models import (
    ALLOWED_SPANS_HZ,
    MAX_FREQUENCY_HZ,
    MIN_FREQUENCY_HZ,
    FrequencyEntry,
    FrequencyList,
)
from .morse import DecodedMessage
from .rtl_power import RtlPowerStream
from .rtl_iq import RtlIqStream
from .spectrum import (
    WaterfallScale,
    encode_waterfall_bins,
    reduce_bins,
    smooth_spectrum_bins,
)
from .status import StatusWriter
from .store import (
    DecoderSettings,
    DecoderSettingsStore,
    FrequencyLibraryStore,
    ListStore,
    MessageRecord,
    MessageStore,
    PocketAlertSettings,
    PocketAlertStore,
)


LOG = logging.getLogger("freewili_foxhunt")


class FoxhuntApp:
    DISPLAY_RETRY_SECONDS = 5.0
    INITIAL_SHELL_RECOVERY_GRACE_SECONDS = 20.0
    INITIAL_SHELL_RECOVERY_SECONDS = 90.0
    MORSE_DUPLICATE_SECONDS = 30.0

    def __init__(
        self,
        frequency_list: FrequencyList,
        status_path: Path,
        store: ListStore,
        headless: bool = False,
        once: bool = False,
        display: Any | None = None,
        sdr: Any | None = None,
        frequency_lists: list[FrequencyList] | None = None,
        library_store: FrequencyLibraryStore | None = None,
        saved_frequencies: list[FrequencyEntry] | None = None,
        alert_store: PocketAlertStore | None = None,
        alert_settings: PocketAlertSettings | None = None,
        message_store: MessageStore | None = None,
        message_records: list[MessageRecord] | None = None,
        decoder_store: DecoderSettingsStore | None = None,
        decoder_settings: DecoderSettings | None = None,
    ) -> None:
        self.frequency_list = frequency_list
        self.frequency_lists = frequency_lists or [frequency_list]
        if all(item.id != frequency_list.id for item in self.frequency_lists):
            self.frequency_lists.insert(0, frequency_list)
        self.store = store
        self.library_store = library_store
        self.alert_store = alert_store
        self.message_store = message_store
        self.message_records = message_records if message_records is not None else []
        self.decoder_store = decoder_store
        self.decoder_settings = decoder_settings or DecoderSettings()
        self.alert_settings = alert_settings or PocketAlertSettings()
        self.alert_settings.validate()
        if saved_frequencies is None:
            saved_frequencies = []
            seen: set[int] = set()
            for item in self.frequency_lists:
                for entry in item.frequencies:
                    if entry.frequency_hz in seen:
                        continue
                    saved_frequencies.append(FrequencyEntry.from_dict(entry.to_dict()))
                    seen.add(entry.frequency_hz)
        self.saved_frequencies = saved_frequencies
        saved_hz = {entry.frequency_hz for entry in self.saved_frequencies}
        for entry in frequency_list.frequencies:
            if entry.frequency_hz not in saved_hz:
                self.saved_frequencies.append(FrequencyEntry.from_dict(entry.to_dict()))
                saved_hz.add(entry.frequency_hz)
        self.selected = 0
        self.status = StatusWriter(status_path)
        self.headless = headless
        self.display = display or (NullDisplay() if headless else create_display())
        if sdr is not None:
            self.sdr = sdr
        else:
            try:
                self.sdr = RtlIqStream()
                LOG.info("using low-latency native librtlsdr capture")
            except (AttributeError, OSError) as error:
                LOG.warning("native librtlsdr unavailable, using rtl_power: %s", error)
                self.sdr = RtlPowerStream()
        self.once = once
        set_cw_enabled = getattr(self.sdr, "set_cw_enabled", None)
        if callable(set_cw_enabled):
            set_cw_enabled(self.decoder_settings.cw_enabled)
        self.stop_event = threading.Event()
        self.pending_delta = 0
        self.editor_mode = False
        self.lists_mode = False
        self.list_cursor = self.active_list_index
        self.library_page_start = 0
        self.library_cursor = 0
        self.editor_cursor = 0
        self.dirty = False
        self.capture_paused = False
        self.last_rssi_dbfs: float | None = None
        self.last_peak_offset_hz: float | None = None
        self._display_retry_at = 0.0
        self._started_at = time.monotonic()
        self._display_ever_connected = False
        self._display_shell_recovery_done = False
        self._waterfall_timestamps: deque[float] = deque(maxlen=64)
        self._display_push_ms = 0.0
        self.last_morse_message: str | None = None
        self.last_morse_confidence: float | None = None
        self.last_morse_candidate: str | None = None
        self.last_morse_candidate_confidence: float | None = None
        self._last_morse_message_at = 0.0
        self.waterfall_scale = WaterfallScale(
            frequency_list.floor_dbfs,
            frequency_list.ceiling_dbfs,
        )
        self.editor_actions = (
            "ADD +25K",
            "FREQ -25K",
            "FREQ +25K",
            "MOVE UP",
            "MOVE DOWN",
            "DELETE",
            "SPAN",
            "SAVE",
        )

    @property
    def entry(self):
        return self.frequency_list.frequencies[self.selected]

    @property
    def active_list_index(self) -> int:
        for index, item in enumerate(self.frequency_lists):
            if item.id == self.frequency_list.id:
                return index
        return 0

    def select_delta(self, delta: int) -> None:
        self.pending_delta += delta

    def stop(self) -> None:
        self.stop_event.set()

    def _drain_decoded_messages(self) -> None:
        messages = getattr(self.sdr, "messages", None)
        if messages is None:
            return
        while True:
            try:
                item: DecodedMessage = messages.get_nowait()
            except queue.Empty:
                return
            now = time.monotonic()
            observed_unix = time.time()
            if self.message_store is not None:
                record = self.message_store.observe(
                    self.message_records,
                    text=item.text,
                    frequency_hz=self.entry.frequency_hz,
                    confidence=item.confidence,
                    observed_unix=observed_unix,
                )
            else:
                record = MessageRecord(
                    text=item.text,
                    frequency_hz=self.entry.frequency_hz,
                    first_seen_unix=observed_unix,
                    last_seen_unix=observed_unix,
                    confidence=item.confidence,
                    agreement=1.0,
                    verified=True,
                )
            LOG.info(
                "decoded Morse candidate confidence=%.2f agreement=%.2f "
                "evidence=%d verified=%s text=%r",
                record.confidence,
                record.agreement,
                record.evidence_count,
                record.verified,
                record.text,
            )
            self.last_morse_candidate = record.text
            self.last_morse_candidate_confidence = min(
                record.confidence,
                record.agreement if record.agreement > 0.0 else record.confidence,
            )
            # Raw candidates remain in the durable evidence set but do not
            # become a user-facing callsign/message until independent repeats
            # agree. A wrong valid Morse pattern is otherwise dangerously easy
            # to mislabel as a 100%-certain callsign.
            if not record.verified:
                continue
            suppress_popup = (
                record.text == self.last_morse_message
                and now - self._last_morse_message_at
                < self.MORSE_DUPLICATE_SECONDS
            )
            self.last_morse_message = record.text
            self.last_morse_confidence = record.display_confidence
            self._last_morse_message_at = now
            if not suppress_popup:
                self._queue_message_record(record, replay=False)

    def _queue_message_record(
        self,
        record: MessageRecord,
        *,
        replay: bool,
        display: Any | None = None,
    ) -> None:
        show_message = getattr(display or self.display, "show_message", None)
        if not callable(show_message):
            return
        try:
            show_message(
                record.text,
                record.display_confidence,
                frequency_hz=record.frequency_hz,
                repeat_count=record.repeat_count,
                observed_unix=record.last_seen_unix,
                replay=replay,
            )
        except TypeError:
            # Third-party/legacy display adapters can continue showing the
            # transient text even though they cannot render durable metadata.
            show_message(record.text, record.display_confidence)

    def _replay_message_history(self, display: Any | None = None) -> None:
        # The native viewer is deliberately bounded to sixteen records. Send
        # oldest-to-newest so its final cursor lands on the latest detection.
        verified = [record for record in self.message_records if record.verified]
        for record in verified[-16:]:
            self._queue_message_record(record, replay=True, display=display)

    def _connect_display(self) -> None:
        try:
            self.display.connect()
            set_alert = getattr(self.display, "set_pocket_alert", None)
            if callable(set_alert):
                set_alert(
                    self.alert_settings.enabled,
                    self.alert_settings.threshold_dbfs,
                )
            set_cw_decoder = getattr(self.display, "set_cw_decoder", None)
            if callable(set_cw_decoder):
                set_cw_decoder(self.decoder_settings.cw_enabled)
            try:
                self.display.show_splash(3.0)
            except DisplayUnavailable as error:
                # The live receiver remains usable if a user has not installed
                # the optional Main-SD splash asset yet.
                LOG.warning("WaveRider splash unavailable: %s", error)
            self.display.build(self.frequency_list, self.selected)
            self._replay_message_history()
            self._display_ever_connected = True
        except DisplayUnavailable as error:
            self._drop_display(error)

    def _recover_initial_shell_route(self, now: float) -> bool:
        """Release only a boot-race shell, never a later intentional terminal."""

        if (
            self._display_ever_connected
            or self._display_shell_recovery_done
            or now - self._started_at < self.INITIAL_SHELL_RECOVERY_GRACE_SECONDS
            or now - self._started_at > self.INITIAL_SHELL_RECOVERY_SECONDS
        ):
            return False
        result = release_initial_shell_route()
        if result.released:
            self._display_shell_recovery_done = True
            LOG.warning("boot display recovery: %s", result.message)
            return True
        LOG.info("boot display recovery pending: %s", result.message)
        return False

    def _drop_display(self, error: Exception) -> None:
        LOG.warning("display unavailable: %s", error)
        self.display.close()
        self.display = NullDisplay()
        now = time.monotonic()
        recovered = self._recover_initial_shell_route(now)
        self._display_retry_at = now + (1.0 if recovered else self.DISPLAY_RETRY_SECONDS)

    def _retry_display_if_needed(self) -> None:
        if self.headless or not isinstance(self.display, NullDisplay):
            return
        now = time.monotonic()
        if now < self._display_retry_at:
            return
        candidate = create_display()
        try:
            candidate.connect()
            set_alert = getattr(candidate, "set_pocket_alert", None)
            if callable(set_alert):
                set_alert(
                    self.alert_settings.enabled,
                    self.alert_settings.threshold_dbfs,
                )
            set_cw_decoder = getattr(candidate, "set_cw_decoder", None)
            if callable(set_cw_decoder):
                set_cw_decoder(self.decoder_settings.cw_enabled)
            candidate.build(self.frequency_list, self.selected)
            self._replay_message_history(candidate)
        except DisplayUnavailable as error:
            LOG.warning("display reconnect failed: %s", error)
            candidate.close()
            self._display_retry_at = now + self.DISPLAY_RETRY_SECONDS
            return
        self.display = candidate
        self._display_ever_connected = True
        LOG.info("display reconnected")

    def _apply_pending_selection(self) -> bool:
        action = self.display.poll_action()
        if action:
            self._handle_action(action)
        if not self.pending_delta:
            return False
        self.selected = (self.selected + self.pending_delta) % len(self.frequency_list.frequencies)
        self.pending_delta = 0
        if not self.capture_paused:
            self.sdr.start(self.entry)
        self.waterfall_scale.reset()
        self.display.update_selection(self.selected)
        return True

    def _editor_footer(self) -> str:
        action = self.editor_actions[self.editor_cursor]
        dirty = " *" if self.dirty else ""
        return f"EDIT {self.editor_cursor + 1}/{len(self.editor_actions)} {action}{dirty}"

    def _show_live(self) -> None:
        self.lists_mode = False
        self.editor_mode = False
        self.display.build(self.frequency_list, self.selected)
        self.display.set_button_labels(
            ("LISTS", "MSGS", "NEXT", "PREV", "REFRESH")
        )
        if self.capture_paused:
            self.display.set_status("PAUSED")

    def _show_lists(self) -> None:
        self.lists_mode = True
        self.editor_mode = False
        active_frequency = self.entry.frequency_hz
        self.library_cursor = next(
            (
                index
                for index, entry in enumerate(self.saved_frequencies)
                if entry.frequency_hz == active_frequency
            ),
            0,
        )
        self.library_page_start = (self.library_cursor // 16) * 16
        self._publish_library()

    def _publish_library(self) -> None:
        if not self.saved_frequencies:
            return
        maximum_start = ((len(self.saved_frequencies) - 1) // 16) * 16
        self.library_page_start = min(max(0, self.library_page_start), maximum_start)
        window = self.saved_frequencies[self.library_page_start : self.library_page_start + 16]
        selected = min(
            max(0, self.library_cursor - self.library_page_start),
            len(window) - 1,
        )
        live_frequencies = {entry.frequency_hz for entry in self.frequency_list.frequencies}
        build_library = getattr(self.display, "build_library", None)
        if callable(build_library):
            build_library(
                window,
                live_frequencies,
                len(self.frequency_list.frequencies),
                len(self.saved_frequencies),
                self.library_page_start,
                selected,
            )
        else:
            self.display.build_lists(
                self.frequency_lists,
                self.active_list_index,
                self.list_cursor,
            )

    def _save_library(self) -> None:
        if self.library_store is not None:
            self.library_store.save(self.saved_frequencies)

    def _library_index(self, local_index: int) -> int | None:
        index = self.library_page_start + local_index
        if 0 <= index < len(self.saved_frequencies):
            return index
        return None

    def _activate_list(self, index: int) -> None:
        self.frequency_list = self.frequency_lists[index]
        self.selected = 0
        self.waterfall_scale = WaterfallScale(
            self.frequency_list.floor_dbfs,
            self.frequency_list.ceiling_dbfs,
        )
        if not self.capture_paused:
            self.sdr.start(self.entry)
        self._show_live()

    def _mark_current_signal(self) -> None:
        if self.last_rssi_dbfs is None:
            self.display.set_footer("WAITING FOR FIRST RF SAMPLE")
            return
        path = self.store.directory.parent / "marks.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_unix": time.time(),
            "list_id": self.frequency_list.id,
            "list_name": self.frequency_list.name,
            "entry_id": self.entry.id,
            "frequency_hz": self.entry.frequency_hz,
            "span_hz": self.entry.span_hz,
            "rssi_dbfs": self.last_rssi_dbfs,
            "peak_offset_hz": self.last_peak_offset_hz,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self.display.set_footer(f"MARK SAVED  {self.last_rssi_dbfs:.1f} dBFS")

    def _toggle_capture(self) -> None:
        if self.capture_paused:
            self.capture_paused = False
            self.sdr.start(self.entry)
            self.waterfall_scale.reset()
            self.display.set_status("CONNECT")
            self.display.set_button_labels(("LISTS", "BAND", "NEXT", "MARK", "STOP"))
            return
        self.sdr.stop()
        self.capture_paused = True
        self.display.set_status("PAUSED")
        self.display.set_button_labels(("LISTS", "BAND", "NEXT", "MARK", "START"))

    def _handle_lists_action(self, action: str) -> None:
        if action in {"gray", "library_back"}:
            self._show_live()
        elif action == "library_prev_page":
            self.library_page_start = max(0, self.library_page_start - 16)
            self.library_cursor = self.library_page_start
            self._publish_library()
        elif action == "library_next_page":
            if self.library_page_start + 16 < len(self.saved_frequencies):
                self.library_page_start += 16
                self.library_cursor = self.library_page_start
            self._publish_library()
        elif action.startswith("library_toggle:"):
            self._toggle_library_frequency(int(action.split(":", 1)[1]))
        elif action.startswith("library_delete:"):
            self._delete_library_frequency(int(action.split(":", 1)[1]))
        elif action.startswith("library_tune:"):
            self._tune_library_frequency(int(action.split(":", 1)[1]))

    def _toggle_library_frequency(self, local_index: int) -> None:
        index = self._library_index(local_index)
        if index is None:
            return
        self.library_cursor = index
        saved = self.saved_frequencies[index]
        live_index = next(
            (
                position
                for position, entry in enumerate(self.frequency_list.frequencies)
                if entry.frequency_hz == saved.frequency_hz
            ),
            None,
        )
        if live_index is not None:
            if len(self.frequency_list.frequencies) <= 1:
                self.display.set_footer("KEEP AT LEAST ONE LIVE FREQUENCY")
                self._publish_library()
                return
            del self.frequency_list.frequencies[live_index]
            if live_index < self.selected:
                self.selected -= 1
            elif live_index == self.selected:
                self.selected = min(self.selected, len(self.frequency_list.frequencies) - 1)
                if not self.capture_paused:
                    self.sdr.start(self.entry)
                self.waterfall_scale.reset()
        else:
            if len(self.frequency_list.frequencies) >= 16:
                self.display.set_footer("LIVE LIST FULL (16)")
                self._publish_library()
                return
            self.frequency_list.frequencies.append(FrequencyEntry.from_dict(saved.to_dict()))
        self.store.save(self.frequency_list)
        self.display.set_footer("LIVE LIST UPDATED")
        self._publish_library()

    def _delete_library_frequency(self, local_index: int) -> None:
        index = self._library_index(local_index)
        if index is None:
            return
        saved = self.saved_frequencies[index]
        live_index = next(
            (
                position
                for position, entry in enumerate(self.frequency_list.frequencies)
                if entry.frequency_hz == saved.frequency_hz
            ),
            None,
        )
        if live_index is not None and len(self.frequency_list.frequencies) <= 1:
            self.display.set_footer("KEEP AT LEAST ONE LIVE FREQUENCY")
            self._publish_library()
            return
        if live_index is not None:
            del self.frequency_list.frequencies[live_index]
            self.selected = min(self.selected, len(self.frequency_list.frequencies) - 1)
            if not self.capture_paused:
                self.sdr.start(self.entry)
            self.waterfall_scale.reset()
            self.store.save(self.frequency_list)
        del self.saved_frequencies[index]
        self.library_cursor = min(index, len(self.saved_frequencies) - 1)
        self.library_page_start = (max(0, self.library_cursor) // 16) * 16
        self._save_library()
        self.display.set_footer("DELETED")
        self._publish_library()

    def _tune_library_frequency(self, local_index: int) -> None:
        index = self._library_index(local_index)
        if index is None:
            return
        saved = self.saved_frequencies[index]
        live_index = next(
            (
                position
                for position, entry in enumerate(self.frequency_list.frequencies)
                if entry.frequency_hz == saved.frequency_hz
            ),
            None,
        )
        if live_index is None:
            if len(self.frequency_list.frequencies) >= 16:
                self.display.set_footer("LIVE LIST FULL (16)")
                self._publish_library()
                return
            self.frequency_list.frequencies.append(FrequencyEntry.from_dict(saved.to_dict()))
            self.store.save(self.frequency_list)
            live_index = len(self.frequency_list.frequencies) - 1
        self.selected = live_index
        if not self.capture_paused:
            self.sdr.start(self.entry)
        self.waterfall_scale.reset()
        self._show_live()

    def _handle_action(self, action: str) -> None:
        LOG.info("button action: %s", action)
        if action == "messages_clear":
            if self.message_store is not None:
                self.message_store.clear(self.message_records)
            else:
                self.message_records.clear()
            self.last_morse_message = None
            self.last_morse_confidence = None
            self.last_morse_candidate = None
            self.last_morse_candidate_confidence = None
            self._last_morse_message_at = 0.0
            LOG.info("cleared persisted CW message and candidate history")
            return
        if action.startswith("decoder_enabled:"):
            self.decoder_settings.cw_enabled = action.endswith(":1")
            if self.decoder_store is not None:
                self.decoder_store.save(self.decoder_settings)
            set_cw_enabled = getattr(self.sdr, "set_cw_enabled", None)
            if callable(set_cw_enabled):
                set_cw_enabled(self.decoder_settings.cw_enabled)
            set_cw_decoder = getattr(self.display, "set_cw_decoder", None)
            if callable(set_cw_decoder):
                set_cw_decoder(self.decoder_settings.cw_enabled)
            LOG.info(
                "CW decoder %s",
                "enabled" if self.decoder_settings.cw_enabled else "disabled",
            )
            return
        if action.startswith("alert_enabled:"):
            self.alert_settings.enabled = action.endswith(":1")
            self._save_alert_settings()
            return
        if action.startswith("alert_threshold:"):
            try:
                threshold = int(action.split(":", 1)[1])
            except ValueError:
                return
            if -70 <= threshold <= -10:
                self.alert_settings.threshold_dbfs = threshold
                self._save_alert_settings()
            return
        if action.startswith("add:"):
            try:
                frequency_hz = int(action.split(":", 1)[1])
            except ValueError:
                return
            if self.lists_mode:
                self._add_saved_frequency(frequency_hz)
            else:
                self._add_frequency(frequency_hz)
            return
        if action.startswith("select:"):
            try:
                selected = int(action.split(":", 1)[1])
            except ValueError:
                return
            if 0 <= selected < len(self.frequency_list.frequencies):
                self.pending_delta += selected - self.selected
            return
        if action == "lists":
            self._show_lists()
            return
        if self.lists_mode:
            self._handle_lists_action(action)
            return
        if not self.editor_mode:
            if action == "gray":
                self._show_lists()
            elif action == "yellow":
                self.display.set_footer("MESSAGE HISTORY IS IN THE NATIVE APP")
            elif action == "green":
                self.pending_delta += 1
            elif action == "blue":
                self.pending_delta -= 1
            elif action == "red":
                self._refresh_receiver()
            return

        if action == "yellow":
            self.editor_cursor = (self.editor_cursor - 1) % len(self.editor_actions)
        elif action == "green":
            self.editor_cursor = (self.editor_cursor + 1) % len(self.editor_actions)
        elif action == "red":
            self._show_live()
            return
        elif action in ("blue", "gray"):
            self._execute_editor_action(self.editor_actions[self.editor_cursor])
        self.display.set_footer(self._editor_footer())

    def _save_alert_settings(self) -> None:
        self.alert_settings.validate()
        if self.alert_store is not None:
            self.alert_store.save(self.alert_settings)
        set_alert = getattr(self.display, "set_pocket_alert", None)
        if callable(set_alert):
            set_alert(
                self.alert_settings.enabled,
                self.alert_settings.threshold_dbfs,
            )
        # The native page originated this command and has already applied the
        # new value locally. Do not republish all 16 frequencies merely to
        # echo the setting back: that long mailbox transaction competes with
        # live rows and can leave the command/status UI stale. The persisted
        # value is included in the next ordinary build or service reconnect.

    def _add_saved_frequency(self, frequency_hz: int) -> None:
        if len(self.saved_frequencies) >= 100:
            self.display.set_footer("SAVED LIBRARY FULL (100)")
            self._publish_library()
            return
        if not MIN_FREQUENCY_HZ <= frequency_hz <= MAX_FREQUENCY_HZ:
            self.display.set_footer("FREQUENCY OUT OF SDR RANGE")
            self._publish_library()
            return
        if any(entry.frequency_hz == frequency_hz for entry in self.saved_frequencies):
            self.display.set_footer(f"{frequency_hz / 1_000_000:.3f} ALREADY SAVED")
            self._publish_library()
            return
        entry = FrequencyEntry(
            frequency_hz=frequency_hz,
            label=f"Saved {frequency_hz / 1_000_000:.3f}",
            span_hz=self.entry.span_hz,
            gain_profile=self.entry.gain_profile,
        )
        self.saved_frequencies.append(entry)
        self._save_library()
        self.library_cursor = len(self.saved_frequencies) - 1
        self.library_page_start = (self.library_cursor // 16) * 16
        self.display.set_footer("SAVED")
        self._publish_library()

    def _add_frequency(self, frequency_hz: int | None = None) -> None:
        maximum = int(getattr(self.display, "MAX_LIST_ENTRIES", 100))
        if len(self.frequency_list.frequencies) >= maximum:
            self.display.set_footer(f"LIST FULL ({maximum})")
            return
        if frequency_hz is None:
            self.display.set_footer("ENTER AN EXACT FREQUENCY ON THE DEVICE")
            return
        if not MIN_FREQUENCY_HZ <= frequency_hz <= MAX_FREQUENCY_HZ:
            self.display.set_footer("FREQUENCY OUT OF SDR RANGE")
            return
        if any(item.frequency_hz == frequency_hz for item in self.frequency_list.frequencies):
            self.display.set_footer(f"{frequency_hz / 1_000_000:.3f} ALREADY IN LIST")
            return
        new_entry = FrequencyEntry(
            frequency_hz=frequency_hz,
            label=f"New {frequency_hz / 1_000_000:.3f}",
            span_hz=self.entry.span_hz,
            gain_profile=self.entry.gain_profile,
        )
        self.selected += 1
        self.frequency_list.frequencies.insert(self.selected, new_entry)
        self.display.build(self.frequency_list, self.selected)
        if not self.capture_paused:
            self.sdr.start(self.entry)
        self.waterfall_scale.reset()
        self.store.save(self.frequency_list)
        self.dirty = False
        self.display.set_footer(f"ADDED {self.entry.frequency_hz / 1_000_000:.3f}")

    def _remove_frequency(self) -> None:
        if len(self.frequency_list.frequencies) <= 1:
            self.display.set_footer("KEEP AT LEAST ONE FREQUENCY")
            return
        removed = self.entry.frequency_hz
        self._execute_editor_action("DELETE")
        self.store.save(self.frequency_list)
        self.dirty = False
        self.display.set_footer(f"REMOVED {removed / 1_000_000:.3f}")

    def _refresh_receiver(self) -> None:
        self.display.set_status("REFRESH")
        self.last_rssi_dbfs = None
        self.last_peak_offset_hz = None
        self._waterfall_timestamps.clear()
        self.waterfall_scale.reset()
        self.sdr.start(self.entry)
        self.display.build(self.frequency_list, self.selected)

    def _execute_editor_action(self, action: str) -> None:
        retune = False
        rebuild = False
        if action == "ADD +25K":
            frequency_hz = self.entry.frequency_hz + 25_000
            if frequency_hz > MAX_FREQUENCY_HZ:
                frequency_hz = self.entry.frequency_hz - 25_000
            new_entry = FrequencyEntry(
                frequency_hz=frequency_hz,
                label=f"New {frequency_hz / 1_000_000:.3f}",
                span_hz=self.entry.span_hz,
                gain_profile=self.entry.gain_profile,
            )
            self.selected += 1
            self.frequency_list.frequencies.insert(self.selected, new_entry)
            retune = rebuild = True
        elif action in ("FREQ -25K", "FREQ +25K"):
            delta = -25_000 if action == "FREQ -25K" else 25_000
            self.entry.frequency_hz = min(
                MAX_FREQUENCY_HZ,
                max(MIN_FREQUENCY_HZ, self.entry.frequency_hz + delta),
            )
            self.entry.validate()
            retune = rebuild = True
        elif action in ("MOVE UP", "MOVE DOWN"):
            target = self.selected + (-1 if action == "MOVE UP" else 1)
            if target in range(len(self.frequency_list.frequencies)):
                entries = self.frequency_list.frequencies
                entries[self.selected], entries[target] = entries[target], entries[self.selected]
                self.selected = target
                rebuild = True
        elif action == "DELETE":
            if len(self.frequency_list.frequencies) > 1:
                del self.frequency_list.frequencies[self.selected]
                self.selected = min(self.selected, len(self.frequency_list.frequencies) - 1)
                retune = rebuild = True
        elif action == "SPAN":
            current = ALLOWED_SPANS_HZ.index(self.entry.span_hz)
            self.entry.span_hz = ALLOWED_SPANS_HZ[(current + 1) % len(ALLOWED_SPANS_HZ)]
            retune = True
        elif action == "SAVE":
            self.store.save(self.frequency_list)
            self.dirty = False
            return

        if rebuild:
            self.display.build(self.frequency_list, self.selected)
        if retune:
            if not self.capture_paused:
                self.sdr.start(self.entry)
            self.waterfall_scale.reset()
        if rebuild or retune:
            self.dirty = True

    def run(self) -> int:
        self.status.write(state="starting", frequency_hz=self.entry.frequency_hz)
        try:
            # RTL-SDR capture is independent of the Main/display handshake.
            # Start it first so USB initialization and the first FFT row can
            # proceed while WaveRider connects to the app-signal mailbox.
            self.sdr.start(self.entry)
            self._connect_display()
            while not self.stop_event.is_set():
                self._retry_display_if_needed()
                if self._apply_pending_selection():
                    continue
                try:
                    item = self.sdr.rows.get(timeout=0.2)
                except queue.Empty:
                    continue
                if isinstance(item, Exception):
                    raise item
                waterfall_bins = int(getattr(self.display, "WATERFALL_BINS", 12))
                bins = smooth_spectrum_bins(
                    reduce_bins(item.powers_dbfs, waterfall_bins)
                )
                floor_dbfs, ceiling_dbfs = self.waterfall_scale.update(bins)
                quantized = encode_waterfall_bins(
                    bins,
                    floor_dbfs,
                    ceiling_dbfs,
                )
                peak_offset = item.peak_frequency_hz - self.entry.frequency_hz
                self.last_rssi_dbfs = item.peak_dbfs
                self.last_peak_offset_hz = peak_offset
                try:
                    if not self.lists_mode:
                        self.display.update_receiver(self.entry, item.peak_dbfs, peak_offset)
                        display_started = time.monotonic()
                        self.display.push_waterfall(quantized)
                        self._drain_decoded_messages()
                        display_finished = time.monotonic()
                        self._display_push_ms = (display_finished - display_started) * 1000.0
                        self._waterfall_timestamps.append(display_finished)
                except DisplayUnavailable as error:
                    self._drop_display(error)
                row_rate_hz = 0.0
                if len(self._waterfall_timestamps) > 1:
                    elapsed = self._waterfall_timestamps[-1] - self._waterfall_timestamps[0]
                    if elapsed > 0:
                        row_rate_hz = (len(self._waterfall_timestamps) - 1) / elapsed
                snapshot = self.display.snapshot
                morse_timing = getattr(
                    getattr(self.sdr, "morse_decoder", None), "timing", None
                )
                self.status.write(
                    state="live",
                    sdr_connected=True,
                    display_connected=snapshot.connected,
                    display_message=snapshot.message,
                    list_name=self.frequency_list.name,
                    selected=self.selected,
                    frequency_hz=self.entry.frequency_hz,
                    span_hz=self.entry.span_hz,
                    rssi_dbfs=item.peak_dbfs,
                    peak_offset_hz=peak_offset,
                    waterfall_bins=len(quantized),
                    waterfall_raw_min_dbfs=round(min(bins), 2),
                    waterfall_raw_max_dbfs=round(max(bins), 2),
                    waterfall_floor_dbfs=round(floor_dbfs, 2),
                    waterfall_ceiling_dbfs=round(ceiling_dbfs, 2),
                    waterfall_encoded_min=min(quantized),
                    waterfall_encoded_max=max(quantized),
                    waterfall_encoded_unique=len(set(quantized)),
                    waterfall_row_rate_hz=round(row_rate_hz, 2),
                    display_push_ms=round(self._display_push_ms, 1),
                    sdr_queue_depth=self.sdr.rows.qsize(),
                    sdr_realtime_ratio=round(
                        float(getattr(self.sdr, "realtime_ratio", 0.0)), 3
                    ),
                    sdr_processing_ms=round(
                        float(getattr(self.sdr, "last_processing_ms", 0.0)), 1
                    ),
                    sdr_carrier_active=bool(
                        getattr(self.sdr, "carrier_active", False)
                    ),
                    sdr_carrier_margin_db=round(
                        float(getattr(self.sdr, "carrier_margin_db", 0.0)), 1
                    ),
                    morse_message=self.last_morse_message,
                    morse_confidence=self.last_morse_confidence,
                    morse_history_count=sum(
                        1 for record in self.message_records if record.verified
                    ),
                    morse_candidate_count=sum(
                        1 for record in self.message_records if not record.verified
                    ),
                    morse_candidate=self.last_morse_candidate,
                    morse_candidate_confidence=self.last_morse_candidate_confidence,
                    morse_attempt=getattr(morse_timing, "last_attempt_text", None),
                    morse_attempt_confidence=getattr(
                        morse_timing, "last_attempt_confidence", None
                    ),
                    morse_attempt_timing_confidence=getattr(
                        morse_timing, "last_attempt_timing_confidence", None
                    ),
                    morse_attempt_signal_confidence=getattr(
                        morse_timing, "last_attempt_signal_confidence", None
                    ),
                    morse_attempt_known_confidence=getattr(
                        morse_timing, "last_attempt_known_confidence", None
                    ),
                    morse_attempt_rejection=getattr(
                        morse_timing, "last_attempt_rejection", None
                    ),
                    morse_attempt_count=getattr(morse_timing, "attempt_count", 0),
                    morse_attempt_raw_duration_ms=getattr(
                        morse_timing, "last_attempt_raw_duration_ms", None
                    ),
                    morse_attempt_duration_ms=getattr(
                        morse_timing, "last_attempt_duration_ms", None
                    ),
                    morse_attempt_raw_mark_count=getattr(
                        morse_timing, "last_attempt_raw_mark_count", 0
                    ),
                    morse_attempt_raw_gap_count=getattr(
                        morse_timing, "last_attempt_raw_gap_count", 0
                    ),
                    morse_attempt_raw_mark_range_ms=getattr(
                        morse_timing, "last_attempt_raw_mark_range_ms", None
                    ),
                    morse_attempt_raw_gap_range_ms=getattr(
                        morse_timing, "last_attempt_raw_gap_range_ms", None
                    ),
                    morse_attempt_mark_count=getattr(
                        morse_timing, "last_attempt_mark_count", 0
                    ),
                    morse_attempt_gap_count=getattr(
                        morse_timing, "last_attempt_gap_count", 0
                    ),
                    morse_attempt_mark_range_ms=getattr(
                        morse_timing, "last_attempt_mark_range_ms", None
                    ),
                    morse_attempt_gap_range_ms=getattr(
                        morse_timing, "last_attempt_gap_range_ms", None
                    ),
                    morse_attempt_unit_ms=getattr(
                        morse_timing, "last_attempt_unit_ms", None
                    ),
                    morse_unit_ms=round(
                        float(
                            getattr(
                                getattr(
                                    getattr(self.sdr, "morse_decoder", None),
                                    "timing",
                                    None,
                                ),
                                "unit_seconds",
                                0.0,
                            )
                        )
                        * 1000.0,
                        1,
                    ),
                    morse_tone_hz=round(
                        float(
                            getattr(
                                getattr(self.sdr, "morse_decoder", None),
                                "detected_tone_hz",
                                0.0,
                            )
                        ),
                        1,
                    ),
                    cw_decoder_enabled=self.decoder_settings.cw_enabled,
                    audio_monitor_available=False,
                )
                if self.once:
                    return 0
        except Exception as error:
            LOG.exception("foxhunt runtime failed")
            self.status.write(
                state="error",
                sdr_connected=False,
                display_connected=self.display.snapshot.connected,
                error=str(error),
            )
            return 1
        finally:
            self.sdr.close()
            self.display.close()
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FreeWili 2 RTL-SDR foxhunt instrument")
    parser.add_argument("--state-dir", default="/var/lib/freewili-foxhunt")
    parser.add_argument("--list", dest="list_path")
    parser.add_argument("--status", default="/run/freewili-foxhunt/status.json")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    store = ListStore(Path(args.state_dir) / "lists")
    lists = store.load_all()
    if args.list_path:
        selected_list = store.load(args.list_path)
    elif lists:
        selected_list = lists[0]
    else:
        raise SystemExit(f"no frequency lists found under {store.directory}")

    library_store = FrequencyLibraryStore(Path(args.state_dir) / "frequency-library.json")
    saved_frequencies = library_store.load_or_seed(lists)
    alert_store = PocketAlertStore(Path(args.state_dir) / "pocket-alert.json")
    alert_settings = alert_store.load_or_default()
    message_store = MessageStore(Path(args.state_dir) / "messages.json")
    message_records = message_store.load_or_empty()
    decoder_store = DecoderSettingsStore(Path(args.state_dir) / "decoder-settings.json")
    decoder_settings = decoder_store.load_or_default()

    app = FoxhuntApp(
        selected_list,
        Path(args.status),
        store,
        args.headless,
        args.once,
        frequency_lists=lists,
        library_store=library_store,
        saved_frequencies=saved_frequencies,
        alert_store=alert_store,
        alert_settings=alert_settings,
        message_store=message_store,
        message_records=message_records,
        decoder_store=decoder_store,
        decoder_settings=decoder_settings,
    )
    signal.signal(signal.SIGTERM, lambda *_: app.stop())
    signal.signal(signal.SIGINT, lambda *_: app.stop())
    signal.signal(signal.SIGUSR1, lambda *_: app.select_delta(1))
    signal.signal(signal.SIGUSR2, lambda *_: app.select_delta(-1))
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
