import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_manage", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class UpdateStatusTests(TestCase):
    def test_reports_fast_forward_update(self):
        with patch.object(manage, "git_output", side_effect=[
            "main", "", "", "current000", "remote111", "current000"
        ]):
            status = manage.repository_update_status()
        self.assertEqual(status, {
            "available": True,
            "can_update": True,
            "current": "current",
            "remote": "remote1",
            "version": "v1.0.0",
        })

    def test_declines_update_when_tracked_changes_exist(self):
        with patch.object(manage, "git_output", side_effect=["main", " M web/js/app.js"]):
            status = manage.repository_update_status()
        self.assertFalse(status["available"])
        self.assertFalse(status["can_update"])
        self.assertEqual(status["reason"], "存在未提交的本地代码修改")
        self.assertEqual(status["version"], "v1.0.0")

    def test_updates_with_fast_forward_only(self):
        with patch.object(manage, "repository_update_status", return_value={
            "available": True, "can_update": True, "current": "old1234", "remote": "new5678"
        }), patch.object(manage, "git_output", side_effect=["", "new5678"] ) as git:
            result = manage.update_repository()
        self.assertEqual(result, {"ok": True, "updated": True, "previous": "old1234", "current": "new5678"})
        git.assert_any_call("merge", "--ff-only", "origin/main")
