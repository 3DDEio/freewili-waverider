from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.store import FrequencyLibraryStore


def test_library_seeds_unique_saved_frequencies_and_round_trips(tmp_path):
    lists = [
        FrequencyList(
            "First",
            [
                FrequencyEntry(147_495_000, "Fox"),
                FrequencyEntry(433_200_000, "UHF"),
            ],
        ),
        FrequencyList(
            "Second",
            [
                FrequencyEntry(147_495_000, "Duplicate"),
                FrequencyEntry(446_125_000, "Backup"),
            ],
        ),
    ]
    store = FrequencyLibraryStore(tmp_path / "frequency-library.json")

    seeded = store.load_or_seed(lists)

    assert [entry.frequency_hz for entry in seeded] == [
        147_495_000,
        433_200_000,
        446_125_000,
    ]
    assert [entry.frequency_hz for entry in store.load()] == [
        147_495_000,
        433_200_000,
        446_125_000,
    ]


def test_library_rejects_duplicate_saved_frequencies(tmp_path):
    store = FrequencyLibraryStore(tmp_path / "frequency-library.json")
    entries = [
        FrequencyEntry(433_200_000, "One"),
        FrequencyEntry(433_200_000, "Two"),
    ]

    try:
        store.save(entries)
    except ValueError as error:
        assert "duplicates" in str(error)
    else:
        raise AssertionError("duplicate saved frequencies were accepted")
