"""Machine-readable runtime status for foxhuntctl and support bundles."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class StatusWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, **values: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_monotonic": time.monotonic(),
            "updated_unix": time.time(),
            **values,
        }
        fd, temporary = tempfile.mkstemp(prefix=".foxhunt-status-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
