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


class BookmarkParserTests(TestCase):
    def paths(self, text):
        return [(item["title"], item["path"]) for item in manage.parse_html(text)]

    def test_exports_on_one_line_or_with_other_attribute_orders_are_read(self):
        one_line = ('<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p><DT><H3>开发</H3><DL><p>'
                    '<DT><A HREF="https://a.example/">A</A><DT><A HREF="https://b.example/">B &amp; C</A>'
                    '</DL><p><DT><A HREF="https://c.example/">D</A></DL><p>')
        self.assertEqual(self.paths(one_line), [("A", "开发"), ("B & C", "开发"), ("D", "其他")])
        self.assertEqual(self.paths('<DL><p>\n<DT><a add_date="1" href=\'https://x.example/\'>X</a>\n</DL>'),
                         [("X", "其他")])
        split = '<DL><p>\n<DT><H3 ADD_DATE="1"\n   LAST_MODIFIED="2">工作\n</H3>\n<DL><p>\n<DT><A\n HREF="https://w.example/">W</A>\n</DL><p>\n</DL>'
        self.assertEqual(self.paths(split), [("W", "工作")])

    def test_unclosed_links_empty_folders_and_links_without_address(self):
        text = ('<DL><DT><H3>空文件夹</H3><DT><A HREF="https://e.example">E</A>'
                '<DT><H3>F</H3><DL><DT><A HREF="https://f.example">F1<DT><A>无地址</A><DT><A HREF="  ">空白</A></DL></DL>')
        self.assertEqual(self.paths(text), [("E", "其他"), ("F1", "F")])

    def test_duplicates_are_skipped_in_page_data_without_rewriting_the_source(self):
        items = manage.parse_html('<DL><DT><A HREF="https://www.Example.com/a/">A</A><DT><H3>X</H3><DL>'
                                  '<DT><A HREF="https://example.com/a">dup</A><DT><A HREF="https://example.com/b">B</A></DL></DL>')
        kept, dropped = manage.dedupe_items(items)
        self.assertEqual(([item["title"] for item in kept], dropped), (["A", "B"], 1))


class BuildTests(TestCase):
    def setUp(self):
        import tempfile

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / "bookmarks.html"
        self.data = self.root / "data.js"
        for name, value in (("SRC", self.source), ("EXAMPLE_SRC", self.root / "example.html"), ("DATA_JS", self.data)):
            patcher = patch.object(manage, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source.write_text(manage.render_bookmarks_html([
            {"title": "A", "href": "https://a.example/", "path": "工作", "group": "工作", "host": "a.example"},
            {"title": "A again", "href": "https://a.example", "path": "其他", "group": "其他", "host": "a.example"},
        ]), encoding="utf-8")
        self.before = self.source.read_bytes()

    def test_build_skips_duplicates_but_keeps_the_source_file_exact(self):
        self.assertEqual([item["title"] for item in manage.build()], ["A"])
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_launch_rebuilds_only_when_source_or_code_changed(self):
        import os

        manage.build()
        with patch.object(manage, "build", wraps=manage.build) as build:
            manage.build_if_stale()
            build.assert_not_called()
            stat = self.source.stat()
            os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            manage.build_if_stale()
            self.assertEqual(build.call_count, 1, "书签源变化后重新生成")
            manage.build_if_stale()
            self.assertEqual(build.call_count, 1)
            with patch.object(manage, "APP_VERSION", "v99.0.0"):
                manage.build_if_stale()
            self.assertEqual(build.call_count, 2, "程序版本变化后重新生成")
            self.data.unlink()
            manage.build_if_stale()
            self.assertEqual(build.call_count, 3, "缺少 data.js 时重新生成")

    def test_unchanged_page_data_keeps_its_timestamp(self):
        import os

        manage.build()
        os.utime(self.data, ns=(1_000_000_000, 1_000_000_000))
        manage.build()
        self.assertEqual(self.data.stat().st_mtime_ns, 1_000_000_000, "内容不变时不改写，浏览器缓存仍有效")
        self.source.write_text(manage.render_bookmarks_html([
            {"title": "B", "href": "https://b.example/", "path": "工作", "group": "工作", "host": "b.example"},
        ]), encoding="utf-8")
        manage.build()
        self.assertIn('"title": "B"', self.data.read_text(encoding="utf-8"))
        self.assertEqual(list(self.root.glob(".data.js.*.tmp")), [])

    def test_html_without_bookmarks_never_replaces_the_current_page(self):
        manage.build()
        page = self.data.read_bytes()
        empty = self.root / "export.html"
        for text in ("<html><body>not a bookmark export</body></html>", ""):
            with self.subTest(text=text):
                empty.write_text(text, encoding="utf-8")
                with self.assertRaises(SystemExit):
                    manage.replace_src(empty)
                self.assertEqual(self.source.read_bytes(), self.before)
                self.assertEqual(self.data.read_bytes(), page)
        self.assertFalse((self.root / ".bookmark-backups").exists())

    def test_backup_counts_are_read_cheaply_and_match_the_parser(self):
        manage.build()
        self.source.write_text(manage.render_bookmarks_html([
            {"title": "C", "href": "https://c.example/", "path": "其他", "group": "其他", "host": "c.example"},
        ]), encoding="utf-8")
        manage.replace_bookmark_source(self.source.read_text(encoding="utf-8") + "\n")
        backup = manage.backup_files()[0]
        self.assertEqual(manage.bookmark_backups()[0]["count"], len(manage.parse_html(backup.read_text(encoding="utf-8"))))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("cached")):
            self.assertEqual(manage.bookmark_backups()[0]["count"], 1)


class PickerTests(TestCase):
    def test_macos_uses_the_native_picker_from_any_thread(self):
        result = manage.subprocess.CompletedProcess([], 0, "/Users/me/Downloads/bookmarks.html\n", "")
        with patch.object(manage.sys, "platform", "darwin"), patch.object(manage.subprocess, "run", return_value=result) as run:
            self.assertEqual(manage.pick_html(), Path("/Users/me/Downloads/bookmarks.html"))
        self.assertEqual(run.call_args.args[0][0], "osascript")
        cancelled = manage.subprocess.CompletedProcess([], 1, "", "")
        with patch.object(manage.sys, "platform", "darwin"), patch.object(manage.subprocess, "run", return_value=cancelled):
            self.assertIsNone(manage.pick_html())

    def test_missing_tkinter_is_a_reported_sync_failure(self):
        with patch.object(manage.sys, "platform", "win32"), patch.dict("sys.modules", {"tkinter": None}):
            with self.assertRaises(SystemExit):
                manage.pick_html()
