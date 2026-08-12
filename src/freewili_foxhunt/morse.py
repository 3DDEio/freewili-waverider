"""Dependency-free narrow-FM tone and Morse decoding for the CM0 IQ path."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from statistics import median


MORSE_TO_TEXT = {
    ".-": "A",
    "-...": "B",
    "-.-.": "C",
    "-..": "D",
    ".": "E",
    "..-.": "F",
    "--.": "G",
    "....": "H",
    "..": "I",
    ".---": "J",
    "-.-": "K",
    ".-..": "L",
    "--": "M",
    "-.": "N",
    "---": "O",
    ".--.": "P",
    "--.-": "Q",
    ".-.": "R",
    "...": "S",
    "-": "T",
    "..-": "U",
    "...-": "V",
    ".--": "W",
    "-..-": "X",
    "-.--": "Y",
    "--..": "Z",
    "-----": "0",
    ".----": "1",
    "..---": "2",
    "...--": "3",
    "....-": "4",
    ".....": "5",
    "-....": "6",
    "--...": "7",
    "---..": "8",
    "----.": "9",
    ".-.-.-": ".",
    "--..--": ",",
    "..--..": "?",
    ".----.": "'",
    "-.-.--": "!",
    "-..-.": "/",
    "-....-": "-",
    ".--.-.": "@",
}

CALLSIGN_TOKEN = re.compile(r"^(?=.{3,8}$)(?=.*[A-Z])(?=.*\d)[A-Z0-9]+$")


@dataclass(frozen=True)
class DecodedMessage:
    text: str
    confidence: float
    timing_confidence: float = 0.0
    signal_confidence: float = 1.0


class MorseTimingDecoder:
    """Convert a debounced tone/no-tone stream into complete Morse messages."""

    MIN_UNIT_SECONDS = 1.2 / 30.0
    MAX_UNIT_SECONDS = 1.2 / 8.0

    def __init__(self, initial_wpm: float = 13.0) -> None:
        self.initial_unit_seconds = 1.2 / initial_wpm
        self.reset()

    def reset(self) -> None:
        self.unit_seconds = self.initial_unit_seconds
        self.tone = False
        self.elapsed = 0.0
        self._marks: list[float] = []
        self._gaps: list[float] = []
        self._signal_evidence: list[float] = []
        self.last_attempt_text: str | None = None
        self.last_attempt_confidence: float | None = None
        self.last_attempt_timing_confidence: float | None = None
        self.last_attempt_signal_confidence: float | None = None
        self.last_attempt_known_confidence: float | None = None
        self.last_attempt_rejection: str | None = None
        self.attempt_count = 0
        self.last_attempt_raw_duration_ms: int | None = None
        self.last_attempt_duration_ms: int | None = None
        self.last_attempt_raw_mark_count = 0
        self.last_attempt_raw_gap_count = 0
        self.last_attempt_raw_mark_range_ms: tuple[int, int, int] | None = None
        self.last_attempt_raw_gap_range_ms: tuple[int, int, int] | None = None
        self.last_attempt_mark_count = 0
        self.last_attempt_gap_count = 0
        self.last_attempt_mark_range_ms: tuple[int, int, int] | None = None
        self.last_attempt_gap_range_ms: tuple[int, int, int] | None = None
        self.last_attempt_unit_ms: float | None = None

    @staticmethod
    def _duration_summary_ms(values: list[float]) -> tuple[int, int, int] | None:
        if not values:
            return None
        return (
            round(min(values) * 1000.0),
            round(median(values) * 1000.0),
            round(max(values) * 1000.0),
        )

    @staticmethod
    def _trimmed_mean(values: list[float]) -> float:
        ordered = sorted(values)
        if len(ordered) >= 8:
            trim = max(1, len(ordered) // 10)
            ordered = ordered[trim:-trim]
        return sum(ordered) / max(1, len(ordered))

    def _estimate_unit(
        self,
        marks: list[float] | None = None,
        gaps: list[float] | None = None,
    ) -> tuple[float, float]:
        """Fit all message timings at once instead of trusting the first mark.

        A common field failure was a 20 WPM beacon starting while the decoder
        still assumed 13 WPM.  Its first 180 ms dash landed just below the old
        online dot/dash threshold and became a valid-but-wrong letter.  Whole
        message fitting evaluates every plausible dot unit against the 1/3
        mark and 1/3/7 gap ratios, making the preamble help decode itself.
        """

        marks = self._marks if marks is None else marks
        gaps = self._gaps if gaps is None else gaps
        candidates = [self.unit_seconds, self.initial_unit_seconds]
        for duration in marks:
            candidates.extend((duration, duration / 3.0))
        for duration in gaps:
            candidates.extend((duration, duration / 3.0, duration / 7.0))
        candidates = [
            value
            for value in candidates
            if self.MIN_UNIT_SECONDS <= value <= self.MAX_UNIT_SECONDS
        ]
        if not candidates:
            return self.unit_seconds, 0.0

        def score(unit: float) -> float:
            residuals: list[float] = []
            for duration in marks:
                ratio = duration / unit
                residuals.append(min(abs(ratio - 1.0), abs(ratio - 3.0)))
            for duration in gaps:
                ratio = duration / unit
                residuals.append(
                    min(abs(ratio - 1.0), abs(ratio - 3.0), abs(ratio - 7.0))
                )
            # A small continuity term breaks genuinely ambiguous all-dot or
            # all-dash samples without overpowering the message evidence.
            continuity = abs(unit - self.unit_seconds) / max(
                self.MIN_UNIT_SECONDS, self.unit_seconds
            )
            return self._trimmed_mean(residuals) + continuity * 0.15

        unit = min(candidates, key=score)
        residual = score(unit)
        return unit, max(0.0, min(1.0, 1.0 - residual / 0.85))

    def _clean_runs(
        self, unit: float
    ) -> tuple[list[float], list[float]]:
        """Merge receiver clicks/dropouts shorter than a plausible Morse dot."""

        # Cleaning must not use a newly fitted *slower* unit as its dropout
        # threshold.  On the connected 13 WPM beacon, detector hysteresis
        # shortened ordinary intra-symbol gaps to about 60 ms.  An ambiguous
        # preliminary fit drifted to 129 ms, treated those real gaps as
        # dropouts, and merged adjacent marks into impossible 620 ms runs.
        # Anchor cleanup to the already-established speed when it is faster;
        # only a no-tone run below 60% of that unit is safe to erase.  This
        # still repairs the physically modeled 33 ms dropout at 20 WPM while
        # preserving the observed 60 ms separators at 13 WPM.
        cleanup_unit = min(unit, self.unit_seconds)

        runs: list[list[float | bool]] = []
        for index, mark in enumerate(self._marks):
            runs.append([True, mark])
            if index < len(self._gaps):
                runs.append([False, self._gaps[index]])
        changed = True
        while changed and len(runs) >= 3:
            changed = False
            for index in range(1, len(runs) - 1):
                is_tone = bool(runs[index][0])
                duration = float(runs[index][1])
                left_same = bool(runs[index - 1][0]) == (not is_tone)
                right_same = bool(runs[index + 1][0]) == (not is_tone)
                threshold = cleanup_unit * (0.55 if is_tone else 0.60)
                if duration >= threshold or not (left_same and right_same):
                    continue
                merged = (
                    float(runs[index - 1][1])
                    + duration
                    + float(runs[index + 1][1])
                )
                runs[index - 1 : index + 2] = [[not is_tone, merged]]
                changed = True
                break
        while (
            runs
            and bool(runs[0][0])
            and float(runs[0][1]) < cleanup_unit * 0.55
        ):
            runs.pop(0)
            if runs and not bool(runs[0][0]):
                runs.pop(0)
        while (
            runs
            and bool(runs[-1][0])
            and float(runs[-1][1]) < cleanup_unit * 0.55
        ):
            runs.pop()
            if runs and not bool(runs[-1][0]):
                runs.pop()
        marks = [float(duration) for tone, duration in runs if bool(tone)]
        gaps = [float(duration) for tone, duration in runs if not bool(tone)]
        return marks, gaps

    def _finish_message(self) -> DecodedMessage | None:
        if not self._marks:
            return None
        self.attempt_count += 1
        unit, _ = self._estimate_unit()
        unit = max(self.unit_seconds * 0.60, min(self.unit_seconds * 1.40, unit))
        unit = max(self.MIN_UNIT_SECONDS, min(self.MAX_UNIT_SECONDS, unit))
        self.last_attempt_raw_mark_count = len(self._marks)
        self.last_attempt_raw_gap_count = len(self._gaps)
        self.last_attempt_raw_mark_range_ms = self._duration_summary_ms(self._marks)
        self.last_attempt_raw_gap_range_ms = self._duration_summary_ms(self._gaps)
        self.last_attempt_raw_duration_ms = round(
            (sum(self._marks) + sum(self._gaps)) * 1000.0
        )
        marks, gaps = self._clean_runs(unit)
        unit, fit_confidence = self._estimate_unit(marks, gaps)
        unit = max(self.unit_seconds * 0.60, min(self.unit_seconds * 1.40, unit))
        unit = max(self.MIN_UNIT_SECONDS, min(self.MAX_UNIT_SECONDS, unit))
        self.last_attempt_mark_count = len(marks)
        self.last_attempt_gap_count = len(gaps)
        self.last_attempt_mark_range_ms = self._duration_summary_ms(marks)
        self.last_attempt_gap_range_ms = self._duration_summary_ms(gaps)
        self.last_attempt_duration_ms = round((sum(marks) + sum(gaps)) * 1000.0)
        self.last_attempt_unit_ms = unit * 1000.0
        characters: list[str] = []
        symbols: list[str] = []
        timing_scores: list[float] = []

        def finish_character() -> None:
            if not symbols:
                return
            characters.append(MORSE_TO_TEXT.get("".join(symbols), "?"))
            symbols.clear()

        for index, duration in enumerate(marks):
            ratio = duration / unit
            expected = 1.0 if ratio < 2.0 else 3.0
            symbols.append("." if expected == 1.0 else "-")
            timing_scores.append(max(0.0, 1.0 - abs(ratio - expected) / 0.9))
            if index >= len(gaps):
                continue
            gap_ratio = gaps[index] / unit
            expected_gap = min((1.0, 3.0, 7.0), key=lambda value: abs(gap_ratio - value))
            timing_scores.append(
                max(0.0, 1.0 - abs(gap_ratio - expected_gap) / 1.25)
            )
            # The 20 ms tone detector's attack/release hysteresis compresses
            # over-air separator ratios: the connected 13 WPM beacon produced
            # stable clusters near 0.7 (inside a character), 1.6 (between
            # characters), and 5.8 (between words).  Conservative midpoints
            # at 1.5 and 4.0 preserve those three clusters.  Confidence still
            # scores against ideal 1/3/7 timing, so merely relaxing a boundary
            # cannot promote noisy text through the quality gate.
            if gap_ratio >= 4.0:
                finish_character()
                if characters and characters[-1] != " ":
                    characters.append(" ")
            elif gap_ratio >= 1.5:
                finish_character()
        finish_character()

        text = "".join(characters).strip()
        decoded = sum(character != " " for character in text)
        unknown = text.count("?")
        useful = sum(character.isalnum() for character in text)
        known_confidence = 0.0 if decoded == 0 else 1.0 - unknown / decoded
        timing_confidence = (
            0.55 * fit_confidence
            + 0.45 * self._trimmed_mean(timing_scores)
            if timing_scores
            else 0.0
        )
        signal_confidence = (
            median(self._signal_evidence) if self._signal_evidence else 1.0
        )
        confidence = (
            0.50 * timing_confidence
            + 0.30 * known_confidence
            + 0.20 * signal_confidence
        )
        tokens = [token.strip(".,!?-/") for token in text.split()]
        callsigns = [token for token in tokens if CALLSIGN_TOKEN.fullmatch(token)]
        # Many fox beacons bookend their payload with the station callsign. If
        # two callsign-shaped tokens disagree, the decoder has direct internal
        # evidence that at least one is wrong. Do not present either as fact.
        if len(callsigns) >= 2 and callsigns[0] != callsigns[-1]:
            confidence *= 0.70
        self.last_attempt_text = text
        self.last_attempt_confidence = confidence
        self.last_attempt_timing_confidence = timing_confidence
        self.last_attempt_signal_confidence = signal_confidence
        self.last_attempt_known_confidence = known_confidence
        self._marks.clear()
        self._gaps.clear()
        self._signal_evidence.clear()
        # A valid Morse lookup is not sufficient evidence.  Ambiguous timing
        # is withheld here rather than reported as a false callsign at 100%.
        rejection_reasons: list[str] = []
        if useful < 4:
            rejection_reasons.append("too-short")
        if known_confidence < 0.75:
            rejection_reasons.append("unknown-patterns")
        if confidence < 0.78:
            rejection_reasons.append("low-confidence")
        self.last_attempt_rejection = ",".join(rejection_reasons) or None
        if rejection_reasons:
            return None
        # A rejected/noisy candidate must never retrain the persistent speed
        # model. Earlier builds updated this value before the quality gate, so
        # repeated garbage could walk a 13 WPM decoder down to about 6 WPM and
        # eventually suppress every real beacon dot. Whole-message fitting
        # handles abrupt valid speed changes; retain timing only from a
        # candidate that has actually passed every quality check.
        # A syntactically valid candidate can still be a wrong-speed decode.
        # The connected 13 WPM beacon produced seven different, mostly-known
        # strings with perfect tone evidence but only 0.62 timing confidence;
        # accepting the first one as a speed teacher walked the persistent
        # model to about 21 WPM.  Keep such candidates for repeat consensus,
        # but retrain speed only from a decisively timed reception.  Clean
        # abrupt 20 WPM acquisition remains above this gate in the IQ suite.
        if timing_confidence >= 0.80:
            self.unit_seconds = self.unit_seconds * 0.25 + unit * 0.75
        return DecodedMessage(
            text=text,
            confidence=confidence,
            timing_confidence=timing_confidence,
            signal_confidence=signal_confidence,
        )

    def feed(
        self,
        tone: bool,
        duration_seconds: float,
        evidence: float = 1.0,
        carrier_active: bool | None = None,
    ) -> list[DecodedMessage]:
        if duration_seconds <= 0.0:
            return []
        messages: list[DecodedMessage] = []
        if tone != self.tone:
            prior = self.elapsed
            if self.tone:
                # Absolute 12 ms rejection catches receiver clicks without
                # discarding real high-speed Morse dots.
                if prior >= 0.012:
                    self._marks.append(prior)
            elif self._marks and prior >= 0.012:
                self._gaps.append(prior)
            self.tone = tone
            self.elapsed = 0.0
        self.elapsed += duration_seconds
        if tone:
            self._signal_evidence.append(max(0.0, min(1.0, evidence)))

        if not self.tone:
            ordinary_timeout = max(1.0, self.unit_seconds * 10.0)
            fallback_timeout = max(5.0, self.unit_seconds * 40.0)
            should_finish = self.elapsed >= fallback_timeout or (
                carrier_active is not True and self.elapsed >= ordinary_timeout
            )
            if self._marks and should_finish:
                message = self._finish_message()
                if message is not None:
                    messages.append(message)
        return messages


class NfmMorseDecoder:
    """Detect an audio tone in offset-tuned RTL IQ and decode its Morse timing.

    The detector samples phase differences at about 16 kHz. The known tuner
    offset is removed before phase extraction, so no full-rate complex mixer or
    PCM transport is required. Twenty-millisecond Goertzel windows recognize
    the configured tone while the timing decoder adapts to practical Morse
    speeds around its 13 WPM starting point.
    """

    # Preserve enough samples per 800 Hz tone cycle for stable 20 ms Goertzel
    # edges. Continuous SDR reads now run in their own thread, so this
    # higher-fidelity rate no longer pauses USB collection between blocks.
    AUDIO_RATE_HZ = 16_000
    WINDOW_SECONDS = 0.020
    ATTACK_WINDOWS = 2
    RELEASE_WINDOWS = 2

    def __init__(self, tone_hz: float = 800.0) -> None:
        self.tone_hz = tone_hz
        self.timing = MorseTimingDecoder()
        self.reset()

    def reset(self) -> None:
        self.timing.reset()
        self._configuration: tuple[int, int, int] | None = None
        self._stride = 1
        self._pick_offset = 0
        self._previous: tuple[float, float] | None = None
        self._correction_cos = 1.0
        self._correction_sin = 0.0
        self._audio_rate_hz = float(self.AUDIO_RATE_HZ)
        self._window_samples = max(16, round(self.AUDIO_RATE_HZ * self.WINDOW_SECONDS))
        self._audio: list[float] = []
        self._candidate = False
        self._candidate_windows = 0
        self._candidate_duration_seconds = 0.0
        self._candidate_evidence: list[float] = []
        self._stable_tone = False
        self.detected_tone_hz = self.tone_hz

    def _configure(
        self,
        sample_rate_hz: int,
        tuner_center_hz: int,
        target_center_hz: int,
    ) -> None:
        configuration = (sample_rate_hz, tuner_center_hz, target_center_hz)
        if configuration == self._configuration:
            return
        self.reset()
        self._configuration = configuration
        self._stride = max(1, round(sample_rate_hz / self.AUDIO_RATE_HZ))
        self._audio_rate_hz = sample_rate_hz / self._stride
        self._window_samples = max(
            16, round(self._audio_rate_hz * self.WINDOW_SECONDS)
        )
        expected_phase = (
            2.0
            * math.pi
            * (target_center_hz - tuner_center_hz)
            * self._stride
            / sample_rate_hz
        )
        self._correction_cos = math.cos(expected_phase)
        self._correction_sin = math.sin(expected_phase)

    @staticmethod
    def _goertzel(values: list[float], frequency_hz: float, rate_hz: float) -> float:
        omega = 2.0 * math.pi * frequency_hz / rate_hz
        coefficient = 2.0 * math.cos(omega)
        previous = 0.0
        previous_two = 0.0
        for value in values:
            current = value + coefficient * previous - previous_two
            previous_two = previous
            previous = current
        return max(
            0.0,
            previous_two * previous_two
            + previous * previous
            - coefficient * previous * previous_two,
        )

    def _window_tone_evidence(self, values: list[float]) -> tuple[bool, float]:
        mean = sum(values) / len(values)
        centered = [value - mean for value in values]
        total = sum(value * value for value in centered)
        if total / len(centered) < 1e-5:
            return False, 0.0
        # Beacon audio pitch is not standardized. Search a bounded range around
        # the configured preference instead of silently losing mark fragments
        # when a transmitter uses (for example) 650 or 1,000 Hz. Fifty-hertz
        # bins match the resolution of each 20 ms window.
        low_hz = max(350, round((self.tone_hz - 350.0) / 50.0) * 50)
        high_hz = min(1_400, round((self.tone_hz + 350.0) / 50.0) * 50)
        frequencies = [
            float(value) for value in range(int(low_hz), int(high_hz) + 1, 50)
        ]
        powers = {
            frequency: self._goertzel(centered, frequency, self._audio_rate_hz)
            for frequency in frequencies
        }
        peak_frequency = max(powers, key=powers.get)
        target = powers[peak_frequency]
        competitors = [
            power
            for frequency, power in powers.items()
            if abs(frequency - peak_frequency) >= 150.0
        ]
        competing_power = max(competitors, default=1e-12)
        normalized = target / max(1e-12, total * len(centered) / 2.0)
        prominence = target / max(1e-12, competing_power)
        # Schmitt thresholds prevent a slightly fading CW tone from being
        # chopped into extra dots while still requiring strong evidence to
        # begin a mark.  The continuous score is carried into message quality;
        # a barely accepted tone can no longer yield a 100%-certain decode.
        if self._stable_tone:
            detected = normalized >= 0.28 and prominence >= 2.2
        else:
            detected = normalized >= 0.50 and prominence >= 4.0
        if detected:
            self.detected_tone_hz = (
                self.detected_tone_hz * 0.75 + peak_frequency * 0.25
            )
        evidence = min(1.0, normalized / 0.70, prominence / 6.0)
        return detected, max(0.0, evidence)

    def _window_has_tone(self, values: list[float]) -> bool:
        return self._window_tone_evidence(values)[0]

    def _feed_tone_window(
        self,
        raw_tone: bool,
        evidence: float = 1.0,
        carrier_active: bool | None = None,
    ) -> list[DecodedMessage]:
        if raw_tone == self._stable_tone:
            # A provisional opposite state that vanishes before its debounce
            # threshold was a detector click/dropout. Assign those buffered
            # windows back to the stable state, together with this window,
            # instead of exposing a false 20/40 ms Morse run.
            duration = self.WINDOW_SECONDS
            if self._candidate != self._stable_tone:
                duration += self._candidate_duration_seconds
            self._candidate = self._stable_tone
            self._candidate_windows = 0
            self._candidate_duration_seconds = 0.0
            self._candidate_evidence.clear()
            return self.timing.feed(
                self._stable_tone,
                duration,
                evidence=evidence if self._stable_tone else 1.0,
                carrier_active=carrier_active,
            )

        if raw_tone == self._candidate:
            self._candidate_windows += 1
            self._candidate_duration_seconds += self.WINDOW_SECONDS
            self._candidate_evidence.append(evidence)
        else:
            self._candidate = raw_tone
            self._candidate_windows = 1
            self._candidate_duration_seconds = self.WINDOW_SECONDS
            self._candidate_evidence = [evidence]
        required = self.ATTACK_WINDOWS if raw_tone else self.RELEASE_WINDOWS
        if self._candidate_windows < required:
            return []

        # The candidate is now real. Feed its complete buffered duration to
        # the new state; the old implementation repeatedly fed those windows
        # to the prior state while waiting, systematically distorting both
        # marks and gaps. Two-window release preserves the connected
        # receiver's shortest real 60 ms separators. A two-window (40 ms)
        # fade inside a dash is accepted here and then safely rejoined by
        # MorseTimingDecoder._clean_runs, whose established 13 WPM threshold
        # is deliberately above 40 ms and below 60 ms.
        duration = self._candidate_duration_seconds
        candidate_evidence = (
            median(self._candidate_evidence)
            if self._candidate_evidence
            else evidence
        )
        self._stable_tone = raw_tone
        self._candidate_windows = 0
        self._candidate_duration_seconds = 0.0
        self._candidate_evidence.clear()
        return self.timing.feed(
            self._stable_tone,
            duration,
            evidence=candidate_evidence if self._stable_tone else 1.0,
            carrier_active=carrier_active,
        )

    def feed_iq(
        self,
        data: bytes,
        sample_rate_hz: int,
        tuner_center_hz: int,
        target_center_hz: int,
        carrier_active: bool | None = None,
    ) -> list[DecodedMessage]:
        self._configure(sample_rate_hz, tuner_center_hz, target_center_hz)
        sample_count = len(data) // 2
        messages: list[DecodedMessage] = []
        for index in range(self._pick_offset, sample_count, self._stride):
            current = (
                float(data[index * 2]) - 127.5,
                float(data[index * 2 + 1]) - 127.5,
            )
            if self._previous is not None:
                previous_i, previous_q = self._previous
                current_i, current_q = current
                real = current_i * previous_i + current_q * previous_q
                imaginary = current_q * previous_i - current_i * previous_q
                corrected_real = (
                    real * self._correction_cos
                    + imaginary * self._correction_sin
                )
                corrected_imaginary = (
                    imaginary * self._correction_cos
                    - real * self._correction_sin
                )
                self._audio.append(math.atan2(corrected_imaginary, corrected_real))
            self._previous = current
        self._pick_offset = (self._pick_offset - sample_count) % self._stride

        while len(self._audio) >= self._window_samples:
            window = self._audio[: self._window_samples]
            del self._audio[: self._window_samples]
            tone, evidence = self._window_tone_evidence(window)
            messages.extend(
                self._feed_tone_window(tone, evidence, carrier_active=carrier_active)
            )
        return messages
