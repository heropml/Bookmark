import importlib.util
import json
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_progress", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class ProgressTests(TestCase):
    def test_actual_stages_and_source_fallback_precede_git_operations(self):
        events = []
        replies = iter(["main", "", manage.UpdateError("超时"), "", "new", "old", "old", "", "new"])

        def git(*args, **kwargs):
            if "fetch" in args:
                self.assertEqual(events[-1]["stage"], "fetching")
            if "merge" in args:
                self.assertEqual(events[-1]["stage"], "applying")
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return reply

        with patch.object(manage, "git_output", side_effect=git):
            result = manage.update_repository(events.append)
        self.assertTrue(result["updated"])
        self.assertEqual([event["stage"] for event in events], ["waiting", "checking", "fetching", "fetching", "applying"])
        self.assertEqual([event["source"] for event in events if "source" in event], ["Gitee", "GitHub", "GitHub"])
        self.assertIn("切换", events[3]["message"])

    def test_dirty_checkout_never_claims_download_or_apply(self):
        events = []
        with patch.object(manage, "git_output", side_effect=["main", " M app.py"]):
            with self.assertRaisesRegex(manage.UpdateError, "未提交"):
                manage.update_repository(events.append)
        self.assertEqual([event["stage"] for event in events], ["waiting", "checking"])

    def test_disconnected_client_does_not_abort_accepted_upgrade(self):
        handler = Mock()
        handler.server.instance = "old"
        handler.wfile.write.side_effect = BrokenPipeError()
        applied = []

        def upgrade(progress):
            progress({"stage": "checking"})
            progress({"stage": "applying"})
            applied.append(True)
            return {"ok": True, "updated": True}

        with patch.object(manage, "update_repository", side_effect=upgrade):
            manage.Handler.stream_update(handler)
        self.assertEqual(applied, [True])
        handler.server.schedule_restart.assert_called_once()
        handler.wfile.write.assert_called_once()


class ProgressHTTPTests(TestCase):
    def setUp(self):
        self.server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/__update"
        self.restart = patch.object(self.server, "schedule_restart")
        self.schedule = self.restart.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.restart.stop()

    def request(self, streaming=True):
        return Request(self.url, method="POST", headers={"Accept": "application/x-ndjson"} if streaming else {})

    def test_progress_arrives_before_upgrade_finishes(self):
        release = threading.Event()
        completed = threading.Event()

        def upgrade(progress):
            progress({"stage": "fetching", "source": "Gitee", "message": "同步代码中"})
            if not release.wait(3):
                raise manage.UpdateError("test timeout")
            progress({"stage": "applying", "message": "应用代码"})
            completed.set()
            return {"ok": True, "updated": True}

        with patch.object(manage, "update_repository", side_effect=upgrade):
            try:
                with urlopen(self.request(), timeout=2) as response:
                    self.assertEqual(response.headers["Content-Type"], "application/x-ndjson; charset=utf-8")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    event = json.loads(response.readline())
                    self.assertEqual(event, {"type": "progress", "stage": "fetching", "source": "Gitee", "message": "同步代码中"})
                    self.assertFalse(completed.is_set(), "进度必须在操作结束前送达，不能缓冲至最后")
                    self.schedule.assert_not_called()
                    release.set()
                    events = [json.loads(line) for line in response]
            finally:
                release.set()
        self.assertEqual(events[0]["stage"], "applying")
        self.assertEqual(events[1], {"type": "result", "ok": True, "updated": True, "instance": self.server.instance})
        self.schedule.assert_called_once()

    def test_streamed_error_is_explained_and_does_not_restart(self):
        with patch.object(manage, "update_repository", side_effect=manage.UpdateError("证书验证失败", "certificate_error")):
            with urlopen(self.request(), timeout=2) as response:
                events = [json.loads(line) for line in response]
        self.assertEqual(events, [{"type": "error", "message": "证书验证失败", "error": "certificate_error"}])
        self.schedule.assert_not_called()

    def test_no_update_returns_result_without_restart(self):
        with patch.object(manage, "update_repository", return_value={"ok": True, "updated": False}):
            with urlopen(self.request(), timeout=2) as response:
                event = json.load(response)
        self.assertEqual(event["type"], "result")
        self.assertFalse(event["updated"])
        self.schedule.assert_not_called()

    def test_legacy_clients_keep_json_response_and_restart(self):
        with patch.object(manage, "update_repository", return_value={"ok": True, "updated": True}) as upgrade:
            with urlopen(self.request(False), timeout=2) as response:
                result = json.load(response)
                self.assertIn("application/json", response.headers["Content-Type"])
        upgrade.assert_called_once_with()
        self.assertEqual(result, {"ok": True, "updated": True, "instance": self.server.instance})
        self.schedule.assert_called_once()

    def test_legacy_clients_keep_http_error_response(self):
        with patch.object(manage, "update_repository", side_effect=manage.UpdateError("本地修改")):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.request(False), timeout=2)
        with caught.exception as response:
            self.assertEqual(response.code, 409)
            self.assertEqual(json.load(response), {"ok": False, "message": "本地修改"})
        self.schedule.assert_not_called()
