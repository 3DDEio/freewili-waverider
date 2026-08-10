"""Long-running rtl_power process with safe retuning."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
from collections.abc import Iterator

from .models import FrequencyEntry
from .spectrum import SpectrumRow, parse_rtl_power_csv


GAIN_DB_BY_PROFILE = {
    "auto": None,
    "foxhunt": 25.4,
    "close-in": 0.0,
    "manual": 25.4,
}


class RtlPowerStream:
    def __init__(self, executable: str = "rtl_power") -> None:
        resolved = shutil.which(executable)
        if not resolved:
            raise FileNotFoundError(f"{executable} is not installed")
        self.executable = resolved
        self.process: subprocess.Popen[str] | None = None
        self.rows: queue.Queue[SpectrumRow | Exception] = queue.Queue(maxsize=4)
        self.reader: threading.Thread | None = None

    def command_for(self, entry: FrequencyEntry) -> list[str]:
        entry.validate()
        low = entry.frequency_hz - entry.span_hz // 2
        high = entry.frequency_hz + entry.span_hz // 2
        target_bins = 240
        bin_hz = max(100, entry.span_hz // target_bins)
        command = [
            self.executable,
            "-f",
            f"{low}:{high}:{bin_hz}",
            "-i",
            "1",
        ]
        gain = GAIN_DB_BY_PROFILE[entry.gain_profile]
        if gain is not None:
            command.extend(["-g", f"{gain:.1f}"])
        command.append("/dev/stdout")
        return command

    def start(self, entry: FrequencyEntry) -> None:
        self.stop()
        while not self.rows.empty():
            self.rows.get_nowait()
        self.process = subprocess.Popen(
            self.command_for(entry),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env={**os.environ, "LC_ALL": "C"},
        )
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

    def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                if not line.strip():
                    continue
                try:
                    item: SpectrumRow | Exception = parse_rtl_power_csv(line)
                except (ValueError, IndexError) as error:
                    item = error
                if self.rows.full():
                    self.rows.get_nowait()
                self.rows.put_nowait(item)
        finally:
            if self.process and self.process.poll() not in (None, 0, -15):
                if not self.rows.full():
                    self.rows.put_nowait(RuntimeError("rtl_power stopped unexpectedly"))

    def __iter__(self) -> Iterator[SpectrumRow]:
        while self.process is not None:
            item = self.rows.get()
            if isinstance(item, Exception):
                raise item
            yield item

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        if self.reader is not None:
            self.reader.join(timeout=1)
            self.reader = None

    def close(self) -> None:
        self.stop()
