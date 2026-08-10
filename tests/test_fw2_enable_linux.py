from tools.fw2_enable_linux import call


class FakeSerial:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.writes = []

    def reset_input_buffer(self):
        pass

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass

    def read(self, _size):
        return next(self.chunks, b"")


def test_linux_enable_accepts_multiline_success_frame():
    port = FakeSerial(
        [
            b"menu noise\r\n[l\\a ABC 8 Linux CPU power: ON ",
            b"(confirm via live state)\r\nOk 1]\r\n",
        ]
    )

    frame = call(port, (b"l", b"a"), b"[l\\a ", "enabling CM0 Linux")

    assert frame.startswith(b"[l\\a ")
    assert frame.endswith(b"Ok 1]")
    assert port.writes == [b"\x02l\na\n"]
