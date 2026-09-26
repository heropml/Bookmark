import http.client
import importlib.util
import json
import os
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_local_service", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class ServiceTestCase(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.web = Path(folder.name) / "web"
        (self.web / "js").mkdir(parents=True)
        (self.web / "index.html").write_text("<html>书签</html>", encoding="utf-8")
        (self.web / "data.js").write_text('window.BOOKMARKS = [{"title": "private"}];', encoding="utf-8")
        (self.web / "js/app.js").write_text("render();", encoding="utf-8")
        self.window_state = Path(folder.name) / "window-state.json"
        for name, value in (("WEB_ROOT", self.web), ("WINDOW_STATE", self.window_state)):
            patcher = patch.object(manage, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port
        self.page = f"http://127.0.0.1:{self.port}"

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()


class RequestOriginTests(ServiceTestCase):
    def test_other_host_names_cannot_read_private_bookmarks(self):
        # A rebinding attacker's page sends its own name as Host while reaching 127.0.0.1.
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                status, _, body = self.request(method, "/data.js", {"Host": f"attacker.example:{self.port}"})
                self.assertEqual(status, 403)
                self.assertNotIn(b"private", body)
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            with self.subTest(host=host):
                status, _, body = self.request("GET", "/data.js", {"Host": host})
                self.assertEqual(status, 200)
                self.assertIn(b"private", body)

    def test_window_size_is_saved_only_from_this_page(self):
        body = json.dumps({"width": 800, "height": 600})
        for origin in ("https://evil.example", "null", None):
            with self.subTest(origin=origin):
                headers = {"Content-Type": "text/plain"} if origin is None else {"Origin": origin, "Content-Type": "text/plain"}
                status, _, _ = self.request("POST", "/__window_state", headers, body)
                self.assertEqual(status, 403)
        self.assertFalse(self.window_state.exists())
        status, _, _ = self.request("POST", "/__window_state", {"Origin": self.page, "Content-Type": "application/json"}, body)
        self.assertEqual(status, 204)
        self.assertEqual(json.loads(self.window_state.read_text(encoding="utf-8")), {"width": 800, "height": 600, "maximized": False})


class StaticRevalidationTests(ServiceTestCase):
    def test_unchanged_files_answer_not_modified(self):
        for path in ("/js/app.js", "/index.html", "/"):
            with self.subTest(path=path):
                status, headers, body = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Cache-Control"], "no-cache")
                self.assertTrue(body)
                status, headers, body = self.request("GET", path, {"If-None-Match": headers["ETag"]})
                self.assertEqual(status, 304)
                self.assertEqual(body, b"")

    def test_rewritten_file_is_sent_again_even_with_an_older_timestamp(self):
        script = self.web / "js/app.js"
        _, headers, _ = self.request("GET", "/js/app.js")
        stat = script.stat()
        # Installers can restore older timestamps; same size, so only the ETag notices the change.
        script.write_text("update();", encoding="utf-8")
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns - 5_000_000_000))
        status, headers, body = self.request("GET", "/js/app.js", {"If-None-Match": headers["ETag"]})
        self.assertEqual(status, 200)
        self.assertEqual(body, b"update();")

    def test_restart_capability_matches_supported_platform(self):
        for platform in ("darwin", "win32", "linux"):
            with self.subTest(platform=platform), patch.object(manage.sys, "platform", platform):
                status, _, body = self.request("GET", "/__service")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["can_restart"], platform == "darwin")

    def test_service_replies_stay_uncached(self):
        status, headers, _ = self.request("GET", "/__service")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("ETag", headers)


class UpdateCheckCacheTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        for name, kwargs in (("installed_version", {"return_value": manage.APP_VERSION}),
                             ("repository_update_status", {"return_value": {"available": False, "version": manage.APP_VERSION}})):
            patcher = patch.object(manage, name, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
        self.check = mock

    def check_update(self, query="", headers=None):
        status, _, body = self.request("GET", "/__update" + query, headers)
        return status, json.loads(body)

    def test_pages_opened_together_share_one_check(self):
        for _ in range(3):
            self.assertEqual(self.check_update(), (200, {"available": False, "version": manage.APP_VERSION}))
        self.check.assert_called_once_with()
        with patch.object(manage, "UPDATE_CACHE_SECONDS", 0):
            self.check_update()
        self.assertEqual(self.check.call_count, 2)

    def test_only_this_page_can_ask_to_check_again(self):
        self.check_update()
        self.check_update("?refresh=1", {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(self.check.call_count, 1)
        self.check_update("?refresh=1", {"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(self.check.call_count, 2)

    def test_failed_check_is_repeated_after_a_short_pause(self):
        self.check.side_effect = manage.UpdateError("Gitee：证书验证失败", "certificate_error")
        for _ in range(2):
            status, result = self.check_update()
            self.assertEqual(status, 503)
            self.assertEqual(result["error"], "certificate_error")
        self.check.assert_called_once_with()
        with patch.object(manage, "UPDATE_RETRY_SECONDS", 0):
            self.check_update()
        self.assertEqual(self.check.call_count, 2)

    def test_an_upgrade_attempt_makes_the_previous_check_stale(self):
        self.check_update()
        with patch.object(manage, "update_repository", return_value={"ok": True, "updated": False}):
            status, _, _ = self.request("POST", "/__update", {"Origin": self.page})
        self.assertEqual(status, 200)
        self.check_update()
        self.assertEqual(self.check.call_count, 2)
