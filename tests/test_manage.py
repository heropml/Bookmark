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
            "version": manage.APP_VERSION,
        })

    def test_declines_update_when_tracked_changes_exist(self):
        with patch.object(manage, "git_output", side_effect=["main", " M web/js/app.js"]):
            status = manage.repository_update_status()
        self.assertFalse(status["available"])
        self.assertFalse(status["can_update"])
        self.assertEqual(status["reason"], "存在未提交的本地代码修改")
        self.assertEqual(status["version"], manage.APP_VERSION)

    def test_updates_with_fast_forward_only(self):
        with patch.object(manage, "repository_update_status", return_value={
            "available": True, "can_update": True, "current": "old1234", "remote": "new5678",
            "target": "new5678full", "source": "Gitee"
        }), patch.object(manage, "git_output", side_effect=["", "new5678"] ) as git:
            result = manage.update_repository()
        self.assertEqual(result, {"ok": True, "updated": True, "previous": "old1234", "current": "new5678", "source": "Gitee"})
        git.assert_any_call("merge", "--ff-only", "new5678full")


class BookmarkDataTests(TestCase):
    def test_hosts_never_keep_credentials(self):
        self.assertEqual(manage.host_of("http://admin:secret@192.168.1.1:8080/login"), "192.168.1.1:8080")
        self.assertEqual(manage.host_of("https://user@www.example.com/"), "example.com")
        self.assertEqual(manage.host_of("https://www.example.com/a@b"), "example.com")

    def test_toolbar_folder_is_not_a_category_in_any_language(self):
        template = (
            "<DL><p>\n"
            '    <DT><H3 ADD_DATE="1" PERSONAL_TOOLBAR_FOLDER="true">{}</H3>\n'
            "    <DL><p>\n"
            '        <DT><A HREF="https://a.example/">A</A>\n'
            "        <DT><H3>工作</H3>\n"
            "        <DL><p>\n"
            '            <DT><A HREF="https://b.example/">B</A>\n'
            "        </DL><p>\n"
            "    </DL><p>\n"
            '    <DT><H3>其他收藏</H3>\n'
            "    <DL><p>\n"
            '        <DT><A HREF="https://c.example/">C</A>\n'
            "    </DL><p>\n"
            "</DL><p>\n"
        )
        for toolbar in ("书签栏", "收藏夹栏", "Bookmarks bar", "Favorites bar"):
            with self.subTest(toolbar=toolbar):
                items = manage.parse_html(template.format(toolbar))
                self.assertEqual([(item["title"], item["path"], item["group"]) for item in items], [
                    ("A", "其他", "其他"), ("B", "工作", "工作"), ("C", "其他收藏", "其他收藏"),
                ])

    def test_folder_named_like_the_chinese_toolbar_is_still_skipped_without_the_marker(self):
        items = manage.parse_html('<DL><p>\n<DT><H3>书签栏</H3>\n<DL><p>\n<DT><A HREF="https://a.example/">A</A>\n</DL><p>\n</DL><p>\n')
        self.assertEqual(items[0]["path"], "其他")

    def test_page_data_only_carries_fields_the_page_reads(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder, patch.object(manage, "DATA_JS", Path(folder) / "data.js"):
            item = {"title": "A", "href": "https://a.example/", "path": "工作", "group": "工作", "host": "a.example"}
            manage.write_data([item], "test")
            written = (Path(folder) / "data.js").read_text(encoding="utf-8")
        self.assertEqual(written, 'window.BOOKMARKS = [{"title": "A", "href": "https://a.example/", '
                                  '"path": "工作", "group": "工作", "host": "a.example"}];\n')
