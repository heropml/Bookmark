import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_manage", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class GitOutputTests(TestCase):
    def test_windows_git_commands_do_not_create_console_windows(self):
        result = manage.subprocess.CompletedProcess([], 0, "main\n", "")
        with patch.object(manage.sys, "platform", "win32"), patch.object(
            manage.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True
        ), patch.object(manage.subprocess, "run", return_value=result) as run:
            self.assertEqual(manage.git_output("branch", "--show-current"), "main")
        self.assertEqual(run.call_args.args[0], ["git", "branch", "--show-current"])
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
        self.assertEqual(run.call_args.kwargs["timeout"], manage.GIT_TIMEOUT_SECONDS)
        self.assertEqual(run.call_args.kwargs["stdout"], manage.subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs["stderr"], manage.subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(run.call_args.kwargs["env"]["GCM_INTERACTIVE"], "Never")

    def test_non_windows_git_commands_do_not_use_windows_flags(self):
        for platform in ("darwin", "linux"):
            with self.subTest(platform=platform), patch.object(manage.sys, "platform", platform), patch.object(
                manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess([], 0, "main\n", "")
            ) as run:
                self.assertEqual(manage.git_output("branch", "--show-current"), "main")
                self.assertEqual(run.call_args.kwargs.get("creationflags", 0), 0)

    def test_git_failures_and_timeouts_keep_existing_errors(self):
        with patch.object(manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess([], 1, "", "failed")):
            with self.assertRaisesRegex(manage.UpdateError, "无法检查更新"):
                manage.git_output("status")
        with patch.object(manage.subprocess, "run", side_effect=manage.subprocess.TimeoutExpired("git", 15)):
            with self.assertRaisesRegex(manage.UpdateError, "无法连接更新服务"):
                manage.git_output("status")


class UpdateStatusTests(TestCase):
    def test_reports_fast_forward_update(self):
        with patch.object(manage, "git_output", side_effect=[
            "main", "", "", "remote111", "current000", "current000"
        ]):
            status = manage.repository_update_status()
        self.assertEqual(status, {
            "available": True,
            "can_update": True,
            "current": "current",
            "remote": "remote1",
            "target": "remote111",
            "source": "Gitee",
            "version": "v1.0.7",
        })

    def test_declines_update_when_tracked_changes_exist(self):
        with patch.object(manage, "git_output", side_effect=["main", " M web/js/app.js"]):
            status = manage.repository_update_status()
        self.assertFalse(status["available"])
        self.assertFalse(status["can_update"])
        self.assertEqual(status["reason"], "存在未提交的本地代码修改")
        self.assertEqual(status["version"], "v1.0.7")

    def test_updates_with_fast_forward_only(self):
        with patch.object(manage, "repository_update_status", return_value={
            "available": True, "can_update": True, "current": "old1234", "remote": "new5678",
            "target": "new5678full", "source": "Gitee"
        }), patch.object(manage, "git_output", side_effect=["", "new5678"] ) as git:
            result = manage.update_repository()
        self.assertEqual(result, {"ok": True, "updated": True, "previous": "old1234", "current": "new5678", "source": "Gitee"})
        git.assert_any_call("merge", "--ff-only", "new5678full")
