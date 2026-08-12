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
    def test_archive_uses_strict_cm0_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in serial_install.CM0_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"required")
            package = root / "src" / "freewili_foxhunt"
            (package / "__pycache__").mkdir(parents=True)
            (package / "app.py").write_text("pass\n")
            (package / "__pycache__" / "app.pyc").write_bytes(b"generated")
            (root / ".env").write_text("SECRET=do-not-transfer\n")
            (root / "research").mkdir()
            (root / "research" / "private-dump.bin").write_bytes(b"private")
            payload = serial_install.make_archive(root)
            with tarfile.open(fileobj=BytesIO(payload), mode="r:gz") as archive:
                names = archive.getnames()
            self.assertIn("freewili-foxhunt/src/freewili_foxhunt/app.py", names)
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(".env" in name for name in names))
            self.assertFalse(any("private-dump" in name for name in names))

    def test_archive_fails_when_required_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                serial_install.make_archive(Path(directory))

    def test_cm0_installer_verifies_pinned_packages_and_replaces_runtime_tree(self) -> None:
        installer = (MODULE_PATH.parents[1] / "install.sh").read_text()

        self.assertIn("RTLSDR_VERSION=2.0.2-2+b1", installer)
        self.assertIn("sha256sum -c -", installer)
        self.assertIn("dpkg-query -W", installer)
        self.assertIn("STAGE_DIR=/opt/.freewili-foxhunt.new.$$", installer)
        self.assertIn('mv "$INSTALL_DIR" "$PREVIOUS_DIR"', installer)
        self.assertIn('mv "$STAGE_DIR" "$INSTALL_DIR"', installer)
        self.assertIn("python3 -m compileall", installer)
        self.assertIn("restore_previous_runtime", installer)
        self.assertIn("restore_system_file", installer)
        self.assertIn("ROLLBACK_ARMED=1", installer)
        self.assertIn("ROLLBACK_DIR=/var/lib/freewili-foxhunt/install-rollback", installer)
        self.assertIn("trap 'exit 143' TERM", installer)
        self.assertIn("upgrade was interrupted", installer)
        self.assertIn("mixed version", installer)


if __name__ == "__main__":
    unittest.main()
