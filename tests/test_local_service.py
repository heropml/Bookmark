import http.client
import importlib.util
import json
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
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
                self.assertEqual(json.loads(body)["can_restart"], platform in ("win32", "darwin"))

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


class CrossSiteTests(ServiceTestCase):
    def test_every_reply_forbids_embedding_by_other_sites(self):
        # <script src="http://127.0.0.1:8765/data.js"> on another site would otherwise read bookmarks.
        for path in ("/data.js", "/index.html", "/js/app.js", "/__service", "/missing.js"):
            with self.subTest(path=path):
                _, headers, _ = self.request("GET", path)
                self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")

    def test_other_sites_cannot_fetch_or_embed_but_may_link_to_the_page(self):
        for site in ("cross-site", "same-site"):
            for path in ("/data.js", "/__service", "/__bookmarks/backups"):
                with self.subTest(site=site, path=path):
                    status, _, body = self.request("GET", path, {"Sec-Fetch-Site": site, "Sec-Fetch-Mode": "no-cors"})
                    self.assertEqual(status, 403)
                    self.assertNotIn(b"private", body)
            status, _, _ = self.request("HEAD", "/data.js", {"Sec-Fetch-Site": site, "Sec-Fetch-Mode": "no-cors"})
            self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/index.html", {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})
        self.assertEqual(status, 200)
        for site in ("same-origin", "none"):
            status, _, body = self.request("GET", "/data.js", {"Sec-Fetch-Site": site})
            self.assertEqual(status, 200)
            self.assertIn(b"private", body)


class AssetCacheTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        (self.web / "css").mkdir()
        (self.web / "css/base.css").write_text("body{}", encoding="utf-8")
        (self.web / "index.html").write_text(
            '<html><link rel="stylesheet" href="css/base.css" /><script defer src="js/app.js"></script>'
            '<script src="js/missing.js"></script><img src="https://example.com/a.png"></html>', encoding="utf-8")

    def test_page_names_each_asset_by_its_current_version(self):
        status, headers, body = self.request("GET", "/")
        page = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(int(headers["Content-Length"]), len(body))
        stamp = manage.file_stamp(self.web / "js/app.js")
        self.assertIn(f'src="js/app.js?v={stamp}"', page)
        self.assertIn('href="css/base.css?v=', page)
        self.assertIn('src="js/missing.js"', page, "不存在的文件保持原地址")
        self.assertIn('src="https://example.com/a.png"', page)
        status, _, body = self.request("GET", "/", {"If-None-Match": headers["ETag"]})
        self.assertEqual((status, body), (304, b""))

    def test_stamped_assets_are_cached_for_good_and_changes_get_new_addresses(self):
        _, _, body = self.request("GET", "/index.html")
        stamp = manage.file_stamp(self.web / "js/app.js")
        status, headers, _ = self.request("GET", f"/js/app.js?v={stamp}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], manage.IMMUTABLE_CACHE)
        for query in ("", "?v=old", "?v=" + stamp + "x"):
            with self.subTest(query=query):
                _, headers, _ = self.request("GET", "/js/app.js" + query)
                self.assertEqual(headers["Cache-Control"], "no-cache")
        _, before, _ = self.request("GET", "/index.html")
        (self.web / "js/app.js").write_text("changed();", encoding="utf-8")
        status, after, body = self.request("GET", "/index.html", {"If-None-Match": before["ETag"]})
        self.assertEqual(status, 200, "资源变化后页面也必须重新下载")
        self.assertIn(f'js/app.js?v={manage.file_stamp(self.web / "js/app.js")}', body.decode("utf-8"))

    def test_one_connection_serves_a_whole_page_load(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        self.addCleanup(connection.close)
        for path in ("/index.html", "/css/base.css", "/js/app.js", "/data.js", "/__service"):
            with self.subTest(path=path):
                connection.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
                self.assertFalse(response.will_close, "静态文件和接口应保持连接")

    def test_posts_close_their_connection(self):
        status, headers, _ = self.request("POST", "/__window_state", {"Origin": "https://evil.example"}, "x" * 50)
        self.assertEqual(status, 403)
        self.assertEqual(headers.get("Connection"), "close")


class FaviconTests(ServiceTestCase):
    def test_favicon_is_revalidated_instead_of_resent(self):
        icon = self.web / "icon.ico"
        icon.write_bytes(b"\0" * 2048)
        icons = SimpleNamespace(icon_path=lambda skin: icon)
        with patch.dict("sys.modules", {"shortcut": icons}):
            status, headers, body = self.request("GET", "/__favicon?skin=aurora")
            self.assertEqual((status, len(body)), (200, 2048))
            self.assertEqual(headers["Cache-Control"], "no-cache")
            status, _, body = self.request("GET", "/__favicon?skin=aurora", {"If-None-Match": headers["ETag"]})
        self.assertEqual((status, body), (304, b""))


class WeatherCacheTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        manage.WEATHER_CACHE.clear()
        self.addCleanup(manage.WEATHER_CACHE.clear)

    def test_tabs_opened_together_share_one_upstream_lookup(self):
        with patch.object(manage, "weather_from_uapis", return_value=(21.5, 0, "晴")) as upstream:
            for _ in range(3):
                status, headers, body = self.request("GET", "/__weather?city=%E6%9D%AD%E5%B7%9E")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["current"], {"temperature_2m": 21.5, "weather_code": 0})
                self.assertEqual(headers["X-Weather-Source"], "uapis")
            self.assertEqual(upstream.call_count, 1)
            self.request("GET", "/__weather?city=%E5%AE%81%E6%B3%A2")
            self.assertEqual(upstream.call_count, 2, "不同城市各自查询")
            with patch.object(manage, "WEATHER_CACHE_SECONDS", 0):
                self.request("GET", "/__weather?city=%E6%9D%AD%E5%B7%9E")
            self.assertEqual(upstream.call_count, 3, "过期后重新查询")

    def test_failures_are_not_cached(self):
        with patch.object(manage, "weather_from_uapis", side_effect=OSError), \
                patch.object(manage, "weather_from_open_meteo", side_effect=OSError) as fallback:
            for _ in range(2):
                status, _, _ = self.request("GET", "/__weather?city=x")
                self.assertEqual(status, 502)
        self.assertEqual(fallback.call_count, 2)


class ShortcutIconTests(ServiceTestCase):
    def icons(self, changed, state):
        def set_icon(skin):
            changed.append(skin)
            state[0] += 1
        return SimpleNamespace(set_icon=set_icon, shortcut_state=lambda: state[0])

    def test_repeating_the_same_skin_does_not_rewrite_the_shortcut(self):
        changed = []
        page = {"Origin": self.page}
        with patch.object(manage.sys, "platform", "win32"), \
                patch.dict("sys.modules", {"shortcut": self.icons(changed, [0])}):
            for skin in ("cyber", "cyber", "snow", "snow", "cyber"):
                status, _, _ = self.request("POST", f"/__icon?skin={skin}", page)
                self.assertEqual(status, 204)
        self.assertEqual(changed, ["cyber", "snow", "cyber"])

    def test_shortcut_recreated_elsewhere_gets_the_icon_again(self):
        changed, state = [], [0]
        page = {"Origin": self.page}
        with patch.object(manage.sys, "platform", "win32"), \
                patch.dict("sys.modules", {"shortcut": self.icons(changed, state)}):
            self.request("POST", "/__icon?skin=cyber", page)
            state[0] += 1  # e.g. the installer wrote a fresh shortcut with the default icon
            self.request("POST", "/__icon?skin=cyber", page)
        self.assertEqual(changed, ["cyber", "cyber"])


class StartupTests(TestCase):
    def test_starting_the_service_does_not_wait_for_reverse_dns(self):
        # Reverse DNS for 127.0.0.1 can take many seconds; the service must listen without it.
        with patch("socket.getfqdn", side_effect=AssertionError("reverse DNS lookup")):
            server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.addCleanup(server.server_close)
        self.assertEqual(server.server_name, "127.0.0.1")
        self.assertEqual(server.server_port, server.server_address[1])
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.request("GET", "/__service", headers={"Host": f"127.0.0.1:{server.server_port}"})
        self.assertEqual(connection.getresponse().status, 200)
