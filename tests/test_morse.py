from __future__ import annotations

import math

from freewili_foxhunt.morse import MORSE_TO_TEXT, MorseTimingDecoder, NfmMorseDecoder


TEXT_TO_MORSE = {
    "K": "-.-",
    "O": "---",
    "6": "-....",
    "F": "..-.",
    "Q": "--.-",
    "Y": "-.--",
}


def feed_mark(decoder: MorseTimingDecoder, mark: str, unit: float) -> None:
    decoder.feed(True, unit if mark == "." else unit * 3)
    decoder.feed(False, unit)


def test_timing_decoder_decodes_callsign_and_waits_for_message_gap() -> None:
    decoder = MorseTimingDecoder(initial_wpm=13)
    unit = 1.2 / 13
    messages = []
    for character_index, character in enumerate("KO6FQY"):
        for mark in TEXT_TO_MORSE[character]:
            feed_mark(decoder, mark, unit)
        if character_index != 5:
            decoder.feed(False, unit * 2)
    messages.extend(decoder.feed(False, unit * 12))

    assert [message.text for message in messages] == ["KO6FQY"]
    assert messages[0].confidence == 1.0
    assert decoder.last_attempt_text == "KO6FQY"
    assert decoder.last_attempt_rejection is None


def test_timing_decoder_recovers_complete_configured_beacon_message() -> None:
    decoder = MorseTimingDecoder(initial_wpm=13)
    unit = 1.2 / 13
    text_to_morse = {character: pattern for pattern, character in MORSE_TO_TEXT.items()}
    words = "KO6FQY JOIN NORCALCYBER.IO! KO6FQY".split()

    for word_index, word in enumerate(words):
        for character_index, character in enumerate(word):
            for mark in text_to_morse[character]:
                feed_mark(decoder, mark, unit)
            if character_index != len(word) - 1:
                decoder.feed(False, unit * 2)
        if word_index != len(words) - 1:
            decoder.feed(False, unit * 6)

    messages = decoder.feed(False, unit * 11)

    assert [message.text for message in messages] == [
        "KO6FQY JOIN NORCALCYBER.IO! KO6FQY"
    ]
    assert messages[0].confidence == 1.0


def test_timing_decoder_resists_mark_jitter_and_one_long_outlier() -> None:
    decoder = MorseTimingDecoder(initial_wpm=13)
    unit = 1.2 / 13
    messages = []
    jitter = (0.82, 1.18, 0.91, 1.11, 0.87, 1.07)
    mark_index = 0
    for character_index, character in enumerate("KO6FQY"):
        for mark in TEXT_TO_MORSE[character]:
            duration = unit * (1 if mark == "." else 3) * jitter[mark_index % len(jitter)]
            # One stretched dash used to pull the exponential timing estimate
            # far enough to corrupt the characters after it.
            if mark_index == 3:
                duration *= 1.45
            decoder.feed(True, duration)
            decoder.feed(False, unit)
            mark_index += 1
        if character_index != 5:
            decoder.feed(False, unit * 2.1)
    messages.extend(decoder.feed(False, unit * 12))

    assert [message.text for message in messages] == ["KO6FQY"]
    assert 0.075 <= decoder.unit_seconds <= 0.11


def test_timing_decoder_fits_fast_beacon_before_classifying_first_letter() -> None:
    """A 20 WPM beacon must not be decoded using the 13 WPM startup guess."""

    decoder = MorseTimingDecoder(initial_wpm=13)
    unit = 1.2 / 20
    jitter = (0.91, 1.08, 0.96, 1.04, 0.89, 1.10)
    mark_index = 0
    for character_index, character in enumerate("KO6FQY"):
        for mark in TEXT_TO_MORSE[character]:
            duration = unit * (1 if mark == "." else 3) * jitter[mark_index % 6]
            decoder.feed(True, duration)
            decoder.feed(False, unit)
            mark_index += 1
        if character_index != 5:
            decoder.feed(False, unit * 2)

    messages = decoder.feed(False, 1.1)

    assert [message.text for message in messages] == ["KO6FQY"]
    assert messages[0].timing_confidence >= 0.85
    assert 0.05 <= decoder.unit_seconds <= 0.075


def test_timing_decoder_rejects_disagreeing_bookend_callsigns() -> None:
    decoder = MorseTimingDecoder(initial_wpm=20)
    unit = 1.2 / 20
    text_to_morse = {character: pattern for pattern, character in MORSE_TO_TEXT.items()}
    words = "KO6FQY TEST KO6FQO".split()
    for word_index, word in enumerate(words):
        for character_index, character in enumerate(word):
            for mark in text_to_morse[character]:
                feed_mark(decoder, mark, unit)
            if character_index != len(word) - 1:
                decoder.feed(False, unit * 2)
        if word_index != len(words) - 1:
            decoder.feed(False, unit * 6)

    assert decoder.feed(False, 1.1) == []


def test_timing_decoder_repairs_short_dropout_inside_dash() -> None:
    decoder = MorseTimingDecoder(initial_wpm=20)
    unit = 1.2 / 20
    for character_index, character in enumerate("KO6FQY"):
        for mark_index, mark in enumerate(TEXT_TO_MORSE[character]):
            if character_index == 0 and mark_index == 0:
                decoder.feed(True, unit * 1.35)
                decoder.feed(False, unit * 0.55)
                decoder.feed(True, unit * 1.35)
                decoder.feed(False, unit)
            else:
                feed_mark(decoder, mark, unit)
        if character_index != 5:
            decoder.feed(False, unit * 2)

    messages = decoder.feed(False, 1.3)

    assert [message.text for message in messages] == ["KO6FQY"]


def test_rejected_noise_cannot_retrain_decoder_to_impossible_slow_speed() -> None:
    decoder = MorseTimingDecoder(initial_wpm=13)
    initial_unit = decoder.unit_seconds

    # Six dashes without a character gap are not a valid Morse character. In
    # the field, repeated candidates like this previously updated the learned
    # unit before being rejected, compounding from 13 WPM to about 6 WPM.
    for _ in range(8):
        slower_unit = decoder.unit_seconds * 1.40
        decoder._marks = [slower_unit * 3.0] * 6
        decoder._gaps = [slower_unit] * 5
        decoder._signal_evidence = [0.1] * 6
        assert decoder._finish_message() is None

    assert decoder.unit_seconds == initial_unit
    assert MorseTimingDecoder.MIN_UNIT_SECONDS <= decoder.unit_seconds
    assert decoder.unit_seconds <= MorseTimingDecoder.MAX_UNIT_SECONDS
    assert decoder.last_attempt_text == "?"
    assert decoder.last_attempt_rejection == "too-short,unknown-patterns,low-confidence"


def fm_iq(
    states: list[tuple[bool, float]],
    *,
    sample_rate_hz: int = 240_000,
    carrier_offset_hz: float = -50_000.0,
    tone_hz: float = 800.0,
    deviation_hz: float = 2_000.0,
) -> bytes:
    samples = bytearray()
    phase = 0.0
    sample_index = 0
    for tone, duration in states:
        count = round(duration * sample_rate_hz)
        for _ in range(count):
            audio = (
                math.sin(2.0 * math.pi * tone_hz * sample_index / sample_rate_hz)
                if tone
                else 0.0
            )
            phase += 2.0 * math.pi * (
                carrier_offset_hz + deviation_hz * audio
            ) / sample_rate_hz
            samples.extend(
                (
                    round(127.5 + 90.0 * math.cos(phase)),
                    round(127.5 + 90.0 * math.sin(phase)),
                )
            )
            sample_index += 1
    return bytes(samples)


def test_nfm_decoder_recovers_morse_from_offset_tuned_iq() -> None:
    unit = 1.2 / 13
    states: list[tuple[bool, float]] = [(False, unit * 2)]
    for character_index, character in enumerate("KO6FQY"):
        for mark in TEXT_TO_MORSE[character]:
            states.append((True, unit if mark == "." else unit * 3))
            states.append((False, unit))
        if character_index != 5:
            states.append((False, unit * 2))
    states.append((False, unit * 12))

    decoder = NfmMorseDecoder(tone_hz=800.0)
    payload = fm_iq(states)
    messages = []
    block_bytes = 48_000
    for offset in range(0, len(payload), block_bytes):
        messages.extend(
            decoder.feed_iq(
                payload[offset : offset + block_bytes],
                240_000,
                147_550_000,
                147_500_000,
            )
        )

    assert [message.text for message in messages] == ["KO6FQY"]


def test_nfm_decoder_locks_to_beacon_tone_that_is_not_800_hz() -> None:
    unit = 1.2 / 20
    states: list[tuple[bool, float]] = [(False, unit * 2)]
    for character_index, character in enumerate("KO6FQY"):
        for mark in TEXT_TO_MORSE[character]:
            states.append((True, unit if mark == "." else unit * 3))
            states.append((False, unit))
        if character_index != 5:
            states.append((False, unit * 2))
    states.append((False, unit * 20))

    decoder = NfmMorseDecoder(tone_hz=800.0)
    payload = fm_iq(states, tone_hz=650.0)
    messages = []
    for offset in range(0, len(payload), 48_000):
        messages.extend(
            decoder.feed_iq(
                payload[offset : offset + 48_000],
                240_000,
                147_550_000,
                147_500_000,
            )
        )

    assert [message.text for message in messages] == ["KO6FQY"]
    assert abs(decoder.detected_tone_hz - 650.0) < 35.0


def test_nfm_decoder_rejects_unmodulated_carrier() -> None:
    decoder = NfmMorseDecoder()
    payload = fm_iq([(False, 2.0)])
    messages = decoder.feed_iq(
        payload,
        240_000,
        147_550_000,
        147_500_000,
    )
    assert messages == []
