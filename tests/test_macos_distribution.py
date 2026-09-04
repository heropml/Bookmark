import importlib.util
import json
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_macos_app", ROOT / "scripts" / "macos_app.py")
macos_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(macos_app)


class MacOSDistributionTests(TestCase):
    def test_runtime_preparation_refreshes_public_files_without_private_bookmarks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle, runtime = root / "bundle", root / "runtime"
            (bundle / "web").mkdir(parents=True)
            (bundle / "assets").mkdir()
            (bundle / "data").mkdir()
            (bundle / "web/index.html").write_text("new page", encoding="utf-8")
            (bundle / "data/bookmarks.example.html").write_text("example", encoding="utf-8")
            (runtime / "web").mkdir(parents=True)
            (runtime / "data").mkdir()
            (runtime / "web/data.js").write_text("private data", encoding="utf-8")
            (runtime / "data/bookmarks.html").write_text("private bookmarks", encoding="utf-8")
            with patch.object(macos_app, "bundle_root", return_value=bundle), patch.object(macos_app, "user_root", return_value=runtime):
                self.assertEqual(macos_app.prepare_runtime(), runtime)
            self.assertEqual((runtime / "web/index.html").read_text(encoding="utf-8"), "new page")
            self.assertEqual((runtime / "web/data.js").read_text(encoding="utf-8"), "private data")
            self.assertEqual((runtime / "data/bookmarks.html").read_text(encoding="utf-8"), "private bookmarks")

    def packaged_manage(self):
        spec = importlib.util.spec_from_file_location("bookmark_packaged_manage", ROOT / "scripts" / "manage.py")
        manage = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"BOOKMARK_PACKAGED": "1"}):
            spec.loader.exec_module(manage)
        return manage

    def test_packaged_update_status_reports_a_new_dmg_without_offering_to_install_it(self):
        manage = self.packaged_manage()
        remote = {"available": True, "can_update": True, "mode": "archive", "remote": "v9.9.9",
                  "source": "GitHub", "target": "a" * 40, "tree": "b" * 40}
        with patch.object(manage.archive_update, "update_status", return_value=remote):
            status = manage.repository_update_status()
        self.assertEqual(status["mode"], "dmg")
        self.assertTrue(status["available"])
        self.assertFalse(status["can_update"], "安装版不能就地改写自身")
        self.assertEqual(status["remote"], "v9.9.9")
        self.assertEqual(status["download"], "https://github.com/heropml/Bookmark/releases")
        self.assertNotIn("target", status, "安装版不需要提交号，不能被当作可升级来源")

    def test_packaged_update_status_stays_quiet_on_the_current_version(self):
        manage = self.packaged_manage()
        remote = {"available": False, "can_update": True, "mode": "archive",
                  "remote": manage.APP_VERSION, "source": "Gitee"}
        with patch.object(manage.archive_update, "update_status", return_value=remote):
            status = manage.repository_update_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["download"], "https://gitee.com/heropml/Bookmark/releases")

    def test_packaged_install_is_refused_even_if_a_page_posts_an_upgrade(self):
        manage = self.packaged_manage()
        with patch.object(manage.archive_update, "install", side_effect=AssertionError("must not rewrite the app")):
            with self.assertRaises(manage.UpdateError):
                manage.update_repository()

    def test_files_dropped_by_a_newer_bundle_are_removed_but_private_data_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle, runtime = root / "bundle", root / "runtime"
            for tree in ("web/js", "assets", "data"):
                (bundle / tree).mkdir(parents=True)
            (bundle / "web/index.html").write_text("old page", encoding="utf-8")
            (bundle / "web/js/legacy.js").write_text("// legacy", encoding="utf-8")
            (bundle / "data/bookmarks.example.html").write_text("example", encoding="utf-8")
            with patch.object(macos_app, "bundle_root", return_value=bundle), patch.object(macos_app, "user_root", return_value=runtime):
                macos_app.prepare_runtime()
                (runtime / "web/data.js").write_text("private data", encoding="utf-8")
                (runtime / "data/bookmarks.html").write_text("private bookmarks", encoding="utf-8")
                (runtime / "web/my-image.png").write_bytes(b"user added")
                # The next release drops the legacy module and ships a new one.
                (bundle / "web/js/legacy.js").unlink()
                (bundle / "web/js/new.js").write_text("// new", encoding="utf-8")
                macos_app.prepare_runtime()
            self.assertFalse((runtime / "web/js/legacy.js").exists(), "上一版留下的模块应被清理")
            self.assertEqual((runtime / "web/js/new.js").read_text(encoding="utf-8"), "// new")
            self.assertEqual((runtime / "web/data.js").read_text(encoding="utf-8"), "private data")
            self.assertEqual((runtime / "data/bookmarks.html").read_text(encoding="utf-8"), "private bookmarks")
            self.assertEqual((runtime / "web/my-image.png").read_bytes(), b"user added")

    def test_a_tampered_manifest_cannot_delete_files_outside_the_public_trees(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle, runtime = root / "bundle", root / "runtime"
            (bundle / "web").mkdir(parents=True)
            (bundle / "web/index.html").write_text("page", encoding="utf-8")
            (runtime / "data").mkdir(parents=True)
            (runtime / "data/bookmarks.html").write_text("private bookmarks", encoding="utf-8")
            (runtime / macos_app.BUNDLE_MANIFEST).write_text(
                json.dumps(["../escape.txt", "data/bookmarks.html", "web/../../escape.txt", 7]),
                encoding="utf-8")
            outside = root / "escape.txt"
            outside.write_text("must survive", encoding="utf-8")
            with patch.object(macos_app, "bundle_root", return_value=bundle), patch.object(macos_app, "user_root", return_value=runtime):
                macos_app.prepare_runtime()
            self.assertEqual(outside.read_text(encoding="utf-8"), "must survive")
            self.assertTrue((runtime / "data/bookmarks.html").is_file())

    def test_packaged_icons_are_read_from_the_user_directory_not_the_app_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            icons = runtime / "assets" / "icons"
            icons.mkdir(parents=True)
            (icons / "icon-aurora.ico").write_bytes(b"aurora icon")
            with patch.dict(os.environ, {"BOOKMARK_ROOT": str(runtime)}):
                spec = importlib.util.spec_from_file_location(
                    "bookmark_packaged_shortcut", ROOT / "scripts" / "shortcut.py")
                shortcut = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(shortcut)
            self.assertEqual(shortcut.icon_path("aurora"), icons / "icon-aurora.ico")
            self.assertEqual(shortcut.icon_path("aurora").read_bytes(), b"aurora icon")

    def test_skin_change_outside_windows_answers_instead_of_dropping_the_connection(self):
        spec = importlib.util.spec_from_file_location("bookmark_icon_manage", ROOT / "scripts" / "manage.py")
        manage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manage)
        server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/__icon?skin=aurora"
        with patch.object(manage.sys, "platform", "darwin"):
            with urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 204)
        # Windows still reports a failure rather than resetting the connection.
        with patch.object(manage.sys, "platform", "win32"):
            with patch.dict("sys.modules", {"shortcut": SimpleNamespace(
                    set_icon=lambda skin: (_ for _ in ()).throw(SystemExit("missing icon")))}):
                with self.assertRaises(HTTPError) as failure:
                    urlopen(url, timeout=5)
        self.addCleanup(failure.exception.close)
        self.assertEqual(failure.exception.code, 400)

    def test_packaged_restart_relaunches_the_app_not_a_python_script(self):
        spec = importlib.util.spec_from_file_location("bookmark_packaged_restart", ROOT / "scripts" / "manage.py")
        manage = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"BOOKMARK_PACKAGED": "1"}):
            spec.loader.exec_module(manage)
        self.assertEqual(manage.serve_command("/Applications/Bookmark.app/Contents/MacOS/Bookmark", 8765),
                         ["/Applications/Bookmark.app/Contents/MacOS/Bookmark", "--serve", "8765"])

    def test_open_page_uses_the_default_browser(self):
        manage = SimpleNamespace(
            build=lambda: None,
            pick_port=lambda: 8765,
            page_ok=lambda _port: True,
            WEB_ROOT=ROOT / "web",
            DATA_JS=ROOT / "web" / "data.example.js",
        )
        with patch.object(macos_app.webbrowser, "open") as browser:
            macos_app.open_page(manage)
        browser.assert_called_once()
        self.assertIn("http://127.0.0.1:8765/index.html", browser.call_args.args[0])
