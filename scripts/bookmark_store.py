# -*- coding: utf-8 -*-
"""The homepage's bookmark data: data/bookmarks.html, its backups, and the generated web/data.js."""
from __future__ import annotations

import json
import re
import threading
import uuid
from collections import Counter
from pathlib import Path

import bookmark_formats
import settings
from bookmark_formats import dedupe_items, parse_html, render_bookmarks_html


# Enough history to undo several imports without letting repeated syncs fill the disk.
BOOKMARK_BACKUP_LIMIT = 20


def backup_files() -> list[Path]:
    """Snapshots this app wrote, newest first."""
    folder = settings.SRC.parent / ".bookmark-backups"
    return sorted((path for path in folder.glob("*.html") if re.fullmatch(r"[a-f0-9]{32}", path.stem)),
                  key=lambda path: path.stat().st_mtime, reverse=True)


def backup_bookmarks() -> None:
    """Keep a private, exact copy before replacing the imported bookmark source."""
    if not settings.SRC.is_file():
        return
    content = settings.SRC.read_bytes()
    existing = backup_files()
    # Re-syncing unchanged bookmarks would otherwise stack identical snapshots.
    if existing and existing[0].read_bytes() == content:
        return
    folder = settings.SRC.parent / ".bookmark-backups"
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = folder / (uuid.uuid4().hex + ".html")
    temporary = snapshot.with_suffix(".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(snapshot)
    finally:
        temporary.unlink(missing_ok=True)
    for old in existing[BOOKMARK_BACKUP_LIMIT - 1:]:
        old.unlink(missing_ok=True)


# Snapshots are written once, so each is parsed once; entries leave with the snapshots they count.
_BACKUP_COUNTS: dict[tuple[str, int, int], int] = {}
_BACKUP_COUNTS_LOCK = threading.Lock()


def bookmark_backups() -> list[dict]:
    """List snapshots with the number of bookmarks restoring each one would show."""
    backups = []
    keys = set()
    for path in backup_files():
        stat = path.stat()
        key = (path.name, stat.st_mtime_ns, stat.st_size)
        keys.add(key)
        with _BACKUP_COUNTS_LOCK:
            count = _BACKUP_COUNTS.get(key)
        if count is None:
            count = len(dedupe_items(parse_html(path.read_text(encoding="utf-8")))[0])
            with _BACKUP_COUNTS_LOCK:
                _BACKUP_COUNTS[key] = count
        backups.append({"id": path.stem, "created": stat.st_mtime, "count": count})
    with _BACKUP_COUNTS_LOCK:
        for key in list(_BACKUP_COUNTS):
            if key not in keys:
                del _BACKUP_COUNTS[key]
    return backups


def replace_bookmark_source(text: str) -> None:
    tmp = settings.SRC.with_suffix(settings.SRC.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        # Writing the same bookmarks again replaces nothing, so there is nothing to back up.
        if not (settings.SRC.is_file() and settings.SRC.read_bytes() == tmp.read_bytes()):
            backup_bookmarks()
        tmp.replace(settings.SRC)
    finally:
        tmp.unlink(missing_ok=True)


def restore_bookmarks(snapshot_id: str) -> list[dict]:
    if not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
        raise ValueError("invalid backup id")
    path = settings.SRC.parent / ".bookmark-backups" / (snapshot_id + ".html")
    text = path.read_text(encoding="utf-8")
    items = parse_html(text)
    replace_bookmark_source(text)
    return write_data(dedupe_items(items)[0], settings.SRC.name)


def write_bookmarks_html(items: list[dict]) -> None:
    replace_bookmark_source(render_bookmarks_html(items))
    print(f"wrote {settings.SRC.name}: {len(items)}")


def replace_src(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # A file that yields no links is the wrong file or an unreadable format; keep the current page.
    if not parse_html(text):
        raise SystemExit(f"no bookmarks found in {path.name}")
    if path.resolve() != settings.SRC.resolve():
        replace_bookmark_source(text)
        print(f"copied {path} -> {settings.SRC.name}")


def src_file() -> Path:
    return settings.SRC if settings.SRC.is_file() else settings.EXAMPLE_SRC


def build_stamp_file() -> Path:
    return settings.SRC.with_name(".data-build.json")


def build_stamp(path: Path) -> dict[str, object]:
    """What data.js was generated from: the source file and the code that read it."""
    stat = path.stat()
    try:
        # The page data is read by bookmark_formats and written here.
        script = max(Path(file).stat().st_mtime_ns for file in (bookmark_formats.__file__, __file__))
    except (OSError, TypeError):
        script = 0  # packaged builds have no script files; their version still changes
    return {"source": str(path.resolve()), "mtime_ns": stat.st_mtime_ns, "size": stat.st_size,
            "version": settings.APP_VERSION, "script": script}


def write_data(items: list[dict], source_name: str):
    data = ("window.BOOKMARKS = " + json.dumps(items, ensure_ascii=False) + ";\n").encode("utf-8")
    try:
        unchanged = settings.DATA_JS.read_bytes() == data
    except OSError:
        unchanged = False
    # Rewriting identical data would only change its ETag and make open pages download it again.
    if not unchanged:
        settings.write_atomic(settings.DATA_JS, data)
    groups = Counter(x["group"] for x in items)
    print(f"{'kept' if unchanged else 'wrote'} {settings.DATA_JS.name}: {len(items)} from {source_name}")
    for name, n in groups.most_common():
        print(f"  {n:3d}  {name}")
    return items


def build():
    path = src_file()
    if not path.is_file():
        if settings.DATA_JS.is_file():
            print(f"using existing {settings.DATA_JS.name}")
            return None
        raise SystemExit(f"not found: {settings.SRC.name}")
    stamp = build_stamp(path)
    items, dropped = dedupe_items(parse_html(path.read_text(encoding="utf-8")))
    if dropped:
        print(f"skipped {dropped} duplicates from {path.name}")
    write_data(items, path.name)
    try:
        settings.write_atomic(build_stamp_file(), json.dumps(stamp).encode("utf-8"))
    except OSError:
        pass  # only an optimisation: the next launch simply rebuilds
    return items


def build_if_stale():
    """Launchers call this: rebuild only when the source or the reading code changed."""
    path = src_file()
    if path.is_file() and settings.DATA_JS.is_file():
        try:
            if json.loads(build_stamp_file().read_text(encoding="utf-8")) == build_stamp(path):
                return None
        except (OSError, ValueError):
            pass
    return build()
