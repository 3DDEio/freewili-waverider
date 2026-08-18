import hashlib
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"
LIMITATIONS = ROOT / "docs" / "LIMITATIONS.md"
USER_GUIDE = ROOT / "docs" / "USER_GUIDE.md"
LICENSES = ROOT / "LICENSES.md"


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


def test_share_alike_licenses_are_visible():
    licenses = LICENSES.read_text()
    assert "GPL-3.0-or-later" in licenses
    assert "CC BY-SA 4.0" in licenses
    assert (ROOT / "LICENSE").read_text().startswith("                    GNU GENERAL PUBLIC LICENSE")
    assert (ROOT / "LICENSES" / "CC-BY-SA-4.0.txt").is_file()


def test_native_release_products_are_generated_and_ignored():
    tracked = subprocess.run(
        ["git", "ls-files", "native/dist"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert tracked == ""
    ignored = subprocess.run(
        ["git", "check-ignore", "native/dist/WaveRider.uf2"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert ignored.strip() == "native/dist/WaveRider.uf2"


def test_quick_start_and_native_metadata_match_the_radio_menu_contract():
    readme = README.read_text()
    guide = USER_GUIDE.read_text()
    display_cmake = (
        ROOT / "native" / "waverider_display" / "CMakeLists.txt"
    ).read_text()
    installer = (
        ROOT / "native" / "waverider_installer" / "main.c"
    ).read_text()

    assert "git clone --recurse-submodules https://github.com/3DDEio/freewili-waverider.git" in readme
    assert "Apps → Radio → WaveRider" in readme
    assert "Apps → Radio → WaveRider" in guide
    assert 'NAME "WaveRider"' in display_cmake
    assert 'REPOSITORY "https://github.com/3DDEio/freewili-waverider"' in display_cmake
    assert '#define APP_DIR  "/apps/Radio"' in installer
    assert 'APP_PATH APP_DIR "/WaveRider.uf2"' in installer
    assert 'OLD_RADIO_APP_PATH APP_DIR "/waverider_display.uf2"' in installer
    assert 'LEGACY_APP_DIR "/apps/waverider"' in installer
    assert 'LEGACY_APP_PATH "/apps/waverider/waverider_display.uf2"' in installer
    assert 'APP_STAGE APP_DIR "/WaveRider.new"' in installer
    assert 'APP_BACKUP APPDATA_APP_DIR "/waverider_display.previous.uf2"' in installer
    assert "content mismatch" in installer
    assert "recover_interrupted_upgrade" in installer
    assert "completed interrupted first install" in installer
    assert "restored interrupted upgrade backup" in installer
    assert installer.index("promote_staged_payload()") < installer.index(
        "preserve_or_remove_old_radio_app()"
    )
    assert "count.entries != 0u" in installer
    assert installer.index("ow_sd_list(&s_dev, LEGACY_APP_DIR") < installer.index(
        "ow_sd_remove(&s_dev, LEGACY_APP_DIR)"
    )


def test_release_installation_leads_with_the_one_click_flow():
    readme = README.read_text()
    installation = (ROOT / "docs" / "INSTALLATION.md").read_text()

    assert "installer/Run WaveRider Installer.command" in readme
    assert "installer/Run WaveRider Installer.cmd" in readme
    assert "installer/run-waverider-installer.sh" in readme
    assert "click **Install WaveRider** once" in readme
    assert "does not replace the stock Main or Display firmware" in installation
    assert "physical acceptance runs remain open" in installation


def test_vendor_source_and_release_workflow_are_pinned_and_fail_closed():
    gitmodules = (ROOT / ".gitmodules").read_text()
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()

    assert "github.com/freewili/wilibsp" in gitmodules
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in release
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in release
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in release
    assert "LICENSES/ONEWILI-REDISTRIBUTION.txt" in release
    assert "native/dist/WaveRider.uf2" in release
    assert "native/dist/waverider_installer.uf2" in release
    assert "setup-native-ci-linux.sh" in release
    assert 'native_build="$GITHUB_WORKSPACE/build/release-native"' in release
    assert 'rm -rf "$native_build"' in release
    assert release.count('BUILD_DIR="$native_build" sh deploy/build-native-apps.sh') == 2
    assert 'cmp "build/native-reference/$artifact" "native/dist/$artifact"' in release
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in release
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in ci
    assert "attestations: write" in release
    assert "id-token: write" in release
    assert "build-source-release.sh" in release
    assert "freewili-waverider-source-*.tar.gz.sha256" in release
    assert "Do not publish a supported binary release" in " ".join(notices.split())


def test_exact_debian_source_and_runtime_license_notices_are_bundled():
    source = ROOT / "vendor" / "debian-source" / "rtl-sdr-2.0.2-2"
    for filename in (
        "rtl-sdr_2.0.2-2.dsc",
        "rtl-sdr_2.0.2.orig.tar.xz",
        "rtl-sdr_2.0.2-2.debian.tar.xz",
        "SHA256SUMS",
        "README.md",
    ):
        assert (source / filename).is_file(), filename
    for filename in (
        "WILIBSP-MIT.txt",
        "PICO-SDK-BSD-3-CLAUSE.txt",
        "PICO-PIO-USB-MIT.txt",
        "TUSB-XINPUT-MIT.txt",
        "TINYUSB-MIT.txt",
        "FATFS.txt",
        "SEGGER-RTT.txt",
    ):
        assert (ROOT / "LICENSES" / filename).is_file(), filename


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


def test_public_release_archive_contains_generated_products_without_repo_clutter():
    native_dist = ROOT / "native" / "dist"
    native_dist.mkdir(parents=True, exist_ok=True)
    products = (
        "waverider_display.elf",
        "WaveRider.uf2",
        "waverider_installer.elf",
        "waverider_installer.uf2",
    )
    try:
        sums = []
        for name in products:
            payload = f"generated test product: {name}\n".encode()
            (native_dist / name).write_bytes(payload)
            sums.append(f"{hashlib.sha256(payload).hexdigest()}  native/dist/{name}\n")
        (native_dist / "SHA256SUMS").write_text("".join(sums))

        subprocess.run(["sh", "deploy/build-release.sh"], cwd=ROOT, check=True)
        archive = ROOT / "dist" / "freewili-foxhunt-0.1.0.tar.gz"
        with tarfile.open(archive, mode="r:gz") as bundle:
            names = set(bundle.getnames())
        prefix = "freewili-foxhunt-0.1.0/"
        assert prefix + "tools/fw2_install_native_app.py" in names
        assert prefix + "installer/waverider_installer.py" in names
        assert prefix + "installer/device_install.py" in names
        assert prefix + "installer/Run WaveRider Installer.command" in names
        assert prefix + "installer/Run WaveRider Installer.cmd" in names
        assert prefix + "tools/prepare_wilibsp.py" in names
        assert prefix + "vendor/debian-source/rtl-sdr-2.0.2-2/rtl-sdr_2.0.2-2.dsc" in names
        assert prefix + "native/dist/WaveRider.uf2" in names
        assert prefix + "native/dist/waverider_installer.elf" in names
        assert prefix + "deploy/setup-native-ci-linux.sh" not in names
        assert prefix + "HISTORY.md" not in names
        assert not any("research/" in name for name in names)
        assert not any("test-beacon/" in name for name in names)
        assert not any(".egg-info/" in name for name in names)
    finally:
        for name in (*products, "SHA256SUMS"):
            (native_dist / name).unlink(missing_ok=True)


def test_project_source_archive_fetches_pinned_vendor_source_instead_of_copying_it():
    before_wilibsp = subprocess.run(
        ["git", "-C", "wilibsp", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    before_onewili = subprocess.run(
        ["git", "-C", "wilibsp/libs/onewili", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    subprocess.run(["sh", "deploy/build-source-release.sh"], cwd=ROOT, check=True)
    archive = ROOT / "dist" / "freewili-waverider-source-0.1.0.tar.gz"
    with tarfile.open(archive, mode="r:gz") as bundle:
        names = set(bundle.getnames())
    prefix = "freewili-waverider-source-0.1.0/"
    assert prefix + "CMakeLists.txt" in names
    assert prefix + "tools/prepare_wilibsp.py" in names
    assert prefix + "native/patches/wilibsp-waverider.patch" in names
    assert prefix + "tools/fetch_native_dependencies.py" in names
    assert prefix + "wilibsp/LICENSE" not in names
    assert prefix + "wilibsp/bsp/CMakeLists.txt" not in names
    assert prefix + "wilibsp/libs/onewili/include/onewili.h" not in names
    assert prefix + ".waverider-native-source.json" not in names
    assert prefix + "HISTORY.md" not in names
    assert not any("native/dist/" in name for name in names)
    assert not any("research/" in name for name in names)
    assert not any("test-beacon/" in name for name in names)
    assert subprocess.run(
        ["git", "-C", "wilibsp", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout == before_wilibsp
    assert subprocess.run(
        ["git", "-C", "wilibsp/libs/onewili", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout == before_onewili
