import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import preferences  # noqa: E402
import settings  # noqa: E402
from test_local_service import ServiceTestCase  # noqa: E402


VALUES = {"bm-pins": '["https://example.com/"]', "bm-skin": "celadon"}


def change(changes):
    """Save `changes` from a page that has seen the current disk values."""
    current = preferences.load()["values"]
    return preferences.merge(changes, {key: current.get(key) for key in changes})


class PreferenceStoreTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patcher = patch.object(settings, "DATA_DIR", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_migrate_then_reject_stale_page_clearing_pins(self):
        self.assertFalse(preferences.load()["exists"])
        first = preferences.merge(VALUES, dict.fromkeys(VALUES))
        # A second tab migrating the same browser values agrees with disk and changes nothing.
        self.assertEqual(preferences.merge(VALUES, dict.fromkeys(VALUES)), first)
        # A page that never saw the pins cannot remove them.
        with self.assertRaisesRegex(preferences.Conflict, "置顶"):
            preferences.merge({"bm-pins": None}, {"bm-pins": None})
        self.assertEqual(preferences.load(), first)
        # An explicit user action is allowed to remove every pin.
        second = change({"bm-pins": "[]"})
        self.assertEqual(second["values"]["bm-pins"], "[]")
        self.assertEqual(len(preferences.backups()), 1)

    def test_stale_pages_merge_edits_to_different_fields(self):
        preferences.merge(VALUES, dict.fromkeys(VALUES))
        # Both tabs loaded VALUES; each edits a different field afterwards.
        preferences.merge({"bm-pins": "[]"}, {"bm-pins": VALUES["bm-pins"]})
        preferences.merge({"bm-skin": "paper", "bm-layout": "compact"},
                          {"bm-skin": "celadon", "bm-layout": None})
        preferences.merge({"bm-skin": None}, {"bm-skin": "paper"})
        self.assertEqual(preferences.load()["values"], {"bm-pins": "[]", "bm-layout": "compact"})
        # Making the same change another tab already made is not a conflict.
        preferences.merge({"bm-pins": "[]"}, {"bm-pins": VALUES["bm-pins"]})
        with self.assertRaisesRegex(preferences.Conflict, "置顶"):
            preferences.merge({"bm-pins": '["https://b/"]'}, {"bm-pins": VALUES["bm-pins"]})

    def test_malformed_merge_requests_are_rejected(self):
        for changes, base in (([], {}), ({"bm-skin": "snow"}, None), ({"bm-skin": "snow"}, {}),
                              ({"bm-skin": 1}, {"bm-skin": None}), ({"bm-skin": "snow"}, {"bm-skin": 1}),
                              ({"unexpected": "x"}, {"unexpected": None})):
            with self.subTest(changes=changes, base=base), self.assertRaises(ValueError):
                preferences.merge(changes, base)
        self.assertFalse(preferences.load()["exists"])

    def test_migration_skips_invalid_fields_without_weakening_normal_save_validation(self):
        values = {**VALUES, "bm-layout": "removed-layout", "bm-city": "{broken"}
        result = preferences.merge(values, dict.fromkeys(values), migration=True)
        self.assertEqual(result["values"], VALUES)
        self.assertCountEqual(result["rejected"], ["bm-layout", "bm-city"])
        # Concurrent first-run tabs still agree on the valid fields.
        self.assertEqual(preferences.merge(values, dict.fromkeys(values), migration=True), result)
        with self.assertRaises(ValueError):
            preferences.merge({"bm-layout": "removed-layout"}, {"bm-layout": None})
        with self.assertRaises(ValueError):
            preferences.replace(values)
        with self.assertRaises(ValueError):
            preferences.merge({"bm-skin": "paper"}, {"bm-skin": "celadon"}, migration=True)
        self.assertEqual(preferences.load()["values"], VALUES)

    def test_entirely_invalid_migration_does_not_create_empty_configuration(self):
        result = preferences.merge({"bm-pins": "bad"}, {"bm-pins": None}, migration=True)
        self.assertFalse(result["exists"])
        self.assertEqual(result["rejected"], ["bm-pins"])
        self.assertFalse((self.root / "preferences.json").exists())

    def test_migration_cannot_overwrite_another_pages_change(self):
        change(VALUES)
        with self.assertRaises(preferences.Conflict):
            preferences.merge({"bm-skin": "paper", "bm-layout": "bad"},
                              {"bm-skin": None, "bm-layout": None}, migration=True)
        self.assertEqual(preferences.load()["values"], VALUES)

    def test_frontend_options_and_persisted_keys_match_server_whitelists(self):
        web = SCRIPTS.parent / "web" / "js"
        config = (web / "config.js").read_text(encoding="utf-8")
        mapping = {"skin": "SKINS", "icon": "ICONS", "layout": "LAYOUTS", "motion": "MOTIONS",
                   "trail": "TRAILS", "sky": "SKYS", "fx": "FX"}
        for field, name in mapping.items():
            with self.subTest(field=field):
                body = re.search(rf"const {name} = \[(.*?)\];", config, re.S).group(1)
                choices = re.findall(r'id: "([^"]+)"', body)
                self.assertCountEqual(choices, preferences.CHOICES[field].split())
                for value in choices:
                    preferences.validate({"bm-" + field: value})
        library = (web / "library.js").read_text(encoding="utf-8")
        focus = re.search(r'const next = .*dataset\.focus === "on" \? "([^"]+)" : "([^"]+)";', library)
        self.assertCountEqual(focus.groups(), preferences.CHOICES["focus"].split())
        source = (web / "preferences.js").read_text(encoding="utf-8")
        keys = re.search(r"const keys = \[(.*?)\];", source, re.S).group(1)
        self.assertEqual(set(re.findall(r'"(bm-[^"]+)"', keys)), preferences.KEYS)

    def test_restore_backs_up_current_configuration_and_noop_does_not_stack(self):
        first = change(VALUES)
        self.assertEqual(change(VALUES), first)
        self.assertEqual(preferences.backups(), [])
        change({"bm-skin": "paper"})
        original = preferences.backups()[0]
        restored = preferences.restore(original["id"])
        self.assertEqual(restored["values"], VALUES)
        self.assertEqual(len(preferences.backups()), 2)
        self.assertEqual(preferences.restore(preferences.backups()[0]["id"])["values"]["bm-skin"], "paper")

    def test_unreadable_or_corrupt_file_is_never_treated_as_first_run(self):
        target = self.root / "preferences.json"
        target.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            preferences.merge(VALUES, dict.fromkeys(VALUES))
        with self.assertRaises(ValueError):
            preferences.replace(VALUES)
        self.assertEqual(target.read_text(), "{broken")
        with patch.object(Path, "read_bytes", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                preferences.load()

    def test_failed_backup_or_atomic_replace_keeps_original_bytes(self):
        change(VALUES)
        target = self.root / "preferences.json"
        before = target.read_bytes()
        with patch.object(settings, "write_atomic", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                change({"bm-pins": None})
        self.assertEqual(target.read_bytes(), before)
        atomic = settings.write_atomic

        def fail_current(path, data):
            if path == target:
                raise PermissionError()
            atomic(path, data)

        with patch.object(settings, "write_atomic", side_effect=fail_current):
            with self.assertRaises(PermissionError):
                change({"bm-pins": None})
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(preferences.backups()[0]["pins"], 1)

    def test_two_pages_cannot_silently_overwrite_the_same_field(self):
        change(VALUES)

        def save(skin):
            try:
                preferences.merge({"bm-skin": skin}, {"bm-skin": "celadon"})
                return "saved"
            except preferences.Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(save, ("snow", "paper")))
        self.assertCountEqual(results, ["saved", "conflict"])

    def test_history_is_bounded_and_import_validation_does_not_modify_current(self):
        change(VALUES)
        with patch.object(preferences, "BACKUP_INTERVAL", 0):
            for i in range(25):
                current = change({"bm-city": json.dumps({"name": str(i)})})
        self.assertEqual(len(preferences.backups()), preferences.BACKUP_LIMIT)
        for values in ({**VALUES, "unexpected": "x"}, {"bm-pins": "{}"}, {"bm-skin": "unknown"},
                       {"bm-card-density": "999"}, {"bm-sky-count": "NaN"}, {"bm-pins": "[1]"}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    change(values)
                with self.assertRaises(ValueError):
                    preferences.replace(values)
        for name in ("../preferences", "/tmp/file", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                preferences.restore(name)
        self.assertEqual(preferences.load(), current)

    def test_existing_category_settings_and_incompatible_presets_survive(self):
        values = {**VALUES, "bm-category-layout": '{"公司":{"order":["A","B"],"width":"large"}}',
                  "bm-appearance-presets": '[{"name":"Future","settings":{"skin":"future-skin"}}]'}
        self.assertEqual(change(values)["values"], values)

    def test_retention_listing_failure_does_not_report_successful_save_as_failure(self):
        change(VALUES)
        with patch.object(preferences, "backup_files", side_effect=PermissionError):
            current = change({"bm-skin": "paper"})
        self.assertEqual(preferences.load(), current)
        self.assertEqual(current["values"]["bm-skin"], "paper")

    def test_one_corrupt_backup_does_not_hide_other_backups(self):
        change(VALUES)
        with patch.object(preferences, "BACKUP_INTERVAL", 0):
            change({"bm-pins": None, "bm-skin": None})
            change(VALUES)
        corrupt = preferences.backup_files()[0]
        corrupt.write_text("{broken")
        items = preferences.backups()
        self.assertEqual(len(items), 2)
        self.assertEqual(sum("error" in item for item in items), 1)
        self.assertEqual(next(item for item in items if "error" not in item)["pins"], 1)

    def test_maximum_configuration_roundtrips_with_export_envelope(self):
        overhead = len(json.dumps({"bm-appearance-presets": '[""]'}).encode("utf-8"))
        values = {"bm-appearance-presets": '["' + "a" * (preferences.MAX_BYTES - overhead) + '"]'}
        current = change(values)
        self.assertEqual(preferences.load(), current)
        exported = json.dumps({"format": 1, "values": values}, indent=2).encode("utf-8")
        self.assertLessEqual(len(exported), preferences.MAX_BYTES + 4096)

    def test_burst_of_edits_keeps_one_snapshot_until_interval_passes(self):
        change(VALUES)
        for skin in ("snow", "paper", "sakura"):
            change({"bm-skin": skin})
        self.assertEqual(len(preferences.backups()), 1)
        # The kept snapshot is the state before the burst, not an intermediate edit.
        snapshot = preferences.read_document(preferences.backup_files()[0])
        self.assertEqual(snapshot["values"], VALUES)
        old = time.time() - preferences.BACKUP_INTERVAL - 1
        os.utime(preferences.backup_files()[0], (old, old))
        change({"bm-skin": "abyss"})
        self.assertEqual(len(preferences.backups()), 2)

    def test_restore_and_import_always_back_up_current_configuration(self):
        change(VALUES)
        change({"bm-skin": "paper"})
        self.assertEqual(len(preferences.backups()), 1)
        preferences.replace({**VALUES, "bm-skin": "snow"})
        self.assertEqual(len(preferences.backups()), 2)
        preferences.restore(preferences.backup_files()[-1].stem)
        self.assertEqual(len(preferences.backups()), 3)

    def test_legacy_current_category_is_dropped_instead_of_rejected(self):
        target = self.root / "preferences.json"
        target.write_text(json.dumps({"format": 1, "revision": "a" * 32, "updated": 0,
                                      "values": {**VALUES, "bm-folder": "旧分类"}}), encoding="utf-8")
        current = preferences.load()
        self.assertEqual(current["values"], VALUES)
        # An old page or old export still sending the category saves cleanly without it.
        self.assertEqual(preferences.merge({"bm-folder": "x"}, {"bm-folder": "旧分类"}), current)
        preferences.replace({**VALUES, "bm-folder": "x", "bm-skin": "paper"})
        self.assertNotIn("bm-folder", json.loads(target.read_text(encoding="utf-8"))["values"])


class PreferenceServiceTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(settings, "DATA_DIR", self.web.parent / "data")
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.web / "index.html").write_text(
            '<html><head><!-- bookmark-preferences --><script src="js/preferences.js"></script></head></html>',
            encoding="utf-8")

    def post(self, path, body, headers=None):
        return self.request("POST", path,
                            {"Origin": self.page, "Content-Type": "application/json", **(headers or {})},
                            json.dumps(body))

    def merge(self, changes, base=None, headers=None):
        base = dict.fromkeys(changes) if base is None else base
        return self.post("/__preferences", {"changes": changes, "base": base}, headers)

    def test_html_loads_disk_before_scripts_and_etag_changes_with_preferences(self):
        _, before, body = self.request("GET", "/index.html")
        self.assertIn(b'"exists": false', body)
        self.assertIn(settings.installation_id().encode(), body)
        status, _, raw = self.merge(VALUES)
        self.assertEqual(status, 200)
        current = json.loads(raw)
        status, after, body = self.request("GET", "/index.html", {"If-None-Match": before["ETag"]})
        self.assertEqual(status, 200)
        self.assertNotEqual(before["ETag"], after["ETag"])
        self.assertLess(body.index(b"BOOKMARK_PREFERENCES"), body.index(b' src="js/preferences.js"'))
        self.assertIn(current["revision"].encode(), body)
        self.assertEqual(self.request("GET", "/", {"If-None-Match": after["ETag"]})[0], 304)

    def test_save_origin_and_size_checks_and_field_conflict(self):
        self.assertEqual(self.merge(VALUES, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertFalse((settings.DATA_DIR / "preferences.json").exists())
        self.assertEqual(self.merge(VALUES)[0], 200)
        status, _, body = self.merge({"bm-pins": None})
        self.assertEqual(status, 409)
        self.assertIn("置顶", json.loads(body)["message"])
        self.assertEqual(self.merge({"bm-layout": "compact"})[0], 200)
        self.assertEqual(self.merge({"bm-city": "x" * preferences.MAX_BYTES})[0], 400)
        self.assertEqual(self.merge({"bm-city": "x" * 2 * preferences.MAX_BYTES})[0], 400)
        self.assertEqual(self.request("GET", "/__preferences/backups",
                                     {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"})[0], 403)

    def test_backup_list_and_restore_endpoint(self):
        self.merge(VALUES)
        self.merge({"bm-pins": "[]"}, {"bm-pins": VALUES["bm-pins"]})
        status, headers, body = self.request("GET", "/__preferences/backups")
        self.assertEqual((status, headers["Cache-Control"]), (200, "no-store"))
        backup = json.loads(body)["backups"][0]
        status, _, body = self.post("/__preferences/restore", {"id": backup["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["values"], VALUES)

    def test_import_always_snapshots_while_ordinary_saves_are_throttled(self):
        self.merge(VALUES)
        for skin in ("snow", "paper"):
            current = preferences.load()["values"]["bm-skin"]
            self.assertEqual(self.merge({"bm-skin": skin}, {"bm-skin": current})[0], 200)
        self.assertEqual(len(preferences.backups()), 1)
        status, _, body = self.post("/__preferences", {"values": VALUES})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["values"], VALUES)
        self.assertEqual(len(preferences.backups()), 2)

    def test_migration_endpoint_reports_rejected_fields(self):
        values = {**VALUES, "bm-layout": "obsolete"}
        status, _, body = self.post("/__preferences",
                                    {"changes": values, "base": dict.fromkeys(values), "migration": True})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["values"], VALUES)
        self.assertEqual(result["rejected"], ["bm-layout"])
        self.assertEqual(self.post("/__preferences", {"changes": {}, "base": {}, "migration": "yes"})[0], 400)

    def test_corruption_is_embedded_as_error_and_script_text_is_escaped(self):
        self.merge({"bm-appearance-presets": '["</script><script>alert(1)</script>"]'})
        _, _, body = self.request("GET", "/")
        self.assertNotIn(b"<script>alert(1)", body)
        self.assertIn(b"\\u003c/script>", body)
        (settings.DATA_DIR / "preferences.json").write_text("broken")
        self.assertIn(b'"error":', self.request("GET", "/")[2])
        self.assertEqual(self.merge(VALUES)[0], 400)
