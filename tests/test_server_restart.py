import importlib.util
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_restart", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class RestartTests(TestCase):
    def test_installed_version_reads_disk_without_executing_it(self):
        with patch.object(Path, "read_text", return_value='APP_VERSION = "v9.0.0"\nraise RuntimeError()'):
            self.assertEqual(manage.installed_version(), "v9.0.0")
        with patch.object(Path, "read_text", return_value="not a version"):
            with self.assertRaises(manage.UpdateError):
                manage.installed_version()

    def test_listener_is_closed_before_replacing_only_this_service(self):
        order = []
        server = Mock(restarting=True)
        server.serve_forever.side_effect = lambda: order.append("serve")
        server.server_close.side_effect = lambda: order.append("close")
        with patch.object(manage.sys, "platform", "darwin"), patch.object(manage, "BookmarkServer", return_value=server), patch.object(manage.os, "execv", side_effect=lambda *args: order.append("exec")) as execute:
            manage.serve(8799)
        self.assertEqual(order, ["serve", "close", "exec"])
        execute.assert_called_once_with(manage.sys.executable, [
            manage.sys.executable, "-X", "utf8", str(Path(manage.__file__).resolve()), "--serve", "8799",
        ])

    def test_windows_closes_listener_then_starts_hidden_replacement(self):
        order = []
        server = Mock(restarting=True)
        server.server_close.side_effect = lambda: order.append("close")
        with patch.object(manage.sys, "platform", "win32"), patch.object(manage, "BookmarkServer", return_value=server), patch.object(manage, "start_hidden_server", side_effect=lambda port: order.append(port)), patch.object(manage.os, "execv") as execute:
            manage.serve(8799)
        self.assertEqual(order, ["close", 8799])
        execute.assert_not_called()

    def test_windows_spawn_keeps_space_paths_in_one_argument_and_hides_console(self):
        with patch.object(manage.sys, "platform", "win32"), patch.object(manage, "__file__", "D:/Bookmark demo/scripts/manage.py"), patch.object(manage.subprocess, "Popen") as spawn, patch.object(manage.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            manage.start_hidden_server(8799)
        self.assertEqual(spawn.call_args.args[0][-3:], [str(Path("D:/Bookmark demo/scripts/manage.py").resolve()), "--serve", "8799"])
        self.assertEqual(spawn.call_args.kwargs["creationflags"], 0x08000000)

    def test_worker_only_stops_loop_and_does_not_replace_during_interpreter_exit(self):
        server = Mock()
        with patch.object(manage.time, "sleep"), patch.object(manage.os, "execv") as execute:
            manage.restart_after_update(server)
        server.shutdown.assert_called_once()
        server.server_close.assert_not_called()
        execute.assert_not_called()

    def test_duplicate_restart_requests_schedule_one_replacement(self):
        server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.addCleanup(server.server_close)
        with patch.object(manage.threading, "Thread") as worker:
            server.schedule_restart()
            server.schedule_restart()
        self.assertTrue(server.restarting)
        worker.assert_called_once_with(target=manage.restart_after_update, args=(server,), daemon=False)
        worker.return_value.start.assert_called_once()

    def test_simultaneous_clients_cannot_start_multiple_replacements(self):
        server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.addCleanup(server.server_close)
        started = threading.Event()
        with patch.object(manage, "restart_after_update", side_effect=lambda _: started.set()) as restart:
            with ThreadPoolExecutor(max_workers=8) as clients:
                list(clients.map(lambda _: server.schedule_restart(), range(20)))
            self.assertTrue(started.wait(2))
            restart.assert_called_once_with(server)


class RestartHTTPTests(TestCase):
    def setUp(self):
        self.server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.restart = patch.object(self.server, "schedule_restart")
        self.schedule = self.restart.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.restart.stop()

    def read_json(self, path):
        with urlopen(self.base + path, timeout=2) as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            return json.load(response)

    def test_page_update_check_restarts_stale_backend_even_with_local_changes(self):
        with patch.object(manage, "installed_version", return_value="v9.0.0"), patch.object(manage, "repository_update_status") as git:
            result = self.read_json("/__update")
        self.assertTrue(result["restarting"])
        self.assertEqual(result["instance"], self.server.instance)
        self.assertEqual(result["version"], manage.APP_VERSION)
        self.schedule.assert_called_once()
        git.assert_not_called()

    def test_same_version_keeps_normal_update_check_without_restart(self):
        status = {"available": False, "version": manage.APP_VERSION}
        with patch.object(manage, "installed_version", return_value=manage.APP_VERSION), patch.object(manage, "repository_update_status", return_value=status):
            self.assertEqual(self.read_json("/__update"), status)
        self.schedule.assert_not_called()

    def test_service_readiness_has_instance_without_changing_legacy_health_response(self):
        result = self.read_json("/__service")
        self.assertEqual(result, {
            "version": manage.APP_VERSION, "instance": self.server.instance,
            "installation": manage.installation_id(),
        })
        with urlopen(self.base + "/__health", timeout=2) as response:
            self.assertEqual(response.read(), manage.HEALTH_RESPONSE)
        self.schedule.assert_not_called()

    def test_multiple_pages_share_one_healthy_service(self):
        with patch.object(manage, "installed_version", return_value=manage.APP_VERSION), patch.object(manage, "repository_update_status", return_value={"available": False}):
            def visit(_):
                self.read_json("/__update")
                return self.read_json("/__service")["instance"]
            with ThreadPoolExecutor(max_workers=6) as clients:
                instances = list(clients.map(visit, range(6)))
        self.assertEqual(set(instances), {self.server.instance})
        self.schedule.assert_not_called()

    def test_version_probe_error_does_not_restart(self):
        from urllib.error import HTTPError
        with patch.object(manage, "installed_version", side_effect=OSError("unreadable")):
            with self.assertRaises(HTTPError) as caught:
                self.read_json("/__update")
        self.assertEqual(caught.exception.code, 503)
        self.schedule.assert_not_called()

    def test_certificate_error_is_exposed_without_restarting_service(self):
        from urllib.error import HTTPError
        with patch.object(manage, "repository_update_status", side_effect=manage.UpdateError("Gitee：证书验证失败", "certificate_error")):
            with self.assertRaises(HTTPError) as caught:
                self.read_json("/__update")
        self.assertEqual(caught.exception.code, 503)
        with caught.exception as response:
            result = json.load(response)
        self.assertEqual(result["error"], "certificate_error")
        self.assertIn("证书验证失败", result["reason"])
        self.schedule.assert_not_called()
