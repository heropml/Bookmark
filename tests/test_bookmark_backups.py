import sys
import json
from pathlib import Path
import tempfile
import threading
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))  # the scripts import each other by name

import bookmark_formats  # noqa: E402
import bookmark_store  # noqa: E402
import server as bookmark_server  # noqa: E402
import settings  # noqa: E402


def bookmark(title):
    return {"title": title, "href": f"https://example.com/{title}", "host": "example.com", "path": "工具", "group": "工具"}


class BackupTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "bookmarks.html"
        self.data = self.root / "data.js"
        for key, value in (("SRC", self.source), ("DATA_JS", self.data)):
            mock = patch.object(settings, key, value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_first_import_has_no_snapshot_then_replacement_and_restore_preserve_versions(self):
        bookmark_store.write_bookmarks_html([bookmark("original")])
        self.assertEqual(bookmark_store.bookmark_backups(), [])
        before = self.source.read_bytes()
        bookmark_store.write_bookmarks_html([bookmark("new")])
        backups = bookmark_store.bookmark_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0]["count"], 1)
        self.assertEqual((self.root / ".bookmark-backups" / (backups[0]["id"] + ".html")).read_bytes(), before)
        restored = bookmark_store.restore_bookmarks(backups[0]["id"])
        self.assertEqual(restored[0]["title"], "original")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn('"title": "original"', self.data.read_text())
        self.assertEqual(len(bookmark_store.bookmark_backups()), 2)
        # A restore itself is reversible using the saved pre-restore version.
        recent = bookmark_store.bookmark_backups()[0]
        self.assertEqual(bookmark_store.restore_bookmarks(recent["id"])[0]["title"], "new")

    def test_html_import_keeps_exact_previous_source(self):
        self.source.write_bytes(b"<DL><p>\r\n<DT><A HREF=\"https://example.com\">Old</A>\r\n</DL>")
        before = self.source.read_bytes()
        incoming = self.root / "incoming.html"
        incoming.write_text(bookmark_formats.render_bookmarks_html([bookmark("imported")]))
        bookmark_store.replace_src(incoming)
        snapshot = next((self.root / ".bookmark-backups").glob("*.html"))
        self.assertEqual(snapshot.read_bytes(), before)
        self.assertEqual(self.source.read_text(), incoming.read_text())

    def test_backup_failure_does_not_replace_existing_bookmarks(self):
        bookmark_store.write_bookmarks_html([bookmark("original")])
        before = self.source.read_bytes()
        with patch.object(bookmark_store, "backup_bookmarks", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                bookmark_store.write_bookmarks_html([bookmark("new")])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.source.with_suffix(".html.tmp").exists())

    def test_invalid_or_missing_backup_does_not_write(self):
        bookmark_store.write_bookmarks_html([bookmark("original")])
        before = self.source.read_bytes()
        for value in ("../bookmarks", "/tmp/private", "a" * 33, "x" * 32):
            with self.assertRaises(ValueError):
                bookmark_store.restore_bookmarks(value)
        with self.assertRaises(FileNotFoundError):
            bookmark_store.restore_bookmarks("a" * 32)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(bookmark_store.bookmark_backups(), [])


    def test_unchanged_resync_does_not_stack_identical_backups(self):
        bookmark_store.write_bookmarks_html([bookmark("original")])
        for _ in range(4):
            bookmark_store.write_bookmarks_html([bookmark("original")])
        self.assertEqual(bookmark_store.bookmark_backups(), [], "内容未变时不需要备份")
        bookmark_store.write_bookmarks_html([bookmark("new")])
        bookmark_store.write_bookmarks_html([bookmark("new")])
        self.assertEqual([backup["count"] for backup in bookmark_store.bookmark_backups()], [1])

    def test_only_the_newest_backups_are_kept(self):
        import os
        with patch.object(bookmark_store, "BOOKMARK_BACKUP_LIMIT", 3):
            for index in range(6):
                bookmark_store.write_bookmarks_html([bookmark(f"version{index}")])
                # Distinct mtimes keep the newest-first order deterministic on fast file systems.
                for offset, path in enumerate(bookmark_store.backup_files()):
                    os.utime(path, (1_000_000 - offset, 1_000_000 - offset))
            files = bookmark_store.backup_files()
        self.assertEqual(len(files), 3)
        self.assertIn("version4", files[0].read_text(encoding="utf-8"), "最新的备份保存替换前的上一版")
        self.assertIn("version2", files[-1].read_text(encoding="utf-8"))
        self.assertEqual(len(list((self.root / ".bookmark-backups").iterdir())), 3, "超出上限的旧备份被删除")

class BackupHTTPTests(BackupTests):
    def setUp(self):
        super().setUp()
        self.server = bookmark_server.BookmarkServer(("127.0.0.1", 0), bookmark_server.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, payload, headers=None):
        request_headers = {"Content-Type": "application/json", "X-Bookmark-Sync": "1", "Origin": self.base}
        request_headers.update(headers or {})
        request = Request(self.base + "/__bookmarks/restore", data=json.dumps(payload).encode(), headers=request_headers)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_list_restore_and_confirmation_guards(self):
        bookmark_store.write_bookmarks_html([bookmark("original")])
        bookmark_store.write_bookmarks_html([bookmark("new")])
        with urlopen(self.base + "/__bookmarks/backups") as response:
            backup = json.load(response)["backups"][0]
        payload = {"id": backup["id"], "confirmed": True}
        for headers in ({"Origin": "https://example.org"}, {"X-Bookmark-Sync": ""}, {"Content-Type": "text/plain"}):
            self.assertEqual(self.request(payload, headers)[0], 403)
        for data in ({"id": backup["id"]}, {"id": "../bookmarks", "confirmed": True}, [], {**payload, "padding": "x" * 300}):
            self.assertEqual(self.request(data)[0], 400)
        with bookmark_server.BOOKMARK_SYNC_LOCK:
            self.assertEqual(self.request(payload)[0], 409)
        self.server.restarting = True
        self.assertEqual(self.request(payload)[0], 409)
        self.server.restarting = False
        self.assertIn("new", self.source.read_text())
        self.assertEqual(self.request(payload), (200, {"ok": True, "count": 1}))
        self.assertIn("original", self.source.read_text())
        self.assertEqual(self.request({"id": "f" * 32, "confirmed": True})[0], 404)
