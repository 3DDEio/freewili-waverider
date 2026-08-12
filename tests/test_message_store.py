from __future__ import annotations

from freewili_foxhunt.store import MessageStore


def test_message_store_persists_observations_and_repeat_metadata(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = store.load_or_empty()

    record = store.observe(
        records,
        text="KO6FQY JOIN NORCALCYBER.IO! KO6FQY",
        frequency_hz=147_500_000,
        confidence=0.96,
        observed_unix=1_800_000_000.0,
    )

    assert record.repeat_count == 1
    assert store.load() == records
    assert store.path.read_text().endswith("\n")


def test_message_store_coalesces_similar_repeats_and_fills_erasures(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    store.observe(
        records,
        text="KO6FQY JOIN NORCAL?YBER.IO! KO6FQY",
        frequency_hz=147_500_000,
        confidence=0.88,
        observed_unix=100.0,
    )

    record = store.observe(
        records,
        text="KO6FQY JOIN NORCALCYBER.IO! KO6FQY",
        frequency_hz=147_500_000,
        confidence=1.0,
        observed_unix=110.0,
    )

    assert len(records) == 1
    assert record.text == "KO6FQY JOIN NORCALCYBER.IO! KO6FQY"
    assert record.repeat_count == 2
    assert record.first_seen_unix == 100.0
    assert record.last_seen_unix == 110.0
    assert record.confidence == 1.0


def test_message_store_keeps_different_messages_or_frequencies_separate(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    for frequency_hz, text in (
        (147_500_000, "KO6FQY FIRST BEACON"),
        (147_500_000, "W6ABC DIFFERENT CONTENT"),
        (446_100_000, "KO6FQY FIRST BEACON"),
    ):
        store.observe(
            records,
            text=text,
            frequency_hz=frequency_hz,
            confidence=1.0,
            observed_unix=float(len(records) + 1),
        )

    assert [(item.frequency_hz, item.text) for item in records] == [
        (147_500_000, "KO6FQY FIRST BEACON"),
        (147_500_000, "W6ABC DIFFERENT CONTENT"),
        (446_100_000, "KO6FQY FIRST BEACON"),
    ]


def test_message_store_consolidates_recent_similar_beacon_variants(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    for offset, text in enumerate(
        (
            "TTMNIFQY JOIN NORCADCYBES?TIO! KO6FQY",
            "MODEFOY JOEN NORTNALCYBER.IO! KMDEFQY",
            "KO6FQY JOEN NORCALCYNEERAKIO! KONIFQY",
        )
    ):
        record = store.observe(
            records,
            text=text,
            frequency_hz=147_495_000,
            confidence=0.97 + offset * 0.01,
            observed_unix=100.0 + offset,
        )

    assert len(records) == 1
    assert record.repeat_count == 3
    assert record.variants is not None
    assert len(record.variants) == 3


def test_message_store_weights_repeated_receptions_and_requires_verification(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    variants = (
        "KO6FQY JOIN NORCALCYBER.IO! KO6FQY",
        "KO6FQY JOIN NORCALCY?ER.IO! KO6FQY",
        "KO6FQY JOIN NORCALCYBER.IO! KO6FQY",
    )

    for index, text in enumerate(variants):
        record = store.observe(
            records,
            text=text,
            frequency_hz=147_500_000,
            confidence=0.92,
            observed_unix=100.0 + index,
        )
        if index < 2:
            assert not record.verified

    assert record.verified
    assert record.text == "KO6FQY JOIN NORCALCYBER.IO! KO6FQY"
    assert record.evidence_count == 3
    assert record.variant_counts is not None
    assert record.variant_counts[variants[0]] == 2
    assert record.display_confidence >= 0.9


def test_message_store_bounds_history_to_latest_one_hundred(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    for index in range(105):
        store.observe(
            records,
            text=f"BEACON MESSAGE {index:03d}",
            frequency_hz=147_000_000 + index * 1_000,
            confidence=1.0,
            observed_unix=float(index),
        )

    assert len(records) == 100
    assert records[0].text == "BEACON MESSAGE 005"
    assert records[-1].text == "BEACON MESSAGE 104"


def test_message_store_clear_removes_memory_and_persisted_candidates(tmp_path):
    store = MessageStore(tmp_path / "messages.json")
    records = []
    store.observe(
        records,
        text="UNVERIFIED CANDIDATE",
        frequency_hz=147_500_000,
        confidence=0.75,
        observed_unix=100.0,
    )

    store.clear(records)

    assert records == []
    assert store.load() == []
