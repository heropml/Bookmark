# -*- coding: utf-8 -*-
"""Where the app keeps its files, the switches every part of it reads, and shared file helpers.

Other modules read these as ``settings.NAME`` when they run, so changing one here (as tests do)
changes it everywhere.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
# Launchers run this file; installers and older ZIP updaters also read APP_VERSION from it.
MANAGE_SCRIPT = SCRIPTS / "manage.py"
ROOT = Path(os.environ.get("BOOKMARK_ROOT", SCRIPTS.parent))
WEB_ROOT = ROOT / "web"
DATA_DIR = ROOT / "data"
SRC = DATA_DIR / "bookmarks.html"
EXAMPLE_SRC = DATA_DIR / "bookmarks.example.html"
DATA_JS = WEB_ROOT / "data.js"
WINDOW_STATE = DATA_DIR / ".window-state.json"
PORT = 8765
HEALTH_RESPONSE = b"bookmark-weather-v3\n"
PACKAGED_APP = os.environ.get("BOOKMARK_PACKAGED") == "1"
# Installers, release checks and older ZIP updaters read the release number from this line of
# manage.py, so it is written only there.
VERSION_LINE_RE = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', re.M)


def installation_id() -> str:
    """Identify this directory without exposing its path to the page."""
    return hashlib.sha256(os.fsencode(os.path.normcase(str(ROOT.resolve())))).hexdigest()


def file_stamp(path) -> str:
    stat = os.stat(path)
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}"


def write_atomic(path: Path, data: bytes) -> None:
    """Readers see the old or the new file, never half of one."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_bytes(data)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Windows refuses to replace a file another thread is still sending.
                if attempt == 9:
                    raise
                time.sleep(0.05)
    finally:
        tmp.unlink(missing_ok=True)


def release_version() -> str | None:
    """The version written in manage.py on disk now, read without running it; None if unreadable."""
    try:
        match = VERSION_LINE_RE.search(MANAGE_SCRIPT.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


# The version this process started with. The packaged macOS app has no manage.py file to read,
# so manage.py also sets this when it starts.
APP_VERSION = release_version() or ""
