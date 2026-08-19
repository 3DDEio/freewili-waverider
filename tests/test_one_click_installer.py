from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from installer import device_install


def test_verify_release_checksums_accepts_exact_artifacts(tmp_path):
    artifact = tmp_path / "native/dist/WaveRider.uf2"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"safe app")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (artifact.parent / "SHA256SUMS").write_text(
        f"{digest}  native/dist/WaveRider.uf2\n",
        encoding="utf-8",
    )

    device_install.verify_release_checksums(tmp_path)


def test_verify_release_checksums_rejects_tampering(tmp_path):
    artifact = tmp_path / "native/dist/WaveRider.uf2"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"changed")
    (artifact.parent / "SHA256SUMS").write_text(
        f"{'0' * 64}  native/dist/WaveRider.uf2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        device_install.verify_release_checksums(tmp_path)


def test_find_main_ports_uses_only_fwfinder_serial_interfaces(monkeypatch):
    main = SimpleNamespace(kind="serial", name="Main USB", port="COM7")
    debug = SimpleNamespace(kind="debug", name="CMSIS-DAP", port="COM8")
    display = SimpleNamespace(kind="serial", name="Display USB", port="COM9")
    found = SimpleNamespace(
        serial="FX0177",
        device_type="fw2",
        usb_devices=[debug, display, main],
        get_main_usb_device=lambda: main,
    )
    monkeypatch.setitem(
        sys.modules,
        "pyfwfinder",
        SimpleNamespace(
            find_all=lambda: [found],
            FreeWili2="fw2",
            SerialMain="serial-main",
        ),
    )

    assert device_install.find_main_ports() == [
        ("FreeWili FX0177 — COM7", "COM7")
    ]


def test_find_main_ports_rejects_non_fw2_devices(monkeypatch):
    wrong = SimpleNamespace(
        serial="FW1",
        device_type="fw1",
        usb_devices=[],
        get_main_usb_device=lambda: (_ for _ in ()).throw(
            AssertionError("must not inspect a non-FW2 Main port")
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "pyfwfinder",
        SimpleNamespace(
            find_all=lambda: [wrong],
            FreeWili2="fw2",
            SerialMain="serial-main",
        ),
    )

    assert device_install.find_main_ports() == []


def test_install_native_via_sd_returns_control_to_main_on_failure(
    monkeypatch, tmp_path
):
    source = tmp_path / "WaveRider.uf2"
    source.write_bytes(b"placeholder")
    ownership: list[bool] = []
    monkeypatch.setattr(device_install, "inspect_display_uf2", lambda _path: "SRAM")
    monkeypatch.setattr(device_install, "_mounted_volumes", lambda: set())
    monkeypatch.setattr(
        device_install, "_set_sd_host", lambda _port, to_pc: ownership.append(to_pc)
    )
    monkeypatch.setattr(
        device_install,
        "_wait_for_sd",
        lambda _baseline, _timeout: (_ for _ in ()).throw(TimeoutError("no SD")),
    )
    monkeypatch.setattr(device_install.time, "sleep", lambda _seconds: None)

    with pytest.raises(device_install.DirectSdInstallError, match="no SD"):
        device_install.install_native_via_sd("COM7", source)

    assert ownership == [True, False]


def test_install_native_via_sd_stops_when_ownership_cannot_return(
    monkeypatch, tmp_path
):
    source = tmp_path / "WaveRider.uf2"
    source.write_bytes(b"placeholder")
    calls: list[bool] = []
    monkeypatch.setattr(device_install, "inspect_display_uf2", lambda _path: "SRAM")
    monkeypatch.setattr(device_install, "_mounted_volumes", lambda: set())

    def set_owner(_port, to_pc):
        calls.append(to_pc)
        if not to_pc:
            raise RuntimeError("serial route lost")

    monkeypatch.setattr(device_install, "_set_sd_host", set_owner)
    monkeypatch.setattr(
        device_install,
        "_wait_for_sd",
        lambda _baseline, _timeout: (_ for _ in ()).throw(TimeoutError("no SD")),
    )
    monkeypatch.setattr(device_install.time, "sleep", lambda _seconds: None)

    with pytest.raises(device_install.SdOwnershipError, match="restart"):
        device_install.install_native_via_sd("COM7", source)

    assert calls == [True, False]


def test_install_waverider_falls_back_to_volatile_installer(monkeypatch, tmp_path):
    events: list[str] = []
    monkeypatch.setattr(device_install, "verify_release_checksums", lambda _root: None)
    monkeypatch.setattr(
        device_install,
        "install_native_via_sd",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            device_install.DirectSdInstallError("no mount")
        ),
    )
    monkeypatch.setattr(
        device_install,
        "install_native_via_debug_probe",
        lambda *_args, **_kwargs: events.append("debug"),
    )
    monkeypatch.setattr(
        device_install,
        "prepare_linux_shell",
        lambda *_args, **_kwargs: events.append("linux"),
    )
    monkeypatch.setattr(
        device_install,
        "install_cm0",
        lambda *_args, **_kwargs: events.append("cm0") or "installed",
    )

    device_install.install_waverider(tmp_path, "COM7")

    assert events == ["debug", "linux", "cm0"]


def test_install_waverider_never_falls_back_after_sd_ownership_failure(
    monkeypatch, tmp_path
):
    fallback: list[str] = []
    monkeypatch.setattr(device_install, "verify_release_checksums", lambda _root: None)
    monkeypatch.setattr(
        device_install,
        "install_native_via_sd",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            device_install.SdOwnershipError("ownership unknown")
        ),
    )
    monkeypatch.setattr(
        device_install,
        "install_native_via_debug_probe",
        lambda *_args, **_kwargs: fallback.append("unsafe fallback"),
    )

    with pytest.raises(device_install.SdOwnershipError):
        device_install.install_waverider(tmp_path, "COM7")

    assert fallback == []
