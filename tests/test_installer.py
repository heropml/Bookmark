import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import tarfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_installer", ROOT / "scripts/build_installer.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(TestCase):
    def test_runtime_uses_git_bytes_and_rejects_non_newline_changes(self):
        name = "runtime/python/Lib/sample.py"
        canonical = b"value = 1\n"
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as stream:
            info = tarfile.TarInfo(name)
            info.size = len(canonical)
            stream.addfile(info, io.BytesIO(canonical))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / name
            target.parent.mkdir(parents=True)
            target.write_bytes(b"value = 1\r\n")
            with patch.object(installer.subprocess, "check_output", return_value=archive.getvalue()):
                self.assertEqual(installer.runtime_payload(root), {name: canonical})
                target.write_bytes(b"value = 2\r\n")
                with self.assertRaisesRegex(ValueError, "Commit runtime changes"):
                    installer.runtime_payload(root)

    def test_private_and_development_files_are_excluded(self):
        for name in (
            "web/data.js", "web/DATA.JS", "data/bookmarks.html", "data/.window-state.json",
            "data/.update-backups/old.py", ".git/config", "web/.env", "tests/private.json",
            "scripts/__pycache__/manage.pyc", "runtime/python/Lib/__pycache__/os.pyc",
            "launchers/windows/private.lnk", "launchers/windows/build-installer.bat",
            "../web/index.html", "/web/index.html", "web/../private", "web//private",
            "web\\private", "web/index.html:private",
        ):
            with self.subTest(name=name):
                self.assertFalse(installer.public_file(name))

    def test_runtime_native_modules_and_public_app_files_are_included(self):
        for name in (
            "scripts/manage.py", "scripts/archive_update.py", "web/index.html",
            "web/js/update.js", "web/data.example.js", "data/bookmarks.example.html",
            "runtime/python/pythonw.exe", "runtime/python/DLLs/_ssl.pyd",
            "runtime/python/Lib/site-packages/PIL/_imaging.pyd", "LICENSE",
        ):
            with self.subTest(name=name):
                self.assertTrue(installer.public_file(name))

    def test_actual_payload_has_runtime_and_updater_but_no_private_data(self):
        names = installer.package_files(ROOT)
        self.assertTrue(installer.REQUIRED <= set(names))
        self.assertTrue(all(installer.public_file(name) for name in names))
        self.assertNotIn("web/data.js", names)
        self.assertNotIn("data/bookmarks.html", names)

    def test_untracked_files_are_not_swept_into_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in installer.REQUIRED | {"web/private.txt"}:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            result = subprocess.CompletedProcess([], 0, b"web/index.html\0web/data.js\0")
            with patch.object(installer.subprocess, "run", return_value=result):
                self.assertEqual(set(installer.package_files(root)), installer.REQUIRED)
                (root / "scripts/archive_update.py").unlink()
                with self.assertRaisesRegex(ValueError, "Missing package file"):
                    installer.package_files(root)

    def test_version_is_read_without_importing_application(self):
        self.assertEqual(installer.app_version(ROOT), "1.0.5")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "web").mkdir()
            (root / "scripts/manage.py").write_text('APP_VERSION = "v2.3.4"\nraise Exception()', encoding="utf-8")
            (root / "web/index.html").write_text('<div id="appVersion">v2.3.4</div>', encoding="utf-8")
            self.assertEqual(installer.app_version(root), "2.3.4")
            (root / "web/index.html").write_text("v2.3.3", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "versions disagree"):
                installer.app_version(root)

    def test_installer_preserves_data_and_has_no_broad_process_kills(self):
        script = (ROOT / "scripts/Bookmark.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("CloseApplications=force", script)
        self.assertIn("RestartApplications=no", script)
        self.assertIn("skipifsilent", script)
        self.assertIn("pythonw.exe", script)
        self.assertIn("PrepareToInstall", script)
        self.assertIn("CurUninstallStep <> usUninstall then Exit", script)
        self.assertIn("Executable = PythonPath", script)
        self.assertIn("Executable = PythonwPath", script)
        self.assertIn("ManagePath", script)
        self.assertIn("' --serve '", script)
        self.assertNotIn("[UninstallDelete]", script)
        self.assertNotIn("[InstallDelete]", script)
        self.assertNotIn("taskkill", script.lower())
