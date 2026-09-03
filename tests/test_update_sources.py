import importlib.util
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_sources", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class UpdateSourceTests(TestCase):
    def test_source_order_and_anonymous_https_do_not_depend_on_remotes(self):
        self.assertEqual(manage.UPDATE_SOURCES, (
            ("Gitee", "https://gitee.com/heropml/Bookmark.git"),
            ("GitHub", "https://github.com/heropml/Bookmark.git"),
        ))

    def test_gitee_success_does_not_contact_github(self):
        with patch.object(manage, "git_output", side_effect=["main", "", "", "same", "same"]) as git:
            status = manage.repository_update_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["source"], "Gitee")
        fetches = [call.args for call in git.call_args_list if "fetch" in call.args]
        self.assertEqual(len(fetches), 1)
        self.assertEqual(fetches[0], (
            "-c", "http.proxy=", "-c", "http.https://gitee.com.proxy=",
            "fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
            manage.UPDATE_SOURCES[0][1], "+refs/heads/main:refs/bookmark-updates/gitee",
        ))
        self.assertEqual(git.call_args_list[2].kwargs, {"network_url": manage.UPDATE_SOURCES[0][1]})

    def test_unavailable_gitee_falls_back_to_github_and_pins_full_commit(self):
        with patch.object(manage, "git_output", side_effect=[
            "main", "", manage.UpdateError("超时"), "", "new1234full", "old1234full", "old1234full",
        ]) as git:
            status = manage.repository_update_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["source"], "GitHub")
        self.assertEqual(status["target"], "new1234full")
        git.assert_any_call("fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
                            manage.UPDATE_SOURCES[1][1], "+refs/heads/main:refs/bookmark-updates/github",
                            network_url=manage.UPDATE_SOURCES[1][1])

    def test_all_sources_failing_never_use_stale_refs_or_merge(self):
        with patch.object(manage, "git_output", side_effect=[
            "main", "", manage.UpdateError("超时"), manage.UpdateError("连接失败"),
        ]) as git:
            with self.assertRaisesRegex(manage.UpdateError, "所有更新源均不可用.*Gitee.*GitHub"):
                manage.update_repository()
        self.assertFalse(any("rev-parse" in call.args or "merge" in call.args for call in git.call_args_list))

    def test_wrong_branch_or_dirty_worktree_never_contact_sources(self):
        for replies in (["feature"], ["main", " M scripts/manage.py"]):
            with self.subTest(replies=replies), patch.object(manage, "git_output", side_effect=replies) as git:
                status = manage.repository_update_status()
                self.assertFalse(status["can_update"])
                self.assertFalse(any("fetch" in call.args for call in git.call_args_list))

    def test_local_ahead_or_diverged_never_downgrades_or_tries_second_source(self):
        for base, reason in (("remote", "领先"), ("ancestor", "分叉")):
            with self.subTest(base=base), patch.object(manage, "git_output", side_effect=[
                "main", "", "", "remote", "local", base,
            ]) as git:
                with self.assertRaisesRegex(manage.UpdateError, reason):
                    manage.update_repository()
                self.assertEqual(sum("fetch" in call.args for call in git.call_args_list), 1)
                self.assertFalse(any("merge" in call.args for call in git.call_args_list))

    def test_zip_installation_does_not_attempt_git(self):
        status = {"available": True, "can_update": True, "mode": "archive"}
        with tempfile.TemporaryDirectory() as directory, patch.object(manage, "ROOT", Path(directory)), patch.object(manage, "git_output") as git, patch.object(manage.archive_update, "update_status", return_value=status) as check:
            self.assertEqual(manage.repository_update_status(), status)
        check.assert_called_once_with(manage.APP_VERSION, None)
        git.assert_not_called()

    def test_git_marker_file_does_not_fall_back_to_archive_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(manage, "ROOT", Path(directory)), patch.object(manage.archive_update, "update_status") as archive:
            (Path(directory) / ".git").write_text("gitdir: /another/worktree", encoding="utf-8")
            with self.assertRaisesRegex(manage.UpdateError, "不支持在线升级"):
                manage.repository_update_status()
        archive.assert_not_called()

    def test_zip_install_and_errors_use_existing_upgrade_response_contract(self):
        result = {"ok": True, "updated": True, "mode": "archive"}
        with tempfile.TemporaryDirectory() as directory, patch.object(manage, "ROOT", Path(directory)), patch.object(manage, "git_output") as git, patch.object(manage.archive_update, "install", return_value=result) as install:
            self.assertEqual(manage.update_repository(), result)
            install.assert_called_once_with(Path(directory), manage.APP_VERSION, None)
            install.side_effect = manage.archive_update.ArchiveUpdateError("证书验证失败", "certificate_error")
            with self.assertRaises(manage.UpdateError) as caught:
                manage.update_repository()
            self.assertEqual(caught.exception.code, "certificate_error")
        git.assert_not_called()

    def test_concurrent_checks_and_upgrade_share_one_lock(self):
        entered = threading.Event()
        release = threading.Event()
        second_entered = threading.Event()
        calls = []

        def status(progress=None):
            calls.append(True)
            if len(calls) == 1:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("test did not release first check")
            else:
                second_entered.set()
            return {"available": False, "can_update": True}

        with patch.object(manage, "_repository_update_status", side_effect=status), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(manage.update_repository)
            self.assertTrue(entered.wait(2))
            second = pool.submit(manage.repository_update_status)
            try:
                self.assertFalse(second_entered.wait(0.1))
            finally:
                release.set()
            self.assertFalse(first.result(timeout=2)["updated"])
            self.assertFalse(second.result(timeout=2)["available"])


class LocalGitUpgradeTests(TestCase):
    """Exercise real Git with two tiny local mirrors, never the user's checkout."""

    def test_gitee_then_github_upgrade_preserves_private_files_and_origin(self):
        with tempfile.TemporaryDirectory(prefix="bookmark dual source ") as directory:
            root = Path(directory)
            upstream, client = root / "upstream", root / "client"

            def git(*args, cwd=root):
                result = subprocess.run(["git", *map(str, args)], cwd=cwd, capture_output=True,
                                        text=True, timeout=15, check=True)
                return result.stdout.strip()

            git("init", "-b", "main", upstream)
            git("config", "user.name", "Bookmark test", cwd=upstream)
            git("config", "user.email", "bookmark-test@example.invalid", cwd=upstream)
            (upstream / ".gitignore").write_text("private.txt\n", encoding="utf-8")
            (upstream / "app.txt").write_text("v1", encoding="utf-8")
            git("add", ".", cwd=upstream)
            git("commit", "-m", "initial", cwd=upstream)
            git("clone", upstream, client)
            initial = git("rev-parse", "HEAD", cwd=client)
            (client / "private.txt").write_text("local bookmarks", encoding="utf-8")
            (upstream / "app.txt").write_text("v2", encoding="utf-8")
            git("commit", "-am", "second", cwd=upstream)

            with patch.object(manage, "ROOT", client), patch.object(manage, "UPDATE_SOURCES", (
                ("Gitee", str(upstream)), ("GitHub", str(root / "unused")),
            )):
                status = manage.repository_update_status()
                self.assertTrue(status["available"])
                self.assertEqual(git("rev-parse", "HEAD", cwd=client), initial)
                self.assertTrue(manage.update_repository()["updated"])
                self.assertEqual((client / "app.txt").read_text(encoding="utf-8"), "v2")

            (upstream / "app.txt").write_text("v3", encoding="utf-8")
            git("commit", "-am", "third", cwd=upstream)
            with patch.object(manage, "ROOT", client), patch.object(manage, "UPDATE_SOURCES", (
                ("Gitee", str(root / "unavailable")), ("GitHub", str(upstream)),
            )):
                result = manage.update_repository()
                self.assertTrue(result["updated"])
                self.assertEqual(result["source"], "GitHub")
                self.assertEqual((client / "app.txt").read_text(encoding="utf-8"), "v3")
                self.assertEqual((client / "private.txt").read_text(encoding="utf-8"), "local bookmarks")
                self.assertEqual(git("rev-parse", "origin/main", cwd=client), initial)
                self.assertEqual(git("remote", cwd=client), "origin")
                (client / "app.txt").write_text("local edit", encoding="utf-8")
                with self.assertRaisesRegex(manage.UpdateError, "未提交"):
                    manage.update_repository()
                self.assertEqual((client / "app.txt").read_text(encoding="utf-8"), "local edit")
