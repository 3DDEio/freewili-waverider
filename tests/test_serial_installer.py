from __future__ import annotations

import importlib.util
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "deploy" / "serial_install.py"
SPEC = importlib.util.spec_from_file_location("serial_install", MODULE_PATH)
assert SPEC and SPEC.loader
serial_install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serial_install)


class SerialInstallerTests(unittest.TestCase):
    def test_archive_excludes_generated_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "__pycache__").mkdir(parents=True)
            (root / "src" / "app.py").write_text("pass\n")
            (root / "src" / "__pycache__" / "app.pyc").write_bytes(b"generated")
            payload = serial_install.make_archive(root)
            with tarfile.open(fileobj=BytesIO(payload), mode="r:gz") as archive:
                names = archive.getnames()
            self.assertIn("freewili-foxhunt/src/app.py", names)
            self.assertFalse(any("__pycache__" in name for name in names))


if __name__ == "__main__":
    unittest.main()
