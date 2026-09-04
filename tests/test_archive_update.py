import copy
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from scripts import archive_update as updater


COMMIT = "a" * 40
TREE = "b" * 40


class ArchiveTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bookmark ZIP test ")
        self.addCleanup(self.temporary.cleanup)
        # macOS reports /var for /private/var; install() resolves, so the test must too.
        self.root = Path(self.temporary.name).resolve()
        self.old = {
            "scripts/manage.py": b'APP_VERSION = "v1.0.4"\n',
            "scripts/archive_update.py": b"# old updater\n",
            "web/index.html": b"<html>v1.0.4</html>",
            "web/js/update.js": b"// old update UI\n",
            "runtime/python/python.exe": b"same-runtime",
            "web/data.js": b"private bookmarks JS",
            "data/bookmarks.html": b"private bookmarks HTML",
            "data/.window-state.json": b'{"width":900}',
            "web/my-image.png": b"user-added image",
            "notes.txt": b"personal notes",
        }
        self.new = {
            "scripts/manage.py": b'APP_VERSION = "v1.0.5"\n',
            "scripts/archive_update.py": b"# new updater\n",
            "web/index.html": b"<html>v1.0.5</html>",
            "web/js/update.js": "// 新版更新界面\n".encode(),
            "runtime/python/python.exe": b"same-runtime",
            "web/js/new.js": b"// added module\n",
            # Even if an upstream accidentally includes private paths, ignore them.
            "web/data.js": b"DO NOT INSTALL",
            "data/bookmarks.html": b"DO NOT INSTALL",
            "data/.window-state.json": b"DO NOT INSTALL",
            ".git/config": b"DO NOT INSTALL",
        }
        for path, data in self.old.items():
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        self.manifest = {"truncated": False, "tree": [
            {"path": path, "type": "blob", "mode": "100644", "sha": updater.blob_hash(data), "size": len(data)}
            for path, data in self.new.items()
        ]}
        self.calls = []
        self.events = []

    def remote(self, source, url, limit, deadline=None):
        self.calls.append((source, url))
        if url.endswith("/commits/main"):
            return json.dumps({"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}).encode()
        if "/git/trees/" in url:
            self.assertIn(TREE, url)
            return json.dumps(self.manifest).encode()
        self.assertIn(COMMIT, url, "不能从会变化的 main URL 下载代码")
        path = unquote(url.split(COMMIT + "/", 1)[1])
        data = self.new[path]
        self.assertLessEqual(len(data), limit)
        return data

    def assert_original(self):
        for path, data in self.old.items():
            self.assertEqual((self.root / path).read_bytes(), data, path)
        self.assertFalse((self.root / "web/js/new.js").exists())

    def install(self):
        return updater.install(self.root, "v1.0.4", self.events.append)

    def test_upgrade_needs_no_git_preserves_data_and_backs_up_programs(self):
        with patch.object(updater, "read_url", side_effect=self.remote), patch.object(subprocess, "run", side_effect=AssertionError("must not invoke Git")):
            result = self.install()
        self.assertTrue(result["updated"])
        self.assertEqual(result["current"], "v1.0.5")
        self.assertEqual(result["mode"], "archive")
        self.assertEqual(result["source"], "Gitee")
        for path in updater.REQUIRED | {"web/js/new.js"}:
            self.assertEqual((self.root / path).read_bytes(), self.new[path])
        for path in set(self.old) - updater.REQUIRED:
            self.assertEqual((self.root / path).read_bytes(), self.old[path])
        backup = Path(result["backup"])
        self.assertTrue(backup.is_relative_to(self.root / "data/.update-backups"))
        self.assertEqual((backup / "web/index.html").read_bytes(), self.old["web/index.html"])
        self.assertFalse((self.root / ".git").exists())
        self.assertFalse(list((self.root / "data").glob(".update-stage-*")))
        self.assertEqual(self.events[0]["stage"], "checking")
        self.assertEqual(self.events[-1]["stage"], "applying")
        self.assertTrue(all(source == "Gitee" for source, _ in self.calls))

    def test_same_or_older_version_is_not_installed_and_only_small_metadata_is_read(self):
        for remote_version in ("v1.0.4", "v1.0.3"):
            self.new["scripts/manage.py"] = f'APP_VERSION = "{remote_version}"\n'.encode()
            self.calls.clear()
            with patch.object(updater, "read_url", side_effect=self.remote):
                result = self.install()
            self.assertFalse(result["updated"])
            self.assertEqual(len(self.calls), 2)
            self.assert_original()
        self.assertGreater(updater._version("v1.10.0"), updater._version("v1.9.9"))

    def test_metadata_falls_back_but_successful_gitee_source_remains_authoritative(self):
        def unavailable(source, *args):
            if source == "Gitee":
                raise updater.ArchiveUpdateError("证书验证失败", "certificate_error")
            return self.remote(source, *args)

        with patch.object(updater, "read_url", side_effect=unavailable):
            status = updater.update_status("v1.0.4")
        self.assertEqual(status["source"], "GitHub")
        self.assertTrue(status["available"])

    def test_download_fallback_pins_original_commit_and_hashes(self):
        def unavailable(source, url, *args):
            if source == "Gitee" and url.endswith("web/js/new.js"):
                raise updater.ArchiveUpdateError("下载失败")
            return self.remote(source, url, *args)

        with patch.object(updater, "read_url", side_effect=unavailable):
            result = self.install()
        self.assertEqual(result["source"], "GitHub")
        self.assertTrue(any("切换 GitHub" in event["message"] for event in self.events))
        github_urls = [url for source, url in self.calls if source == "GitHub"]
        self.assertTrue(github_urls)
        self.assertTrue(all(COMMIT in url for url in github_urls))

    def test_both_sources_fail_before_files_are_changed(self):
        with patch.object(updater, "read_url", side_effect=updater.ArchiveUpdateError("证书验证失败", "certificate_error")):
            with self.assertRaises(updater.ArchiveUpdateError) as caught:
                self.install()
        self.assertEqual(caught.exception.code, "certificate_error")
        self.assert_original()

    def test_corrupted_download_never_reaches_apply(self):
        def corrupted(source, url, *args):
            if url.endswith("web/js/new.js"):
                return b"tampered"
            return self.remote(source, url, *args)

        with patch.object(updater, "read_url", side_effect=corrupted):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "校验失败"):
                self.install()
        self.assert_original()
        self.assertFalse(any(event["stage"] == "applying" for event in self.events))

    def test_unsafe_or_incomplete_manifests_are_rejected_before_any_replacement(self):
        original = copy.deepcopy(self.manifest)
        malformed = []
        for path in ("../escape.py", "/absolute.py", "web/a/../../escape.py", "web/a\\b", "web/C:ads", "web/NUL.txt", "web/a."):
            item = {**original["tree"][0], "path": path}
            malformed.append({"truncated": False, "tree": original["tree"] + [item]})
        malformed.extend([
            {**original, "truncated": True},
            {**original, "tree": original["tree"][1:]},
            {**original, "tree": original["tree"] + [{**original["tree"][0], "path": "SCRIPTS/MANAGE.PY"}]},
            {**original, "tree": original["tree"] + [{**original["tree"][0], "path": "web/link", "mode": "120000"}]},
            {**original, "tree": original["tree"] + [{**original["tree"][0], "path": "web/large", "size": updater.MAX_FILE + 1}]},
        ])
        for manifest in malformed:
            with self.subTest(manifest=manifest):
                self.manifest = manifest
                with patch.object(updater, "read_url", side_effect=self.remote):
                    with self.assertRaises(updater.ArchiveUpdateError):
                        self.install()
                self.assert_original()

    def test_windows_runtime_change_is_rejected_without_touching_application(self):
        for entry in self.manifest["tree"]:
            if entry["path"].startswith("runtime/"):
                entry["sha"] = "c" * 40
        with patch.object(updater.sys, "platform", "win32"), patch.object(updater, "read_url", side_effect=self.remote):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "运行时有变化"):
                self.install()
        self.assert_original()

    def test_other_platforms_do_not_replace_bundled_windows_runtime(self):
        for entry in self.manifest["tree"]:
            if entry["path"].startswith("runtime/"):
                entry["sha"] = "c" * 40
        with patch.object(updater.sys, "platform", "darwin"), patch.object(updater, "read_url", side_effect=self.remote):
            self.assertTrue(self.install()["updated"])
        self.assertEqual((self.root / "runtime/python/python.exe").read_bytes(), b"same-runtime")

    def test_failed_replacement_restores_originals_and_removes_only_new_program_file(self):
        replace = updater.os.replace

        def fail_on_index(src, dest):
            if dest == self.root / "web/index.html":
                raise PermissionError("file locked")
            replace(src, dest)

        with patch.object(updater, "read_url", side_effect=self.remote), patch.object(updater.os, "replace", side_effect=fail_on_index):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "已恢复原文件"):
                self.install()
        self.assert_original()
        self.assertEqual(len(list((self.root / "data/.update-backups").glob("backup-*"))), 1)

    def test_edit_during_download_is_preserved_and_upgrade_is_cancelled(self):
        def editing(source, url, *args):
            if url.endswith("web/js/new.js"):
                (self.root / "web/index.html").write_bytes(b"user edit during download")
            return self.remote(source, url, *args)

        with patch.object(updater, "read_url", side_effect=editing):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "文件发生变化"):
                self.install()
        self.assertEqual((self.root / "web/index.html").read_bytes(), b"user edit during download")
        self.assertEqual((self.root / "scripts/manage.py").read_bytes(), self.old["scripts/manage.py"])
        self.assertFalse((self.root / "web/js/new.js").exists())

    def test_rollback_does_not_overwrite_a_concurrent_edit_of_an_applied_file(self):
        replace = updater.os.replace

        def edit_then_fail(src, dest):
            if dest == self.root / "web/index.html":
                (self.root / "web/js/new.js").write_bytes(b"user edit after replacement")
                raise PermissionError("locked")
            replace(src, dest)

        with patch.object(updater, "read_url", side_effect=self.remote), patch.object(updater.os, "replace", side_effect=edit_then_fail):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "部分文件恢复失败"):
                self.install()
        self.assertEqual((self.root / "web/js/new.js").read_bytes(), b"user edit after replacement")
        self.assertEqual((self.root / "scripts/manage.py").read_bytes(), self.old["scripts/manage.py"])

    def test_git_marker_added_during_download_cancels_zip_install(self):
        def converted(source, url, *args):
            if url.endswith("web/js/new.js"):
                (self.root / ".git").mkdir()
            return self.remote(source, url, *args)

        with patch.object(updater, "read_url", side_effect=converted):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "已变为 Git 仓库"):
                self.install()
        self.assert_original()

    def test_directory_collision_does_not_get_replaced(self):
        (self.root / "web/js/new.js").mkdir()
        with patch.object(updater, "read_url", side_effect=self.remote):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "目录冲突"):
                self.install()
        self.assertTrue((self.root / "web/js/new.js").is_dir())

    def test_junctions_and_symlinks_are_not_followed(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "包含链接"):
                updater._destination(self.root, "web/js/new.js")
        with patch.object(Path, "is_junction", return_value=True, create=True):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "包含链接"):
                updater._destination(self.root, "web/js/new.js")

    def test_zip_http_check_and_stream_install_use_real_adapter_without_git(self):
        from scripts import manage

        server = manage.BookmarkServer(("127.0.0.1", 0), manage.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/__update"
        try:
            with patch.object(manage, "APP_VERSION", "v1.0.4"), patch.object(manage, "installed_version", return_value="v1.0.4"), patch.object(manage, "ROOT", self.root), patch.object(updater, "read_url", side_effect=self.remote), patch.object(manage, "git_output", side_effect=AssertionError("ZIP must not invoke Git")), patch.object(server, "schedule_restart") as restart:
                with urlopen(endpoint, timeout=2) as response:
                    status = json.load(response)
                self.assertEqual(status["mode"], "archive")
                self.assertTrue(status["available"])
                request = Request(endpoint, method="POST", headers={"Accept": "application/x-ndjson"})
                with urlopen(request, timeout=3) as response:
                    events = [json.loads(line) for line in response]
                self.assertEqual(events[0]["stage"], "waiting")
                self.assertEqual(events[-1]["type"], "result")
                self.assertTrue(events[-1]["updated"])
                self.assertEqual(events[-1]["instance"], server.instance)
                self.assertEqual(events[-1]["mode"], "archive")
                restart.assert_called_once()
                self.assertEqual((self.root / "web/data.js").read_bytes(), self.old["web/data.js"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


class DownloadTests(TestCase):
    def test_only_official_https_urls_are_accepted(self):
        updater._trusted("https://raw.giteeusercontent.com/heropml/Bookmark/raw/commit/file")
        for url in ("http://gitee.com/file", "https://evil.invalid/file", "https://gitee.com@evil.invalid/file", "https://user:pass@gitee.com/file", "https://gitee.com:8080/file"):
            with self.subTest(url=url), self.assertRaises(updater.ArchiveUpdateError):
                updater._trusted(url)
        with self.assertRaises(updater.ArchiveUpdateError):
            updater._SafeRedirect().redirect_request(None, None, 302, "", {}, "http://gitee.com/file")

    def test_tls_errors_keep_verification_enabled_and_are_classified(self):
        opener = Mock()
        opener.open.side_effect = URLError(ssl.SSLCertVerificationError("untrusted"))
        with patch.object(updater, "build_opener", return_value=opener) as build:
            with self.assertRaises(updater.ArchiveUpdateError) as caught:
                updater.read_url("Gitee", "https://gitee.com/test", 10)
        self.assertEqual(caught.exception.code, "certificate_error")
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertTrue(handlers[1]._context.check_hostname)
        self.assertEqual(handlers[1]._context.verify_mode, ssl.CERT_REQUIRED)

    def test_oversized_response_and_deadline_stop_download(self):
        response = Mock()
        response.geturl.return_value = "https://gitee.com/file"
        response.read1.return_value = b"too large"
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(updater, "build_opener", return_value=opener):
            with self.assertRaisesRegex(updater.ArchiveUpdateError, "大小限制"):
                updater.read_url("Gitee", "https://gitee.com/file", 2)
            with self.assertRaises(updater.ArchiveUpdateError):
                updater.read_url("Gitee", "https://gitee.com/file", 2, deadline=0)

    def test_blob_digest_uses_git_object_format_without_git(self):
        self.assertEqual(updater.blob_hash(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")


class LaunchZIPTests(TestCase):
    def test_zip_server_starts_outside_project_without_git_on_path(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="bookmark ZIP launch ") as directory:
            installation = Path(directory)
            (installation / "scripts").mkdir()
            for name in ("manage.py", "archive_update.py"):
                shutil.copy2(root / "scripts" / name, installation / "scripts" / name)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            process = subprocess.Popen(
                [sys.executable, "-B", str(installation / "scripts/manage.py"), "--serve", str(port)],
                cwd=installation, env={**os.environ, "PATH": ""},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            service = None
            try:
                for _ in range(50):
                    if process.poll() is not None:
                        self.fail(process.communicate()[1].decode("utf-8", errors="replace"))
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/__service", timeout=0.2) as response:
                            service = json.load(response)
                        break
                    except OSError:
                        time.sleep(0.1)
                self.assertIsNotNone(service, "ZIP 服务应能加载本地升级模块并启动")
                self.assertTrue(service["instance"])
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=5)
