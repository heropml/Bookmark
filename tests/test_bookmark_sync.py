import os
import subprocess
import sys
import json
from pathlib import Path
import tempfile
import threading
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, install_opener, urlopen

# Build urllib's shared opener now: creating it later, while tests pretend to be on Windows,
# makes ssl look for the Windows certificate store on other systems.
install_opener(build_opener())

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))  # the scripts import each other by name

import manage  # noqa: E402
import bookmark_store  # noqa: E402
import browser_sync  # noqa: E402
import server as bookmark_server  # noqa: E402
import settings  # noqa: E402


class DirectoryServiceTests(TestCase):
    def test_windows_discovers_common_chromium_browsers_with_bookmarks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local, roaming = root / "local", root / "roaming"
            chrome = local / "Google/Chrome/User Data/Default"
            brave = local / "BraveSoftware/Brave-Browser/User Data/Default"
            qq = local / "Tencent/QQBrowser/User Data/Default"
            quark = local / "Quark/Quark/User Data/Default"
            opera = roaming / "Opera Software/Opera Stable"
            sogou = roaming / "SogouExplorer/Webkit"
            for profile in (chrome, brave, qq, quark):
                profile.mkdir(parents=True)
                (profile / "Bookmarks").write_text('{"roots": {}}', encoding="utf-8")
                (profile.parent / "Local State").write_text(
                    '{"profile": {"last_used": "Default"}}', encoding="utf-8"
                )
            opera.mkdir(parents=True)
            (opera / "Bookmarks").write_text('{"roots": {}}', encoding="utf-8")
            sogou.mkdir(parents=True)
            (sogou / "Bookmarks").write_text('{"roots": {}}', encoding="utf-8")
            with patch.object(sys, "platform", "win32"), patch.dict(
                os.environ, {"LOCALAPPDATA": str(local), "APPDATA": str(roaming)}
            ):
                self.assertEqual(
                    browser_sync.supported_sync_browsers(),
                    ["chrome", "brave", "opera", "qq", "sogou", "quark", "html"],
                )

    def test_unreadable_or_malformed_local_state_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            edge = local / "Microsoft/Edge/User Data"
            (edge / "Default").mkdir(parents=True)
            (edge / "Default/Bookmarks").write_text('{"roots": {}}', encoding="utf-8")
            brave = local / "BraveSoftware/Brave-Browser/User Data"
            (brave / "Default").mkdir(parents=True)
            (brave / "Default/Bookmarks").write_text('{"roots": {}}', encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
                (edge / "Local State").write_text("{broken", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "unable to read Edge profile"):
                    browser_sync.edge_bookmarks_file()
                for state in ("[]", '{"profile": []}', '{"profile": {"last_used": null}}'):
                    with self.subTest(state=state):
                        (edge / "Local State").write_text(state, encoding="utf-8")
                        with self.assertRaisesRegex(SystemExit, "Edge active profile was not found"):
                            browser_sync.edge_bookmarks_file()
                        # Browsers without a usable Local State still fall back to Default.
                        (brave / "Local State").write_text(state, encoding="utf-8")
                        self.assertEqual(browser_sync.chromium_bookmarks_file("brave"), ("Default", brave / "Default/Bookmarks"))
                self.assertEqual(browser_sync.edge_bookmarks_file("Default"), ("Default", edge / "Default/Bookmarks"))

    def test_local_url_reuses_this_directory_service_or_starts_one(self):
        with tempfile.TemporaryDirectory() as folder:
            web = Path(folder)
            (web / "index.html").write_text("<html>", encoding="utf-8")
            (web / "data.js").write_text("window.BOOKMARKS = [];", encoding="utf-8")
            version = f"{(web / 'index.html').stat().st_mtime_ns}-{(web / 'data.js').stat().st_mtime_ns}"
            with patch.object(settings, "WEB_ROOT", web), patch.object(settings, "DATA_JS", web / "data.js"), patch.object(manage, "pick_port", return_value=8767):
                with patch.object(manage, "page_ok", return_value=True), patch.object(manage, "serve_hidden") as start:
                    self.assertEqual(manage.local_url(), f"http://127.0.0.1:8767/index.html?v={version}")
                    start.assert_not_called()
                with patch.object(manage, "page_ok", return_value=False), patch.object(manage, "serve_hidden") as start:
                    manage.local_url()
                    start.assert_called_once_with(8767)

    def test_url_option_prints_only_the_address_for_launchers(self):
        from io import StringIO
        output = StringIO()
        with patch.object(sys, "argv", ["manage.py", "--url"]), patch.object(manage, "local_url", return_value="http://127.0.0.1:8765/index.html?v=1-2"), patch.object(bookmark_store, "build") as build, patch("sys.stdout", output):
            manage.main()
        self.assertEqual(output.getvalue(), "http://127.0.0.1:8765/index.html?v=1-2\n")
        build.assert_not_called()

    def test_macos_sync_failure_explains_full_disk_access(self):
        with patch.object(sys, "platform", "darwin"):
            failure = browser_sync.sync_failure("chrome")
        self.assertEqual(failure["message"], "macOS 未允许“书签”读取 Chrome 数据。")
        self.assertTrue(failure["settings"])
        self.assertTrue(failure["restart"])
        steps = "".join(failure["steps"])
        self.assertIn("完全磁盘访问权限", steps)
        self.assertIn("/Applications/Bookmark.app", steps)
        self.assertIn("即使开关已开启", steps)
        self.assertIn("“−”移除", steps)
        self.assertIn("“＋”重新添加", steps)
        self.assertIn("“重启书签”重启后台服务", steps)
        with patch.object(sys, "platform", "win32"):
            failure = browser_sync.sync_failure("edge")
        self.assertEqual(failure["message"], "无法读取或保存 Edge 书签。")
        self.assertNotIn("settings", failure, "只有 macOS 权限问题提供系统设置入口")
        self.assertNotIn("restart", failure)

    def test_directory_identity_is_stable_distinct_and_not_a_plain_path(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "源码"
            with patch.object(settings, "ROOT", first):
                key = settings.installation_id()
                self.assertEqual(key, settings.installation_id())
                self.assertEqual(len(key), 64)
                self.assertNotIn(str(first), key)
            with patch.object(settings, "ROOT", Path(folder) / "安装"):
                self.assertNotEqual(key, settings.installation_id())

    def test_reuses_own_service_even_if_a_lower_port_is_free(self):
        with patch.object(manage, "port_in_use", side_effect=lambda port: port == settings.PORT + 2), patch.object(manage, "page_ok", return_value=True):
            self.assertEqual(manage.pick_port(), settings.PORT + 2)

    def test_foreign_or_legacy_service_is_not_reused_or_stopped(self):
        with patch.object(manage, "port_in_use", side_effect=lambda port: port == settings.PORT), patch.object(manage, "page_ok", return_value=False), patch.object(subprocess, "Popen") as spawn:
            self.assertEqual(manage.pick_port(), settings.PORT + 1)
            spawn.assert_not_called()

    def test_no_ports_free_reports_an_error(self):
        with patch.object(manage, "port_in_use", return_value=True), patch.object(manage, "page_ok", return_value=False):
            with self.assertRaisesRegex(SystemExit, "no free port"):
                manage.pick_port()

    def test_readiness_requires_matching_directory_and_legacy_health(self):
        from io import BytesIO
        def response(content):
            stream = BytesIO(content)
            stream.status = 200
            return stream
        for identity in (settings.installation_id(), "another-installation", None):
            with self.subTest(identity=identity):
                service = {"version": "v1.0.4", "installation": identity}
                replies = [response(b'<!doctype html><html>'), response(settings.HEALTH_RESPONSE), response(json.dumps(service).encode())]
                with patch("urllib.request.urlopen", side_effect=replies):
                    self.assertEqual(manage.page_ok(8765), identity == settings.installation_id())


class BookmarkSyncHTTPTests(TestCase):
    def setUp(self):
        self.server = bookmark_server.BookmarkServer(("127.0.0.1", 0), bookmark_server.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.platform = patch.object(sys, "platform", "win32")
        self.platform.start()
        self.supported_patch = patch.object(
            browser_sync, "supported_sync_browsers", return_value=["chrome", "edge", "brave", "qq", "html"]
        )
        self.supported_patch.start()
        self.sync_patch = patch.object(browser_sync, "sync_chrome", return_value=[{}, {}])
        self.sync = self.sync_patch.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.sync_patch.stop()
        self.supported_patch.stop()
        self.platform.stop()

    def post(self, data=None, headers=None):
        payload = {"browser": "chrome", "confirmed": True} if data is None else data
        request_headers = {"Content-Type": "application/json", "Origin": self.base, "X-Bookmark-Sync": "1"}
        request_headers.update(headers or {})
        request = Request(self.base + "/__bookmarks/sync", data=json.dumps(payload).encode(), headers=request_headers)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_opening_dialog_only_reads_supported_browsers(self):
        with urlopen(self.base + "/__bookmarks/sync", timeout=3) as response:
            self.assertEqual(json.load(response), {"browsers": ["chrome", "edge", "brave", "qq", "html"]})
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.sync.assert_not_called()

    def test_confirmed_sync_uses_selected_browser_and_returns_count(self):
        status, data = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "count": 2, "browser": "chrome"})
        self.sync.assert_called_once_with()
        with patch.object(browser_sync, "sync_edge", return_value=[{}]) as edge:
            self.assertEqual(self.post({"browser": "edge", "confirmed": True})[0], 200)
            edge.assert_called_once_with()
        with patch.object(browser_sync, "sync_html", return_value=[{}]) as sync_html:
            self.assertEqual(self.post({"browser": "html", "confirmed": True})[0], 200)
            sync_html.assert_called_once_with()
        with patch.object(browser_sync, "sync_chromium", return_value=[{}]) as sync_chromium:
            self.assertEqual(self.post({"browser": "brave", "confirmed": True})[0], 200)
            sync_chromium.assert_called_once_with("brave")
        with patch.object(browser_sync, "sync_chromium", return_value=[{}]) as sync_chromium:
            self.assertEqual(self.post({"browser": "qq", "confirmed": True})[0], 200)
            sync_chromium.assert_called_once_with("qq")

    def test_confirmation_and_supported_browser_are_required(self):
        for data in ({}, [], {"browser": "chrome"}, {"browser": "chrome", "confirmed": "true"}, {"browser": "firefox", "confirmed": True}, {"browser": "../../private", "confirmed": True}, {"browser": "safari", "confirmed": True}):
            with self.subTest(data=data):
                self.assertEqual(self.post(data)[0], 400)
        self.sync.assert_not_called()

    def test_foreign_origins_form_posts_and_rebinding_hosts_cannot_sync(self):
        for headers in (
            {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Origin": ""},
            {"Content-Type": "text/plain"}, {"X-Bookmark-Sync": ""},
            {"Host": "evil.example", "Origin": "http://evil.example"},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.post(headers=headers)[0], 403)
        self.sync.assert_not_called()

    def test_oversized_body_rejected(self):
        self.assertEqual(self.post({"browser": "chrome", "confirmed": True, "extra": "x" * 300})[0], 400)
        self.sync.assert_not_called()

    def test_busy_sync_and_restarting_service_do_not_write(self):
        with bookmark_server.BOOKMARK_SYNC_LOCK:
            self.assertEqual(self.post()[0], 409)
        self.server.restarting = True
        self.assertEqual(self.post()[0], 409)
        self.sync.assert_not_called()

    def test_read_errors_are_sanitized_and_lock_released(self):
        for error in (SystemExit("private/profile/path"), PermissionError("secret"), ValueError("invalid JSON")):
            self.sync.side_effect = error
            code, data = self.post()
            self.assertEqual(code, 422)
            self.assertNotIn("private", data["message"])
            self.assertNotIn("secret", data["message"])
            # The response can arrive before the server thread enters finally.
            acquired = bookmark_server.BOOKMARK_SYNC_LOCK.acquire(timeout=1)
            self.assertTrue(acquired)
            if acquired:
                bookmark_server.BOOKMARK_SYNC_LOCK.release()

    def test_real_sync_reads_only_fixture_profile_and_changes_only_fixture_site(self):
        self.sync_patch.stop()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir, web = root / "site/data", root / "site/web"
            data_dir.mkdir(parents=True)
            web.mkdir()
            user_data = root / "profiles/Google/Chrome/User Data"
            profile = user_data / "Default"
            profile.mkdir(parents=True)
            (user_data / "Local State").write_text(json.dumps({"profile": {"last_used": "Default"}}), encoding="utf-8")
            browser_file = profile / "Bookmarks"
            source = json.dumps({"roots": {"bookmark_bar": {"type": "folder", "name": "书签栏", "children": [{"type": "url", "name": "同步测试", "url": "https://example.com"}]}}}, ensure_ascii=False)
            browser_file.write_text(source, encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "profiles")}), patch.object(settings, "SRC", data_dir / "bookmarks.html"), patch.object(settings, "DATA_JS", web / "data.js"):
                code, result = self.post()
            self.assertEqual(code, 200)
            self.assertEqual(result["count"], 1)
            self.assertIn("同步测试", (web / "data.js").read_text(encoding="utf-8"))
            self.assertEqual(browser_file.read_text(encoding="utf-8"), source)

    def test_macos_offers_existing_chrome_and_safari_implementation(self):
        with patch.object(sys, "platform", "darwin"), patch.object(browser_sync, "supported_sync_browsers", return_value=["chrome", "safari", "html"]), patch.object(browser_sync, "sync_safari", return_value=[{}]) as safari:
            self.assertEqual(browser_sync.supported_sync_browsers(), ["chrome", "safari", "html"])
            self.assertEqual(self.post({"browser": "safari", "confirmed": True})[0], 200)
            safari.assert_called_once_with()

    def test_html_sync_replaces_bookmarks_from_the_file_selected_in_the_dialog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "export.html"
            source.write_text('<DT><A HREF="https://example.com">导入测试</A>', encoding="utf-8")
            with patch.object(browser_sync, "pick_html", return_value=source), patch.object(settings, "SRC", root / "bookmarks.html"), patch.object(settings, "DATA_JS", root / "data.js"):
                items = browser_sync.sync_html()
            self.assertEqual(len(items), 1)
            self.assertIn("导入测试", (root / "data.js").read_text(encoding="utf-8"))

    def test_settings_shortcut_opens_full_disk_access_only_on_macos_and_only_from_this_page(self):
        url = self.base + "/__bookmarks/settings"
        page = {"Origin": self.base}
        with patch.object(subprocess, "run") as run:
            for origin in ("https://evil.example", None):
                headers = {} if origin is None else {"Origin": origin}
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(url, method="POST", headers=headers), timeout=3)
                caught.exception.close()
                self.assertEqual(caught.exception.code, 403)
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(url, method="POST", headers=page), timeout=3)
            caught.exception.close()
            self.assertEqual(caught.exception.code, 404, "Windows 上没有对应的设置页")
            run.assert_not_called()
            with patch.object(sys, "platform", "darwin"):
                with urlopen(Request(url, method="POST", headers=page), timeout=3) as response:
                    self.assertEqual(response.status, 204)
        self.assertEqual(run.call_args.args[0], ["open", browser_sync.FULL_DISK_ACCESS_SETTINGS])
        self.assertIn("Privacy_AllFiles", browser_sync.FULL_DISK_ACCESS_SETTINGS)

    def post_restart(self, headers=None):
        request_headers = {"Origin": self.base, "X-Bookmark-Sync": "1"}
        request_headers.update(headers or {})
        request = Request(self.base + "/__bookmarks/restart", method="POST", headers=request_headers)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_restart_schedules_existing_mechanism_after_response_on_windows_and_macos(self):
        send_json = bookmark_server.Handler.send_json

        def record_response(handler, status, data):
            send_json(handler, status, data)
            sequence.append("response")

        def schedule():
            sequence.append(("restart", bookmark_server.BOOKMARK_SYNC_LOCK.locked()))
            scheduled.set()

        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform):
                sequence = []
                scheduled = threading.Event()
                with patch.object(sys, "platform", platform), patch.object(
                    bookmark_server.Handler, "send_json", record_response
                ), patch.object(self.server, "schedule_restart", side_effect=schedule) as restart:
                    status, data = self.post_restart()
                    self.assertTrue(scheduled.wait(timeout=1))
                    acquired = bookmark_server.BOOKMARK_SYNC_LOCK.acquire(timeout=1)
                    self.assertTrue(acquired)
                    if acquired:
                        bookmark_server.BOOKMARK_SYNC_LOCK.release()
                self.assertEqual(status, 200)
                self.assertEqual(data, {"ok": True, "instance": self.server.instance})
                self.assertEqual(sequence, ["response", ("restart", True)])
                restart.assert_called_once_with()
        self.sync.assert_not_called()

    def test_restart_rejects_foreign_origins_and_missing_action_header(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform), patch.object(sys, "platform", platform), patch.object(self.server, "schedule_restart") as restart:
                for headers in (
                    {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Origin": ""},
                    {"Host": "evil.example", "Origin": "http://evil.example"},
                    {"X-Bookmark-Sync": ""},
                ):
                    with self.subTest(headers=headers):
                        status, data = self.post_restart(headers)
                        self.assertEqual(status, 403)
                        self.assertFalse(data["ok"])
                restart.assert_not_called()

    def test_restart_does_not_interrupt_sync_or_repeat_restart(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform), patch.object(sys, "platform", platform), patch.object(self.server, "schedule_restart") as restart:
                self.server.restarting = False
                with bookmark_server.BOOKMARK_SYNC_LOCK:
                    status, data = self.post_restart()
                    self.assertEqual(status, 409)
                    self.assertIn("同步正在进行", data["message"])
                self.server.restarting = True
                status, data = self.post_restart()
                self.assertEqual(status, 409)
                self.assertIn("正在重启", data["message"])
                restart.assert_not_called()
                acquired = bookmark_server.BOOKMARK_SYNC_LOCK.acquire(timeout=1)
                self.assertTrue(acquired)
                if acquired:
                    bookmark_server.BOOKMARK_SYNC_LOCK.release()

    def test_restart_is_not_available_on_unsupported_platform(self):
        with patch.object(sys, "platform", "linux"), patch.object(self.server, "schedule_restart") as restart:
            request = Request(self.base + "/__bookmarks/restart", method="POST",
                              headers={"Origin": self.base, "X-Bookmark-Sync": "1"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            caught.exception.close()
        self.assertEqual(caught.exception.code, 404)
        restart.assert_not_called()
