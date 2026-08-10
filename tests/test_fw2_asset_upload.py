from types import SimpleNamespace

from deploy.fw2_asset_upload import DEFAULT_ASSETS, patch_fw2_file_menu, wait_for_commit


def test_fw2_asset_upload_routes_legacy_file_command_through_hardware_menu():
    sent = []
    device = SimpleNamespace(
        serial_port=SimpleNamespace(send=lambda value, *args, **kwargs: sent.append(value))
    )

    patch_fw2_file_menu(device)
    device.serial_port.send("x\nf\n1:/images/WAVERIDR.FWI\n")
    device.serial_port.send("x\na\n1:/images\n")
    device.serial_port.send("g\nl\n1:/images/WAVERIDR.FWI\n")

    assert sent == [
        "h\nx\nf\n1:/images/WAVERIDR.FWI\n",
        "h\nx\na\n1:/images\n",
        "g\nl\n1:/images/WAVERIDR.FWI\n",
    ]


def test_default_assets_include_splash_and_continuous_rssi_scale():
    assert DEFAULT_ASSETS == (
        ("assets/splash/WAVERIDR.FWI", "1:/images/WAVERIDR.FWI"),
        ("assets/ui/RSSISCL.FWI", "1:/images/RSSISCL.FWI"),
    )


def test_commit_wait_consumes_delayed_success_frame():
    class Result:
        def __init__(self, value):
            self.ok_value = value

        def is_ok(self):
            return True

    responses = iter([Result(SimpleNamespace(response="success 4944 bytes 123 crc 1"))])
    device = SimpleNamespace(_wait_for_response_frame=lambda *args, **kwargs: next(responses))

    assert "success 4944 bytes" in wait_for_commit(
        device,
        "1:/images/RSSISCL.FWI",
        4944,
        "Send File Now",
    )
