import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_sync_manage", ROOT / "scripts/manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class DirectoryServiceTests(TestCase):
    def test_macos_sync_failure_explains_full_disk_access(self):
        with patch.object(manage.sys, "platform", "darwin"):
            message = manage.sync_failure_message("chrome")
        self.assertIn("Chrome", message)
        self.assertIn("完全磁盘访问权限", message)
        self.assertIn("/Applications/Bookmark.app", message)

    def test_directory_identity_is_stable_distinct_and_not_a_plain_path(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "源码"
            with patch.object(manage, "ROOT", first):
                key = manage.installation_id()
                self.assertEqual(key, manage.installation_id())
                self.assertEqual(len(key), 64)
                self.assertNotIn(str(first), key)
            with patch.object(manage, "ROOT", Path(folder) / "安装"):
                self.assertNotEqual(key, manage.installation_id())

    def test_reuses_own_service_even_if_a_lower_port_is_free(self):
        with patch.object(manage, "port_in_use", side_effect=lambda port: port == manage.PORT + 2), patch.object(manage, "page_ok", return_value=True):
            self.assertEqual(manage.pick_port(), manage.PORT + 2)

    def test_foreign_or_legacy_service_is_not_reused_or_stopped(self):
        with patch.object(manage, "port_in_use", side_effect=lambda port: port == manage.PORT), patch.object(manage, "page_ok", return_value=False), patch.object(manage.subprocess, "Popen") as spawn:
            self.assertEqual(manage.pick_port(), manage.PORT + 1)
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
        for identity in (manage.installation_id(), "another-installation", None):
            with self.subTest(identity=identity):
                service = {"version": "v1.0.4", "installation": identity}
                replies = [response(b'<!doctype html><html>'), response(manage.HEALTH_RESPONSE), response(json.dumps(service).encode())]
                with patch("urllib.request.urlopen", side_effect=replies):
                    self.assertEqual(manage.page_ok(8765), identity == manage.installation_id())


class BookmarkSyncHTTPTests(TestCase):
    def setUp(self):
        self.server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.platform = patch.object(manage.sys, "platform", "win32")
        self.platform.start()
        self.sync_patch = patch.object(manage, "sync_chrome", return_value=[{}, {}])
        self.sync = self.sync_patch.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.sync_patch.stop()
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
            self.assertEqual(json.load(response), {"browsers": ["chrome", "edge"]})
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.sync.assert_not_called()

    def test_confirmed_sync_uses_selected_browser_and_returns_count(self):
        status, data = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "count": 2, "browser": "chrome"})
        self.sync.assert_called_once_with()
        with patch.object(manage, "sync_edge", return_value=[{}]) as edge:
            self.assertEqual(self.post({"browser": "edge", "confirmed": True})[0], 200)
            edge.assert_called_once_with()

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
        with manage.BOOKMARK_SYNC_LOCK:
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
            acquired = manage.BOOKMARK_SYNC_LOCK.acquire(timeout=1)
            self.assertTrue(acquired)
            if acquired:
                manage.BOOKMARK_SYNC_LOCK.release()

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
            with patch.dict(manage.os.environ, {"LOCALAPPDATA": str(root / "profiles")}), patch.object(manage, "SRC", data_dir / "bookmarks.html"), patch.object(manage, "DATA_JS", web / "data.js"):
                code, result = self.post()
            self.assertEqual(code, 200)
            self.assertEqual(result["count"], 1)
            self.assertIn("同步测试", (web / "data.js").read_text(encoding="utf-8"))
            self.assertEqual(browser_file.read_text(encoding="utf-8"), source)

    def test_macos_offers_existing_chrome_and_safari_implementation(self):
        with patch.object(manage.sys, "platform", "darwin"), patch.object(manage, "sync_safari", return_value=[{}]) as safari:
            self.assertEqual(manage.supported_sync_browsers(), ["chrome", "safari"])
            self.assertEqual(self.post({"browser": "safari", "confirmed": True})[0], 200)
            safari.assert_called_once_with()
