from pathlib import Path


ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"
LIMITATIONS = ROOT / "docs" / "LIMITATIONS.md"
USER_GUIDE = ROOT / "docs" / "USER_GUIDE.md"
LICENSES = ROOT / "LICENSES.md"
HISTORY = ROOT / "HISTORY.md"


def test_readme_keeps_field_limits_visible_before_installation():
    readme = README.read_text()

    limitations_heading = readme.index("## Important current limitations")
    install_heading = readme.index("## Install from a release")

    assert limitations_heading < install_heading
    assert "16 frequencies in the Live hunt list" in readme
    assert "100 additional values" in readme
    assert "No received audio yet" in readme
    assert "Relative RSSI, not calibrated dBm" in readme
    assert "Receive only" in readme
    assert "docs/LIMITATIONS.md" in readme
    assert "docs/USER_GUIDE.md" in readme


def test_limit_register_explains_the_current_frequency_cap():
    limitations = LIMITATIONS.read_text()

    assert "## Live list: 16 frequencies maximum" in limitations
    assert "## Saved library: 100 frequencies maximum" in limitations
    assert "32 named app-signal mailbox slots" in limitations
    assert "User impact" in limitations
    assert "Current workaround" in limitations
    assert "Future direction" in limitations


def test_user_guide_preserves_the_physically_validated_button_map():
    guide = USER_GUIDE.read_text()

    for row in (
        "| Gray | Open Lists frequency management |",
        "| Yellow | Open decoded-message history |",
        "| Green | Tune the next frequency |",
        "| Blue | Tune the previous frequency |",
        "| Red | Refresh receiver health and restart SDR collection |",
    ):
        assert row in guide
    assert "Live remains limited to 16" in guide
    assert "open a frequency summary" in guide
    assert "permanently removes every verified message" in guide
    assert "hidden candidate" in guide
    assert "`433200`" in guide
    assert "tap the `sdr live` label" in guide.lower()
    assert "press Red **Refresh**" in guide
    assert "**Waterfall Span**" in guide
    assert "25 kHz, 100 kHz, 200 kHz" in guide
    assert "immediately retunes the SDR" in guide


def test_public_repository_governance_files_are_present():
    for path in (
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / ".github" / "CODEOWNERS",
        ROOT / ".github" / "pull_request_template.md",
    ):
        assert path.is_file(), path


def test_public_history_is_explicitly_reconstructed():
    history = HISTORY.read_text().lower()
    assert "reconstructed" in history
    assert "not" in history and "commit history" in history


def test_share_alike_licenses_are_visible():
    licenses = LICENSES.read_text()
    assert "GPL-3.0-or-later" in licenses
    assert "CC BY-SA 4.0" in licenses
    assert (ROOT / "LICENSE").read_text().startswith("                    GNU GENERAL PUBLIC LICENSE")
    assert (ROOT / "LICENSES" / "CC-BY-SA-4.0.txt").is_file()


def test_native_release_artifacts_have_pinned_checksums():
    sums = (ROOT / "native" / "dist" / "SHA256SUMS").read_text()
    for artifact in (
        "waverider_display.elf",
        "waverider_display.uf2",
        "waverider_installer.elf",
        "waverider_installer.uf2",
    ):
        assert artifact in sums

    display = (ROOT / "native" / "dist" / "waverider_display.uf2").read_bytes()
    installer = (ROOT / "native" / "dist" / "waverider_installer.elf").read_bytes()
    assert b"WaveRider" in display
    assert b"3DDEio/freewili-waverider" in display
    assert b"/apps/Radio/waverider_display.uf2" in installer
    assert b"/apps/waverider/waverider_display.uf2" in installer


def test_quick_start_and_native_metadata_match_the_radio_menu_contract():
    readme = README.read_text()
    guide = USER_GUIDE.read_text()
    display_cmake = (
        ROOT / "native" / "waverider_display" / "CMakeLists.txt"
    ).read_text()
    installer = (
        ROOT / "native" / "waverider_installer" / "main.c"
    ).read_text()

    assert "git clone https://github.com/3DDEio/freewili-waverider.git" in readme
    assert "Apps → Radio → WaveRider" in readme
    assert "Apps → Radio → WaveRider" in guide
    assert 'NAME "WaveRider"' in display_cmake
    assert 'REPOSITORY "https://github.com/3DDEio/freewili-waverider"' in display_cmake
    assert '#define APP_DIR  "/apps/Radio"' in installer
    assert 'LEGACY_APP_PATH "/apps/waverider/waverider_display.uf2"' in installer
    assert installer.index("size != (uint32_t)waverider_payload_len") < installer.index(
        "ow_sd_remove(&s_dev, LEGACY_APP_PATH)"
    )


def test_documentation_index_only_links_to_present_local_files():
    index = ROOT / "docs" / "README.md"
    linked = []
    for line in index.read_text().splitlines():
        if "](" not in line:
            continue
        target = line.split("](", 1)[1].split(")", 1)[0]
        if "://" not in target:
            linked.append((index.parent / target).resolve())

    assert linked
    assert all(path.is_file() for path in linked)
