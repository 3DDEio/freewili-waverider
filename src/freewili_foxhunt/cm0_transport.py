"""Direct OneWili transport over the persistent fwcm0 bridge socket."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import logging
import os
import queue
import socket
import struct
import threading
import time
from typing import Any


BRIDGE_SOCKET = "/run/fwcm0-bridge.sock"
OP_CONSOLE = 0x05
RESET_QUIET = b"\x02"
LOG = logging.getLogger(__name__)


def configured_batch_window() -> int:
    """Return a deliberately bounded production mailbox window.

    A clean-device benchmark may raise this value through the service
    environment.  Defaulting to one prevents an unproven install from
    repeating the 32-command burst that wedged the tested v07 bridge.
    """

    raw = os.environ.get("WAVERIDER_CM0_BATCH_WINDOW", "1")
    try:
        value = int(raw)
    except ValueError:
        LOG.warning("invalid WAVERIDER_CM0_BATCH_WINDOW=%r; using 1", raw)
        return 1
    if not 1 <= value <= 8:
        LOG.warning("unsafe WAVERIDER_CM0_BATCH_WINDOW=%r; using 1", raw)
        return 1
    return value


class SocketCm0Transport:
    """Drop-in OneWili transport without a per-client fwcm0 subprocess."""

    def __init__(self, socket_path: str = BRIDGE_SOCKET) -> None:
        self.socket_path = socket_path
        self._socket: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._running = False
        self.frames: queue.Queue[Any] = queue.Queue()
        self.events: queue.Queue[Any] = queue.Queue()
        self.lines: queue.Queue[str] = queue.Queue()
        self._expected_path: str | None = None
        self._expected_lock = threading.Lock()

    def open(self) -> None:
        if self._socket is not None:
            return
        from onewili import framing

        del framing  # validates that the generated package is importable
        bridge = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        bridge.connect(self.socket_path)
        bridge.sendall(struct.pack("<I", 1) + bytes((OP_CONSOLE,)))
        self._socket = bridge
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._write(RESET_QUIET + b"\n")
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and self.lines.empty() and self.frames.empty():
            time.sleep(0.05)
        time.sleep(0.3)
        self.flush_queues(include_events=True)

    def close(self) -> None:
        self._running = False
        bridge = self._socket
        self._socket = None
        if bridge is not None:
            try:
                bridge.sendall(RESET_QUIET)
                bridge.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            bridge.close()
        if self._reader is not None:
            self._reader.join(timeout=1.0)
            self._reader = None

    def send(self, command: str) -> None:
        if self._socket is None:
            raise RuntimeError("transport is not open")
        with self._expected_lock:
            self._expected_path = command.split(" ", 1)[0]
        self._write(RESET_QUIET + command.encode("ascii") + b"\n")

    def call_batch(
        self,
        commands: list[str],
        timeout: float = 5.0,
        window: int | None = None,
    ) -> list[Any]:
        """Pipeline small command windows across the CM0 mailbox bridge.

        The generated OneWili bindings wait for an acknowledgement after every
        plot point. That round trip, rather than RTL-SDR capture, dominates a
        waterfall row. FW2 v07 can multiplex host traffic and complete Display
        commands out of submission order, so correlate a multiset of response
        paths instead of assuming FIFO completion. The production window is
        deliberately small and hardware-benchmarked: payload byte capacity is
        not evidence that the FPGA mailbox can accept a whole row at once.
        """

        if self._socket is None:
            raise RuntimeError("transport is not open")
        if window is None:
            window = configured_batch_window()
        if window < 1:
            raise ValueError("window must be positive")

        responses: list[Any] = []
        for start in range(0, len(commands), window):
            pending = commands[start : start + window]
            expected_paths = [command.split(" ", 1)[0] for command in pending]
            outstanding = Counter(expected_paths)
            matched: dict[str, deque[Any]] = defaultdict(deque)
            # No single generated call is outstanding when the display enters
            # a batch. Drop already-queued standard replies so a stale frame
            # with the same path cannot satisfy a new plot command. Unsolicited
            # input events remain preserved.
            self.flush_queues()
            for command in pending:
                self._write(RESET_QUIET + command.encode("ascii") + b"\n")
            deadline = time.monotonic() + timeout
            remaining = len(pending)
            while remaining:
                frame = self._wait_frame_any(max(0.0, deadline - time.monotonic()))
                if frame is None:
                    missing = ", ".join(
                        f"{path} x{count}" for path, count in outstanding.items() if count
                    )
                    raise TimeoutError(f"timeout waiting for batched responses: {missing}")
                path = str(getattr(frame, "path", ""))
                if outstanding.get(path, 0) <= 0:
                    LOG.debug("ignoring unrelated CM0 frame while batching: %s", frame)
                    continue
                if not bool(getattr(frame, "success", True)):
                    raise RuntimeError(
                        f"{path!r} failed while batching: {getattr(frame, 'response', '')}"
                    )
                matched[path].append(frame)
                outstanding[path] -= 1
                remaining -= 1
            # Preserve the caller-visible command order even if firmware
            # completed the commands in a different order.
            responses.extend(matched[path].popleft() for path in expected_paths)
        return responses

    def wait_frame(self, timeout: float = 5.0) -> Any | None:
        with self._expected_lock:
            expected_path = self._expected_path
        deadline = time.monotonic() + timeout
        while True:
            frame = self._wait_frame_any(max(0.0, deadline - time.monotonic()))
            if frame is None:
                self._clear_expected_path(expected_path)
                return None
            if expected_path is not None and str(getattr(frame, "path", "")) != expected_path:
                LOG.debug(
                    "ignoring unrelated CM0 frame: got %s, waiting for %s",
                    getattr(frame, "path", None),
                    expected_path,
                )
                continue
            self._clear_expected_path(expected_path)
            return frame

    def _clear_expected_path(self, expected_path: str | None = None) -> None:
        """Release single-call correlation without clobbering a newer send."""

        with self._expected_lock:
            if expected_path is None or self._expected_path == expected_path:
                self._expected_path = None

    def _wait_frame_any(self, timeout: float) -> Any | None:
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush_queues(self, include_events: bool = False) -> None:
        """Discard stale replies while preserving unsolicited input events."""

        self._clear_expected_path()
        destinations = [self.frames, self.lines]
        if include_events:
            destinations.append(self.events)
        for destination in destinations:
            while True:
                try:
                    destination.get_nowait()
                except queue.Empty:
                    break

    def _write(self, data: bytes) -> None:
        if self._socket is None:
            raise RuntimeError("transport is not open")
        self._socket.sendall(data)

    def _read_loop(self) -> None:
        from onewili import framing

        buffered = b""
        while self._running and self._socket is not None:
            try:
                chunk = self._socket.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buffered += chunk
            while b"\n" in buffered:
                raw, buffered = buffered.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not line:
                    continue
                try:
                    if framing.EVENT_RE.match(line):
                        self.events.put(framing.ResponseFrame.parse(line))
                        continue
                    if framing.FRAME_RE.match(line):
                        self.frames.put(framing.ResponseFrame.parse(line))
                        continue
                except ValueError:
                    pass
                self.lines.put(line)
