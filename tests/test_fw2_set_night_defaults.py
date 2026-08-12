from tools import fw2_set_night_defaults


def test_v07_cli_is_fail_closed(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["fw2_set_night_defaults.py", "--method", "v07-debug", "--dry-run"],
    )

    assert fw2_set_night_defaults.main() == 2
    assert "disabled" in capsys.readouterr().out


class TranscriptPort:
    def __init__(self, responses):
        self.responses = [value.encode() for value in responses]
        self.current = b""
        self.writes = []

    def write(self, value):
        self.writes.append(value)
        self.current = self.responses.pop(0)

    def flush(self):
        return None

    def read(self, _count):
        value, self.current = self.current, b""
        return value


def _clock():
    value = -0.01

    def tick():
        nonlocal value
        value += 0.01
        return value

    return tick


def test_night_defaults_require_verified_menus_and_save_startup(monkeypatch):
    monkeypatch.setattr(fw2_set_night_defaults.time, "monotonic", _clock())
    port = TranscriptPort(
        [
            "Configure Sound\nEnter Letter:",
            "Speaker Volume Enter Number:",
            "Configure Sound\nSpeaker Volume [0]\nSys Sounds [default]",
            "System Sounds Enter Number:",
            "Configure Sound\nSpeaker Volume [0]\nSys Sounds [off]",
            "Settings\nConfigure Light Show",
            "Configure Light Show\nDefault Light Show [7]",
            "Default Light Show Enter Number:",
            "Configure Light Show\nDefault Light Show [manual]",
            "Settings\nSave Settings as Startup",
            "Saving settings to settings.txt...\nDone!",
        ]
    )

    fw2_set_night_defaults.apply_night_defaults(port, delay=0)

    assert port.writes == [
        b"g\n",
        b"v\n",
        b"0\n",
        b"p\n",
        b"0\n",
        b"q\n",
        b"f\n",
        b"c\n",
        b"0\n",
        b"q\n",
        b"s\n",
    ]


def test_night_defaults_abort_before_later_changes_on_unexpected_menu(monkeypatch):
    monkeypatch.setattr(fw2_set_night_defaults.time, "monotonic", _clock())
    port = TranscriptPort(["Wrong menu"])

    try:
        fw2_set_night_defaults.apply_night_defaults(port, delay=0)
    except RuntimeError as error:
        assert "Configure Sound" in str(error)
    else:
        raise AssertionError("expected fail-closed menu validation")

    assert port.writes == [b"g\n"]


def test_merge_settings_preserves_unrelated_values_and_removes_duplicates():
    result = fw2_set_night_defaults.merge_settings(
        "theme=night\nsndvol=7\nunknown=yes\nsndsys=1\nsndvol=4\n"
    )

    assert result == (
        "theme=night\n"
        "sndvol=0\n"
        "unknown=yes\n"
        "sndsys=0\n"
        "lshowdef=0\n"
    )


def test_update_settings_image_preserves_other_files_and_unrelated_settings():
    LittleFS, UserContext = fw2_set_night_defaults._littlefs_types()
    context = UserContext(buffsize=fw2_set_night_defaults.LITTLEFS_SIZE)
    filesystem = LittleFS(
        context=context,
        mount=False,
        **fw2_set_night_defaults.LFS_KWARGS,
    )
    filesystem.format()
    filesystem.mount()
    with filesystem.open("/settings.txt", "w") as settings_file:
        settings_file.write("theme=night\nsndvol=9\n")
    with filesystem.open("/keep.txt", "w") as keep_file:
        keep_file.write("untouched")
    filesystem.unmount()

    updated = fw2_set_night_defaults.update_settings_image(bytes(context.buffer))
    files, settings = fw2_set_night_defaults.read_settings_image(updated)

    assert files == ["keep.txt", "settings.txt"]
    assert "theme=night" in settings
    fw2_set_night_defaults.require_night_settings(settings)
    context = UserContext(buffer=bytearray(updated))
    filesystem = LittleFS(context=context, **fw2_set_night_defaults.LFS_KWARGS)
    try:
        with filesystem.open("/keep.txt", "r") as keep_file:
            assert keep_file.read() == "untouched"
    finally:
        filesystem.unmount()


def test_changed_blocks_returns_only_modified_sectors():
    before = bytes(fw2_set_night_defaults.BLOCK_SIZE * 3)
    after = bytearray(before)
    after[fw2_set_night_defaults.BLOCK_SIZE + 12] = 1

    assert fw2_set_night_defaults.changed_blocks(before, bytes(after)) == [1]


def test_update_settings_image_is_byte_identical_when_already_set():
    LittleFS, UserContext = fw2_set_night_defaults._littlefs_types()
    context = UserContext(buffsize=fw2_set_night_defaults.LITTLEFS_SIZE)
    filesystem = LittleFS(
        context=context,
        mount=False,
        **fw2_set_night_defaults.LFS_KWARGS,
    )
    filesystem.format()
    filesystem.mount()
    with filesystem.open("/settings.txt", "w") as settings_file:
        settings_file.write("sndvol=0\nsndsys=0\nlshowdef=0\n")
    filesystem.unmount()
    before = bytes(context.buffer)

    assert fw2_set_night_defaults.update_settings_image(before) == before
