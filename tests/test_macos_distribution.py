import importlib.util
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_macos_app", ROOT / "scripts" / "macos_app.py")
macos_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(macos_app)
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))  # the scripts import each other by name

import archive_update  # noqa: E402
import manage  # noqa: E402
import server as bookmark_server  # noqa: E402
import settings  # noqa: E402
import updates  # noqa: E402


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

    def test_unchanged_app_launches_without_copying_its_files_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle, runtime = root / "bundle", root / "runtime"
            (bundle / "web").mkdir(parents=True)
            (bundle / "web/index.html").write_text("page", encoding="utf-8")
            with patch.object(macos_app, "bundle_root", return_value=bundle), patch.object(macos_app, "user_root", return_value=runtime):
                macos_app.prepare_runtime()
                with patch.object(macos_app.shutil, "copy2", side_effect=AssertionError("copied again")):
                    macos_app.prepare_runtime()
                # A public file that went missing is restored even when the app did not change.
                (runtime / "web/index.html").unlink()
                macos_app.prepare_runtime()
                self.assertEqual((runtime / "web/index.html").read_text(encoding="utf-8"), "page")
                (bundle / "web/index.html").write_text("new page!", encoding="utf-8")
                macos_app.prepare_runtime()
            self.assertEqual((runtime / "web/index.html").read_text(encoding="utf-8"), "new page!")
            self.assertEqual(list(runtime.rglob("*.tmp")), [])

    def packaged(self):
        """Run as the installed macOS app, whose launcher sets BOOKMARK_PACKAGED=1."""
        patcher = patch.object(settings, "PACKAGED_APP", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_installed_app_launcher_switches_the_scripts_to_packaged_mode(self):
        # macos_app sets these before importing manage; settings reads them when it loads.
        spec = importlib.util.spec_from_file_location("bookmark_packaged_settings", SCRIPTS / "settings.py")
        packaged = importlib.util.module_from_spec(spec)
        runtime = Path("/Users/me/Library/Application Support/Bookmark")
        with patch.dict(os.environ, {"BOOKMARK_PACKAGED": "1", "BOOKMARK_ROOT": str(runtime)}):
            spec.loader.exec_module(packaged)
        self.assertTrue(packaged.PACKAGED_APP)
        self.assertEqual(packaged.DATA_JS, runtime / "web/data.js")
        self.assertFalse(settings.PACKAGED_APP, "测试进程本身不是安装版")

    def test_installed_app_reports_its_version_without_a_script_file_to_read(self):
        # The installed app runs manage from its bundle, so settings finds no manage.py beside it.
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "settings.py"
            copy.write_bytes((SCRIPTS / "settings.py").read_bytes())
            spec = importlib.util.spec_from_file_location("settings", copy)
            bundled = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bundled)
        self.assertEqual(bundled.APP_VERSION, "")
        spec = importlib.util.spec_from_file_location("bookmark_bundled_manage", SCRIPTS / "manage.py")
        with patch.dict(sys.modules, {"settings": bundled}):
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        self.assertEqual(bundled.APP_VERSION, manage.APP_VERSION, "页面、更新检查和数据构建都读这个版本")

    def test_packaged_update_status_reports_a_new_dmg_without_offering_to_install_it(self):
        self.packaged()
        remote = {"available": True, "can_update": True, "mode": "archive", "remote": "v9.9.9",
                  "source": "GitHub", "target": "a" * 40, "tree": "b" * 40}
        with patch.object(archive_update, "update_status", return_value=remote):
            status = updates.repository_update_status()
        self.assertEqual(status["mode"], "dmg")
        self.assertTrue(status["available"])
        self.assertFalse(status["can_update"], "安装版不能就地改写自身")
        self.assertEqual(status["remote"], "v9.9.9")
        self.assertEqual(status["download"], "https://github.com/heropml/Bookmark/releases")
        self.assertNotIn("target", status, "安装版不需要提交号，不能被当作可升级来源")

    def test_packaged_update_status_stays_quiet_on_the_current_version(self):
        self.packaged()
        remote = {"available": False, "can_update": True, "mode": "archive",
                  "remote": manage.APP_VERSION, "source": "Gitee"}
        with patch.object(archive_update, "update_status", return_value=remote):
            status = updates.repository_update_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["download"], "https://gitee.com/heropml/Bookmark/releases")

    def test_packaged_install_is_refused_even_if_a_page_posts_an_upgrade(self):
        self.packaged()
        with patch.object(archive_update, "install", side_effect=AssertionError("must not rewrite the app")):
            with self.assertRaises(updates.UpdateError):
                updates.update_repository()

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
        server = bookmark_server.BookmarkServer(("127.0.0.1", 0), bookmark_server.Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/__icon?skin=aurora"
        page = {"Origin": f"http://127.0.0.1:{server.server_port}"}
        with patch.object(sys, "platform", "darwin"):
            with urlopen(Request(url, method="POST", headers=page), timeout=5) as response:
                self.assertEqual(response.status, 204)
        # Windows still reports a failure rather than resetting the connection.
        with patch.object(sys, "platform", "win32"):
            with patch.dict("sys.modules", {"shortcut": SimpleNamespace(
                    set_icon=lambda skin: (_ for _ in ()).throw(SystemExit("missing icon")))}):
                with self.assertRaises(HTTPError) as failure:
                    urlopen(Request(url, method="POST", headers=page), timeout=5)
        self.addCleanup(failure.exception.close)
        self.assertEqual(failure.exception.code, 400)

    def test_other_sites_cannot_change_the_shortcut_icon(self):
        server = bookmark_server.BookmarkServer(("127.0.0.1", 0), bookmark_server.Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/__icon?skin=cyber"
        changed = []
        icons = SimpleNamespace(set_icon=changed.append)
        with patch.object(sys, "platform", "win32"), patch.dict("sys.modules", {"shortcut": icons}):
            # An <img> or form on another site cannot carry this page's Origin.
            for request in (Request(url), Request(url, method="POST", headers={"Origin": "https://evil.example"})):
                with self.subTest(method=request.get_method()):
                    with self.assertRaises(HTTPError) as failure:
                        urlopen(request, timeout=5)
                    failure.exception.close()
                    self.assertIn(failure.exception.code, (403, 404))
        self.assertEqual(changed, [])

    def test_packaged_restart_relaunches_the_app_not_a_python_script(self):
        self.packaged()
        self.assertEqual(bookmark_server.serve_command("/Applications/Bookmark.app/Contents/MacOS/Bookmark", 8765),
                         ["/Applications/Bookmark.app/Contents/MacOS/Bookmark", "--serve", "8765"])

    def test_open_page_uses_the_default_browser(self):
        steps = []
        manage = SimpleNamespace(
            bookmark_store=SimpleNamespace(build_if_stale=lambda: steps.append("build")),
            local_url=lambda: steps.append("url") or "http://127.0.0.1:8765/index.html?v=1-2",
        )
        with patch.object(macos_app.webbrowser, "open") as browser:
            macos_app.open_page(manage)
        self.assertEqual(steps, ["build", "url"], "页面数据应先于打开页面生成")
        browser.assert_called_once_with("http://127.0.0.1:8765/index.html?v=1-2")
