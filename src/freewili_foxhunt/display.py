"""Best-effort adapter for the stock FreeWili dynamic-panel API."""

from __future__ import annotations

import logging
import os
import queue
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FrequencyEntry, FrequencyList


LOG = logging.getLogger(__name__)
ONEWILI_PYTHON_PATHS = (Path("/opt/onewili/python"), Path("/opt/onewili/cm0/python"))


class DisplayUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class DisplaySnapshot:
    connected: bool
    message: str


class NullDisplay:
    def connect(self) -> None:
        return

    def build(self, frequency_list: FrequencyList, selected: int) -> None:
        return

    def show_splash(self, duration_seconds: float = 3.0) -> None:
        del duration_seconds
        return

    def update_receiver(self, entry: FrequencyEntry, rssi_dbfs: float, peak_offset_hz: float) -> None:
        return

    def push_waterfall(self, bins: list[int]) -> None:
        return

    def poll_action(self) -> str | None:
        return None

    def update_selection(self, selected: int) -> None:
        return

    def build_lists(
        self,
        frequency_lists: list[FrequencyList],
        active: int,
        selected: int,
    ) -> None:
        return

    def build_library(
        self,
        entries: list[FrequencyEntry],
        live_frequencies: set[int],
        live_count: int,
        total: int,
        offset: int,
        selected: int,
    ) -> None:
        del entries, live_frequencies, live_count, total, offset, selected
        return

    def update_list_selection(self, selected: int) -> None:
        return

    def set_button_labels(self, labels: tuple[str, str, str, str, str]) -> None:
        return

    def set_status(self, text: str) -> None:
        return

    def set_footer(self, text: str, color: str = "#8DA1A9") -> None:
        return

    def set_pocket_alert(self, enabled: bool, threshold_dbfs: int) -> None:
        del enabled, threshold_dbfs
        return

    def close(self) -> None:
        return

    @property
    def snapshot(self) -> DisplaySnapshot:
        return DisplaySnapshot(False, "headless")


class OneWiliDisplay:
    """Uses stock dynamic controls; no display firmware replacement required."""

    CONTROL_BRAND = 0
    CONTROL_STATUS = 1
    CONTROL_FREQUENCY = 2
    CONTROL_SPAN = 3
    CONTROL_RSSI = 4
    CONTROL_PEAK = 5
    CONTROL_LIST = 6
    CONTROL_WATERFALL = 7
    CONTROL_RSSI_RANGE = 8
    CONTROL_RSSI_VALUE = 9
    CONTROL_RSSI_TICKS = 10
    CONTROL_MESSAGE = 11
    CONTROL_RSSI_MARKER = 12
    CONTROL_CENTER_MARKER = 13
    RSSI_MARKER_STEPS = 33
    CONTROL_BUTTON_FIRST = CONTROL_CENTER_MARKER + 1
    LIST_INDEX = 0
    PLOT_INDEX = 0
    # Twelve display bins preserve useful narrowband shape across a 200 kHz
    # hunt span while cutting 25% of the mailbox commands from every row.  The
    # rejected eight-bin profile was visibly too coarse.
    WATERFALL_BINS = 12
    WATERFALL_X = 148
    WATERFALL_Y = 86
    WATERFALL_WIDTH = 324
    WATERFALL_HEIGHT = 142
    RSSI_SCALE_X = 140
    RSSI_SCALE_WIDTH = 264
    RSSI_FLOOR_DBFS = -70.0
    RSSI_CEILING_DBFS = -10.0
    PEAK_UPDATE_DIVISOR = 5
    BUTTON_STREAM_INTERVAL_MS = 33

    def __init__(self) -> None:
        self.device: Any = None
        self._message = "not connected"
        self._button_state = (0, 0, 0, 0, 0)
        self._pending_actions: deque[str] = deque()
        self._waterfall_row = 0
        self._last_frequency = ""
        self._last_span = ""
        self._last_status = ""
        self._last_rssi = ""
        self._last_peak = ""
        self._button_labels = ("", "", "", "", "")
        self._rssi_marker_index: int | None = None
        self._receiver_updates = 0
        self._pending_frame_commands: list[str] = []

    def connect(self) -> None:
        for path in reversed(ONEWILI_PYTHON_PATHS):
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))
        try:
            from onewili import OneWili

            from .cm0_transport import SocketCm0Transport

            transport = SocketCm0Transport()
            self.device = OneWili(transport=transport).open()
            # h\\a\\e is a Main-host gate and does not acknowledge through the
            # CM0 Display transport on FX0177 v07. Sending it here made clean
            # starts depend on stale frames. Enable only the supported g\\o
            # source on this channel; physical delivery is validated separately.
            # g\u's generated signature discards the five synchronous button
            # bytes. Ask firmware for documented 33 ms unsolicited events so
            # even a quick tap spans several samples without adding a blocking
            # read to every waterfall transaction.
            from onewili import encoding

            self._require(
                self.device.gui._call(  # noqa: SLF001 - generated API omits this method
                    "o",
                    [encoding.enc_int(self.BUTTON_STREAM_INTERVAL_MS)],
                    [],
                ),
                "enable button events",
            )
            self._message = "connected"
        except Exception as error:
            self.device = None
            self._message = str(error)
            raise DisplayUnavailable(f"FreeWili CM0 display bridge unavailable: {error}") from error

    @staticmethod
    def _require(result: Any, action: str) -> None:
        if hasattr(result, "is_err") and result.is_err():
            raise DisplayUnavailable(f"{action}: {result.err_value}")

    def _add_waterfall(self) -> Any:
        controls = self.device.gui.controls
        method = getattr(controls, "add_waterfall", None)
        if method is not None:
            return method(
                self.CONTROL_WATERFALL,
                self.PLOT_INDEX,
                self.WATERFALL_BINS,
                self.WATERFALL_X,
                self.WATERFALL_Y,
                self.WATERFALL_WIDTH,
                self.WATERFALL_HEIGHT,
                "#000B17",
            )

        # CM0 images may contain an older generated Python surface even when
        # MAIN firmware implements the current g\b\m command. Use the same
        # generated encoder and menu call until the image package catches up.
        from onewili import encoding

        return controls._call(  # noqa: SLF001 - compatibility shim
            "m",
            [
                encoding.enc_int(self.CONTROL_WATERFALL),
                encoding.enc_int(self.PLOT_INDEX),
                encoding.enc_int(self.WATERFALL_BINS),
                encoding.enc_int(self.WATERFALL_X),
                encoding.enc_int(self.WATERFALL_Y),
                encoding.enc_int(self.WATERFALL_WIDTH),
                encoding.enc_int(self.WATERFALL_HEIGHT),
                encoding.enc_color("#000B17"),
            ],
            [],
        )

    def _add_center_marker(self, gui: Any) -> None:
        """Overlay a narrow reference at the exact tuned-frequency center.

        The v07 dynamic-control surface does not expose a line primitive. A
        two-pixel, blank button is the smallest solid control it can render and
        gives the waterfall an unambiguous center reference without altering
        any spectrum bins.
        """

        center_x = self.WATERFALL_X + self.WATERFALL_WIDTH // 2 - 1
        self._require(
            gui.controls.add_button(
                self.CONTROL_CENTER_MARKER,
                center_x,
                self.WATERFALL_Y,
                2,
                self.WATERFALL_HEIGHT,
                "#DDF7FF",
                "#DDF7FF",
                "",
            ),
            "add waterfall center marker",
        )

    def _reset_panel(self) -> Any:
        if self.device is None:
            raise DisplayUnavailable("display is not connected")
        # Recreate panel index 0 directly. The older s\f\r reset path is not
        # acknowledged by clean FX0177 v07 firmware and made every fresh start
        # fail before the first control was added. add_panel replaces the
        # indexed dynamic panel and is the supported idempotent boundary here.
        gui = self.device.gui
        # The Display CPU owns the five physical context keys.  A dynamic
        # panel must opt into its native menu handling before those presses are
        # published to the OneWili button stream.  The custom controls below
        # still draw WaveRider's styled labels; this flag is the input gate.
        self._require(gui.panels.add_panel(False, 0, "#071014", True), "create panel")
        return gui

    def _add_brand(self, gui: Any, section: str) -> None:
        self._require(
            gui.controls.add_text(
                self.CONTROL_BRAND, 8, 7, 0, 1, "#F4F8F9", "#071014", "WaveRider"
            ),
            "add WaveRider brand",
        )
        self._require(
            gui.controls.add_text(
                self.CONTROL_STATUS, 372, 7, 0, 1, "#34E69F", "#071014", section
            ),
            "add status",
        )

    def show_splash(self, duration_seconds: float = 3.0) -> None:
        """Show the Main-SD WaveRider image before constructing live controls.

        The standalone firmware image command can read Main SD. Dynamic picture
        controls are rendered by the Display processor and report ``Pic Not
        Found`` for the same Main-SD path on FW2 v07.
        """

        if self.device is None:
            raise DisplayUnavailable("display is not connected")
        self._require(
            self.device.gui.show_fwi_image("1:/images/WAVERIDR.FWI"),
            "show WaveRider splash",
        )
        time.sleep(max(0.0, duration_seconds))

    def _add_button_strip(
        self,
        gui: Any,
        labels: tuple[str, str, str, str, str],
    ) -> None:
        positions = (4, 100, 196, 292, 388)
        colors = ("#C3CDD1", "#FFD84A", "#38D17C", "#48A9E8", "#FF7464")
        for offset, (x, label, color) in enumerate(zip(positions, labels, colors, strict=True)):
            self._require(
                gui.controls.add_button(
                    self.CONTROL_BUTTON_FIRST + offset,
                    x,
                    290,
                    88,
                    26,
                    color,
                    "#0C171C",
                    label,
                ),
                f"add {label} button",
            )
        self._button_labels = labels

    def _add_rssi_range(self, gui: Any) -> None:
        """Add a continuous RGB565 range image and a discrete moving pointer."""

        self._require(
            gui.controls.add_picture_from_file(
                self.CONTROL_RSSI_RANGE,
                self.RSSI_SCALE_X,
                237,
                # FW2 v07's Display renderer resolves picture controls from
                # its images directory and rejects the otherwise valid Main
                # filesystem prefix with an on-screen "Pic Not Found".
                "RSSISCL.FWI",
            ),
            "add RSSI color range",
        )

        # One fixed-width marker track repaints its complete old value. Do not
        # use spaces for the inactive cells: the v07 command parser strips
        # leading whitespace and collapses every marker back to the cold edge.
        # Hyphens survive the bridge and make the moving V unmistakable.
        self._require(
            gui.controls.add_text(
                self.CONTROL_RSSI_MARKER,
                self.RSSI_SCALE_X,
                224,
                0,
                0,
                "#FFFFFF",
                "#071014",
                "-" * self.RSSI_MARKER_STEPS,
            ),
            "add RSSI pointer track",
        )

        self._require(
            gui.controls.add_text(
                self.CONTROL_RSSI_VALUE,
                414,
                235,
                0,
                0,
                "#FFD36F",
                "#071014",
                "--.-",
            ),
            "add RSSI range value",
        )

    def build(self, frequency_list: FrequencyList, selected: int) -> None:
        gui = self._reset_panel()
        self._add_brand(gui, "CONNECT")
        selected_entry = frequency_list.frequencies[selected]
        self._require(
            gui.controls.add_text(
                self.CONTROL_FREQUENCY,
                148,
                31,
                0,
                2,
                "#FFFFFF",
                "#071014",
                f"{selected_entry.frequency_hz / 1_000_000:.3f}",
            ),
            "add frequency",
        )
        self._require(
            gui.controls.add_text(
                self.CONTROL_SPAN,
                330,
                45,
                0,
                0,
                "#8DA1A9",
                "#071014",
                f"SPAN {selected_entry.span_hz // 1000} kHz",
            ),
            "add span",
        )
        self._require(
            gui.controls.add_text(
                self.CONTROL_RSSI, 148, 69, 0, 1, "#FFD36F", "#071014", "RSSI --.- dBFS"
            ),
            "add RSSI",
        )
        self._require(
            gui.controls.add_text(
                self.CONTROL_PEAK, 354, 70, 0, 0, "#8DA1A9", "#071014", "PK -- kHz"
            ),
            "add peak",
        )
        self._require(
            gui.controls.add_log_list(
                self.CONTROL_LIST,
                self.LIST_INDEX,
                8,
                34,
                132,
                251,
                0,
                1,
                "#0A151A",
                "#A9BDC5",
                True,
            ),
            "add frequency list",
        )
        self._require(self._add_waterfall(), "add waterfall")
        self._add_center_marker(gui)
        self._add_rssi_range(gui)
        self._require(
            gui.controls.add_text(
                self.CONTROL_RSSI_TICKS,
                140,
                251,
                0,
                0,
                "#738A93",
                "#071014",
                "-70       -50       -30       -10",
            ),
            "add RSSI legend",
        )
        self._require(
            gui.controls.add_text(
                self.CONTROL_MESSAGE, 148, 274, 0, 0, "#8DA1A9", "#071014", ""
            ),
            "add message",
        )
        for index, entry in enumerate(frequency_list.frequencies):
            # The live hunt view is glance-first: use the larger native font
            # and keep descriptive labels in Lists/editor rather than forcing
            # tiny or clipped text into the narrow channel rail.
            label = f"{entry.frequency_hz / 1_000_000:.3f}"
            self._require(
                gui.control_properties.set_list_item_text(self.LIST_INDEX, index, 0xA9BDC5, label),
                "populate frequency list",
            )
        self._require(
            gui.control_properties.set_list_item_selected(self.LIST_INDEX, selected),
            "select frequency",
        )
        self._add_button_strip(gui, ("LISTS", "BAND", "NEXT", "MARK", "STOP"))
        self._require(gui.panels.show_panel(0), "show panel")
        self._waterfall_row = 0
        self._last_frequency = f"{selected_entry.frequency_hz / 1_000_000:.3f}"
        self._last_span = f"SPAN {selected_entry.span_hz // 1000} kHz"
        self._last_status = "CONNECT"
        self._last_rssi = ""
        self._last_peak = ""
        self._rssi_marker_index = None
        self._receiver_updates = 0
        self._pending_frame_commands = []
        self._message = "panel active"

    def build_lists(
        self,
        frequency_lists: list[FrequencyList],
        active: int,
        selected: int,
    ) -> None:
        gui = self._reset_panel()
        self._add_brand(gui, "LISTS")
        self._require(
            gui.controls.add_text(
                self.CONTROL_FREQUENCY,
                8,
                38,
                0,
                1,
                "#FFFFFF",
                "#071014",
                "FREQUENCY LISTS",
            ),
            "add lists title",
        )
        self._require(
            gui.controls.add_log_list(
                self.CONTROL_LIST,
                self.LIST_INDEX,
                8,
                70,
                464,
                211,
                0,
                1,
                "#0A151A",
                "#A9BDC5",
                True,
            ),
            "add named list picker",
        )
        for index, item in enumerate(frequency_lists):
            marker = "ACTIVE" if index == active else "      "
            text = f"{marker}  {item.name}  ({len(item.frequencies)})"
            color = 0x34E69F if index == active else 0xA9BDC5
            self._require(
                gui.control_properties.set_list_item_text(self.LIST_INDEX, index, color, text),
                "populate named list picker",
            )
        self._require(
            gui.control_properties.set_list_item_selected(self.LIST_INDEX, selected),
            "select named list",
        )
        self._add_button_strip(gui, ("BACK", "PREV", "NEXT", "USE", "EDIT"))
        self._require(gui.panels.show_panel(0), "show list picker")
        self._message = "list picker active"

    def update_receiver(self, entry: FrequencyEntry, rssi_dbfs: float, peak_offset_hz: float) -> None:
        if self.device is None:
            return
        properties = self.device.gui.control_properties
        transport = getattr(self.device, "_transport", None)
        batched = callable(getattr(transport, "call_batch", None))
        commands: list[str] = []
        self._receiver_updates += 1
        values = (
            (self.CONTROL_FREQUENCY, f"{entry.frequency_hz / 1_000_000:.3f}", "_last_frequency"),
            (self.CONTROL_SPAN, f"SPAN {entry.span_hz // 1000} kHz", "_last_span"),
            (self.CONTROL_STATUS, "SDR LIVE", "_last_status"),
            (self.CONTROL_RSSI, f"RSSI {rssi_dbfs:.1f} dBFS", "_last_rssi"),
        )
        for control, text, cache in values:
            if getattr(self, cache) == text:
                continue
            if batched:
                commands.append(f"g\\e\\a {control} {text}")
            else:
                self._require(properties.set_control_value_text(control, text), f"update {cache}")
            setattr(self, cache, text)
        peak_text = f"PK {peak_offset_hz / 1000:+.1f} kHz"
        if (
            self._last_peak != peak_text
            and (not self._last_peak or self._receiver_updates % self.PEAK_UPDATE_DIVISOR == 0)
        ):
            if batched:
                commands.append(f"g\\e\\a {self.CONTROL_PEAK} {peak_text}")
            else:
                self._require(
                    properties.set_control_value_text(self.CONTROL_PEAK, peak_text),
                    "update _last_peak",
                )
            self._last_peak = peak_text
        range_value = f"{rssi_dbfs:.1f}"
        if batched:
            commands.append(f"g\\e\\a {self.CONTROL_RSSI_VALUE} {range_value}")
        else:
            self._require(
                properties.set_control_value_text(self.CONTROL_RSSI_VALUE, range_value),
                "update RSSI range value",
            )
        clamped = max(self.RSSI_FLOOR_DBFS, min(self.RSSI_CEILING_DBFS, rssi_dbfs))
        marker_index = round(
            (clamped - self.RSSI_FLOOR_DBFS)
            * (self.RSSI_MARKER_STEPS - 1)
            / (self.RSSI_CEILING_DBFS - self.RSSI_FLOOR_DBFS)
        )
        if marker_index != self._rssi_marker_index:
            marker_text = (
                "-" * marker_index
                + "V"
                + "-" * (self.RSSI_MARKER_STEPS - marker_index - 1)
            )
            if batched:
                commands.append(f"g\\e\\a {self.CONTROL_RSSI_MARKER} {marker_text}")
            else:
                self._require(
                    properties.set_control_value_text(self.CONTROL_RSSI_MARKER, marker_text),
                    "move RSSI pointer",
                )
            self._rssi_marker_index = marker_index
        self._pending_frame_commands = commands

    def push_waterfall(self, bins: list[int]) -> None:
        if self.device is None:
            return
        properties = self.device.gui.control_properties
        values = bins[: self.WATERFALL_BINS]
        transport = getattr(self.device, "_transport", None)
        batch = getattr(transport, "call_batch", None)
        if batch is not None:
            self._waterfall_row = (self._waterfall_row + 1) & 0x7FFFFFFF
            commands = self._pending_frame_commands + [
                f"g\\e\\f {self.PLOT_INDEX} 0 {int(value)}" for value in values
            ]
            commands.append(
                f"g\\e\\b {self.CONTROL_WATERFALL} {self._waterfall_row}"
            )
            self._pending_frame_commands = []
            try:
                batch(commands)
            except (RuntimeError, TimeoutError) as error:
                raise DisplayUnavailable(f"push waterfall: {error}") from error
        else:
            for value in values:
                result = properties.set_plot_data(self.PLOT_INDEX, 0, int(value))
                if hasattr(result, "is_err") and result.is_err():
                    raise DisplayUnavailable(f"push waterfall: {result.err_value}")
            # Waterfall bins are staged in the plot-data buffer. Changing the
            # control value commits that buffer as the next spectrogram row.
            self._waterfall_row = (self._waterfall_row + 1) & 0x7FFFFFFF
            self._require(
                properties.set_control_value_int(self.CONTROL_WATERFALL, self._waterfall_row),
                "commit waterfall row",
            )
        # Drain input after the row commit so presses are captured even while
        # the main loop is busy in a Display round trip.  Every queued state is
        # processed in order; keeping only the newest state loses a complete
        # press whenever both its down and up events arrive between frames.
        self._sample_button_events()

    def _sample_button_events(self) -> None:
        if self.device is None:
            return
        transport = getattr(self.device, "_transport", None)
        events = getattr(transport, "events", None)
        if events is None:
            return
        names = ("gray", "yellow", "green", "blue", "red")
        while True:
            try:
                frame = events.get_nowait()
            except queue.Empty:
                break
            # Generated transports differ on whether unsolicited event paths
            # retain the wire-level leading '*'. Accept both representations.
            if str(getattr(frame, "path", "")).lstrip("*").casefold() != "button":
                continue
            try:
                values = tuple(
                    int(value, 16) if value.casefold().startswith("0x") else int(value, 10)
                    for value in frame.response.split()[:5]
                )
            except (AttributeError, TypeError, ValueError):
                LOG.debug("unrecognized button event: %s", frame)
                continue
            if len(values) != 5:
                LOG.debug("incomplete button event: %s", frame)
                continue
            previous = self._button_state
            self._button_state = values
            LOG.debug("button state: %s", values)
            for index, name in enumerate(names):
                if values[index] and not previous[index]:
                    self._pending_actions.append(name)

    def poll_action(self) -> str | None:
        self._sample_button_events()
        if self._pending_actions:
            return self._pending_actions.popleft()
        return None

    def update_selection(self, selected: int) -> None:
        if self.device is None:
            return
        properties = self.device.gui.control_properties
        self._require(
            properties.set_list_item_selected(self.LIST_INDEX, selected),
            "select frequency",
        )
        self._require(
            properties.set_list_item_top_index(self.LIST_INDEX, max(0, selected - 2)),
            "scroll frequency list",
        )

    def update_list_selection(self, selected: int) -> None:
        self.update_selection(selected)

    def set_button_labels(self, labels: tuple[str, str, str, str, str]) -> None:
        if self.device is None:
            return
        properties = self.device.gui.control_properties
        for offset, label in enumerate(labels):
            if self._button_labels[offset] == label:
                continue
            self._require(
                properties.set_control_value_text(self.CONTROL_BUTTON_FIRST + offset, label),
                "update button label",
            )
        self._button_labels = labels

    def set_status(self, text: str) -> None:
        if self.device is None or self._last_status == text:
            return
        self._require(
            self.device.gui.control_properties.set_control_value_text(self.CONTROL_STATUS, text),
            "update status",
        )
        self._last_status = text

    def set_footer(self, text: str, color: str = "#8DA1A9") -> None:
        if self.device is None:
            return
        # Text color is fixed when the panel is built; the parameter keeps the
        # display interface expressive for a future native panel implementation.
        del color
        self._require(
            self.device.gui.control_properties.set_control_value_text(self.CONTROL_MESSAGE, text[:42]),
            "update message",
        )

    def set_pocket_alert(self, enabled: bool, threshold_dbfs: int) -> None:
        # Pocket Alert is implemented by the native Display app because the
        # haptic motor is wired to its RP2350 GPIO, not the CM0 Linux host.
        del enabled, threshold_dbfs

    def close(self) -> None:
        if self.device is not None:
            try:
                self.device.close()
            finally:
                self.device = None
                self._message = "closed"

    @property
    def snapshot(self) -> DisplaySnapshot:
        return DisplaySnapshot(self.device is not None, self._message)


class NativeSignalDisplay:
    """Exchange WaveRider state with the loadable native Display app.

    The stock dynamic-panel firmware does not forward the FW2 keyboard on the
    tested v07 image.  The native app reads that keyboard directly and uses
    Main's app-signal mailbox for bidirectional communication with this CM0
    process.  Three 16-bit row words carry twelve four-bit waterfall bins;
    these values remain exactly representable even if Main stores signals as
    single-precision floats.
    """

    WATERFALL_BINS = 12
    MAX_LIST_ENTRIES = 16
    COMMAND_POLL_SECONDS = 0.03
    SIGNAL_NAMES = (
        "wr_cmd",
        "wr_ack",
        "wr_proto",
        "wr_ready",
        "wr_seq",
        "wr_freq",
        "wr_span",
        "wr_rssi",
        "wr_peak",
        "wr_row0",
        "wr_row1",
        "wr_row2",
        "wr_sel",
        "wr_count",
        "wr_lseq",
        "wr_state",
        *(f"wr_f{index}" for index in range(MAX_LIST_ENTRIES)),
    )
    ACTIONS = {
        1: "gray",
        2: "yellow",
        3: "green",
        4: "blue",
        5: "red",
    }

    def __init__(self, transport_factory: Any | None = None) -> None:
        self._transport_factory = transport_factory
        self._transport: Any | None = None
        self._message = "not connected"
        self._selected = 0
        self._list_sequence = 0
        self._row_sequence = 0
        self._last_command_sequence = -1
        self._next_command_poll = 0.0
        self._pending_entry: FrequencyEntry | None = None
        self._pending_rssi = -90.0
        self._pending_peak = 0.0
        self._published_frequency_hz: int | None = None
        self._published_span_hz: int | None = None
        self._library_notice = 0
        self._alert_enabled = False
        self._alert_threshold_dbfs = -50

    def _call(self, command: str, *, required: bool = True) -> Any | None:
        if self._transport is None:
            raise DisplayUnavailable("native Display signal bridge is not connected")
        self._transport.send(command)
        frame = self._transport.wait_frame(timeout=2.0)
        if frame is None:
            if required:
                raise DisplayUnavailable(f"timeout waiting for {command.split(' ', 1)[0]}")
            return None
        if not bool(getattr(frame, "success", True)):
            if required:
                raise DisplayUnavailable(
                    f"{command.split(' ', 1)[0]}: {getattr(frame, 'response', '')}"
                )
            return None
        return frame

    def _set_many(self, values: list[tuple[str, float | int]]) -> None:
        if self._transport is None:
            raise DisplayUnavailable("native Display signal bridge is not connected")
        commands = [f"s\\i\\s {name} {float(value):.3f}" for name, value in values]
        batch = getattr(self._transport, "call_batch", None)
        try:
            if callable(batch):
                batch(commands, timeout=3.0)
            else:
                for command in commands:
                    self._call(command)
        except (RuntimeError, TimeoutError) as error:
            raise DisplayUnavailable(f"publish native Display state: {error}") from error

    def _get(self, name: str) -> float | None:
        frame = self._call(f"s\\i\\g {name}", required=False)
        if frame is None:
            return None
        fields = str(getattr(frame, "response", "")).split()
        if len(fields) < 2 or fields[0] != name:
            return None
        try:
            return float(fields[1])
        except ValueError:
            return None

    def connect(self) -> None:
        if self._transport_factory is None:
            from .cm0_transport import SocketCm0Transport

            transport = SocketCm0Transport()
        else:
            transport = self._transport_factory()
        try:
            transport.open()
            self._transport = transport
            # App signals survive a service restart. Add is deliberately
            # best-effort so reconnecting to an existing mailbox is normal.
            for name in self.SIGNAL_NAMES:
                self._call(f"s\\i\\a {name}", required=False)
            # Protocol v1 makes native button commands durable across a CM0
            # service reconnect. On the first upgrade only, acknowledge the
            # legacy command already in the mailbox so it is not replayed.
            protocol = self._get("wr_proto")
            if protocol is None or protocol < 1:
                command = int(round(self._get("wr_cmd") or 0.0))
                self._last_command_sequence = command >> 8
                self._set_many(
                    [
                        ("wr_ready", 1),
                        ("wr_state", 1),
                        ("wr_ack", self._last_command_sequence),
                        ("wr_proto", 1),
                    ]
                )
            else:
                self._last_command_sequence = int(round(self._get("wr_ack") or 0.0))
                self._set_many([("wr_ready", 1), ("wr_state", 1)])
        except Exception as error:
            try:
                transport.close()
            except Exception:
                pass
            self._transport = None
            self._message = str(error)
            if isinstance(error, DisplayUnavailable):
                raise
            raise DisplayUnavailable(f"native Display signal bridge unavailable: {error}") from error
        self._message = "native Display mailbox connected"

    def show_splash(self, duration_seconds: float = 3.0) -> None:
        # The native firmware owns its launch screen; blocking the CM0 here
        # would only delay the first SDR frame.
        del duration_seconds

    def build(self, frequency_list: FrequencyList, selected: int) -> None:
        self._selected = selected
        entries = frequency_list.frequencies[: self.MAX_LIST_ENTRIES]
        self._list_sequence = (self._list_sequence + 1) & 0xFFFF
        threshold_offset = min(80, max(0, self._alert_threshold_dbfs + 90))
        packed_count = (
            len(entries)
            | (int(self._alert_enabled) << 8)
            | (threshold_offset << 9)
        )
        values: list[tuple[str, float | int]] = [
            ("wr_state", 1),
            ("wr_count", packed_count),
            ("wr_sel", selected),
            ("wr_freq", frequency_list.frequencies[selected].frequency_hz),
            ("wr_span", frequency_list.frequencies[selected].span_hz),
        ]
        values.extend(
            (f"wr_f{index}", entry.frequency_hz)
            for index, entry in enumerate(entries)
        )
        values.extend(
            (f"wr_f{index}", 0)
            for index in range(len(entries), self.MAX_LIST_ENTRIES)
        )
        values.append(("wr_lseq", self._list_sequence))
        self._set_many(values)
        self._published_frequency_hz = frequency_list.frequencies[selected].frequency_hz
        self._published_span_hz = frequency_list.frequencies[selected].span_hz

    def set_pocket_alert(self, enabled: bool, threshold_dbfs: int) -> None:
        if not -70 <= threshold_dbfs <= -10:
            raise ValueError("pocket-alert threshold must be between -70 and -10 dBFS")
        self._alert_enabled = bool(enabled)
        self._alert_threshold_dbfs = int(threshold_dbfs)

    def build_library(
        self,
        entries: list[FrequencyEntry],
        live_frequencies: set[int],
        live_count: int,
        total: int,
        offset: int,
        selected: int,
    ) -> None:
        entries = entries[: self.MAX_LIST_ENTRIES]
        membership = 0
        for index, entry in enumerate(entries):
            if entry.frequency_hz in live_frequencies:
                membership |= 1 << index
        # The low 16 bits describe membership for this page. Keep the global
        # Live rotation count in the next five bits so a paged library can
        # repaint an accurate header immediately after a toggle.
        membership |= min(max(0, live_count), self.MAX_LIST_ENTRIES) << 16
        self._list_sequence = (self._list_sequence + 1) & 0xFFFF
        values: list[tuple[str, float | int]] = [
            ("wr_state", 2),
            ("wr_freq", self._library_notice),
            ("wr_count", len(entries)),
            ("wr_sel", selected),
            ("wr_row0", membership),
            ("wr_row1", total),
            ("wr_row2", offset),
        ]
        # Library frequencies are transported as exact integer kHz so the
        # 32-bit Main mailbox does not round large Hz values. The native app
        # multiplies by 1000 only while wr_state reports Library mode.
        values.extend(
            (f"wr_f{index}", entry.frequency_hz // 1000)
            for index, entry in enumerate(entries)
        )
        values.extend(
            (f"wr_f{index}", 0)
            for index in range(len(entries), self.MAX_LIST_ENTRIES)
        )
        values.append(("wr_lseq", self._list_sequence))
        self._set_many(values)
        self._library_notice = 0

    @staticmethod
    def _pack_four(values: list[int]) -> int:
        packed = 0
        for index, value in enumerate(values[:4]):
            nibble = round(max(0, min(100, int(value))) * 15 / 100)
            packed |= nibble << (index * 4)
        return packed

    def update_receiver(
        self,
        entry: FrequencyEntry,
        rssi_dbfs: float,
        peak_offset_hz: float,
    ) -> None:
        if (
            entry.frequency_hz != self._published_frequency_hz
            or entry.span_hz != self._published_span_hz
        ):
            # Frequency and span are tuning state, not row data. Publishing
            # them only when they change removes two Main-mailbox writes from
            # every steady-state waterfall row while preserving the atomic
            # row commit below.
            self._set_many(
                [("wr_freq", entry.frequency_hz), ("wr_span", entry.span_hz)]
            )
            self._published_frequency_hz = entry.frequency_hz
            self._published_span_hz = entry.span_hz
        self._pending_entry = entry
        self._pending_rssi = rssi_dbfs
        self._pending_peak = peak_offset_hz

    def push_waterfall(self, bins: list[int]) -> None:
        entry = self._pending_entry
        if entry is None:
            return
        padded = (bins[: self.WATERFALL_BINS] + [0] * self.WATERFALL_BINS)[
            : self.WATERFALL_BINS
        ]
        self._row_sequence = (self._row_sequence + 1) & 0xFFFF
        self._set_many(
            [
                ("wr_rssi", self._pending_rssi),
                ("wr_peak", self._pending_peak),
                ("wr_row0", self._pack_four(padded[0:4])),
                ("wr_row1", self._pack_four(padded[4:8])),
                ("wr_row2", self._pack_four(padded[8:12])),
                # Commit last. The native app treats a new sequence as proof
                # that all fields for this row have landed.
                ("wr_seq", self._row_sequence),
            ]
        )

    def poll_action(self) -> str | None:
        now = time.monotonic()
        if now < self._next_command_poll:
            return None
        self._next_command_poll = now + self.COMMAND_POLL_SECONDS
        raw_value = self._get("wr_cmd")
        if raw_value is None:
            return None
        raw = int(round(raw_value))
        sequence = raw >> 8
        if sequence == self._last_command_sequence:
            return None
        self._last_command_sequence = sequence
        opcode = (raw >> 4) & 0xF
        argument = raw & 0xF
        # Acknowledge only after the complete command has been read. The
        # native side leaves wr_cmd intact, so reconnecting before this write
        # causes the command to be retried instead of erased.
        self._set_many([("wr_ack", sequence)])
        if opcode == 6:
            return f"select:{argument}"
        if opcode == 1:
            # Main v07 caps the mailbox at 32 named signals and WaveRider uses
            # all 32 when publishing sixteen list entries. Reuse wr_state for
            # this one-shot kHz payload instead of silently failing to create
            # a 33rd signal. kHz remains exactly representable at the full SDR
            # tuning range and wr_state is not row data.
            requested_khz = self._get("wr_state")
            if requested_khz is not None:
                requested_hz = int(round(requested_khz)) * 1000
                if 24_000_000 <= requested_hz <= 1_766_000_000:
                    return f"add:{requested_hz}"
        if opcode == 7:
            return "lists"
        if opcode == 8:
            return "library_prev_page"
        if opcode == 9:
            return "library_next_page"
        if opcode == 10:
            return f"library_toggle:{argument}"
        if opcode == 11:
            return f"library_delete:{argument}"
        if opcode == 12:
            return f"library_tune:{argument}"
        if opcode == 13:
            return "library_back"
        if opcode == 14:
            return f"alert_enabled:{1 if argument else 0}"
        if opcode == 15:
            threshold_offset = self._get("wr_state")
            if threshold_offset is not None:
                threshold_dbfs = int(round(threshold_offset)) - 90
                if -70 <= threshold_dbfs <= -10:
                    return f"alert_threshold:{threshold_dbfs}"
        return self.ACTIONS.get(opcode)

    def update_selection(self, selected: int) -> None:
        self._selected = selected
        # The pending SDR sample can still describe the previous tuning here.
        # Publish only the new selection; the next committed waterfall frame
        # carries the matching receiver frequency and span.
        self._set_many([("wr_sel", selected)])

    def build_lists(
        self,
        frequency_lists: list[FrequencyList],
        active: int,
        selected: int,
    ) -> None:
        del frequency_lists, active, selected
        self._set_many([("wr_state", 2)])

    def update_list_selection(self, selected: int) -> None:
        del selected

    def set_button_labels(self, labels: tuple[str, str, str, str, str]) -> None:
        del labels

    def set_status(self, text: str) -> None:
        state = 3 if text.casefold() == "paused" else 1
        self._set_many([("wr_state", state)])

    def set_footer(self, text: str, color: str = "#8DA1A9") -> None:
        del color
        normalized = text.upper()
        if "LIVE LIST FULL" in normalized:
            self._library_notice = 1
        elif "KEEP AT LEAST ONE" in normalized:
            self._library_notice = 2
        elif "SAVED LIBRARY FULL" in normalized:
            self._library_notice = 3
        elif "OUT OF SDR RANGE" in normalized:
            self._library_notice = 4
        elif "ALREADY SAVED" in normalized:
            self._library_notice = 5
        elif normalized == "SAVED":
            self._library_notice = 6
        elif normalized == "LIVE LIST UPDATED":
            self._library_notice = 7
        elif normalized == "DELETED":
            self._library_notice = 8

    def close(self) -> None:
        if self._transport is not None:
            try:
                self._set_many([("wr_ready", 0)])
            except DisplayUnavailable:
                pass
            try:
                self._transport.close()
            finally:
                self._transport = None
        self._message = "closed"

    @property
    def snapshot(self) -> DisplaySnapshot:
        return DisplaySnapshot(self._transport is not None, self._message)


def create_display() -> OneWiliDisplay | NativeSignalDisplay:
    backend = os.environ.get("WAVERIDER_DISPLAY_BACKEND", "stock").strip().casefold()
    if backend in {"native", "signals", "display-app"}:
        return NativeSignalDisplay()
    return OneWiliDisplay()
