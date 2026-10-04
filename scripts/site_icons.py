# -*- coding: utf-8 -*-
"""Site icons for bookmark cards, fetched once per host and cached under data/.site-icons."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import threading
import time
from pathlib import Path

import settings

# Site icons are fetched once per host and kept here, so opening the page sends no bookmark
# domains to icon services and icons still show offline.
SITE_ICON_DIR = settings.DATA_DIR / ".site-icons"
SITE_ICON_SOURCES = (
    "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL"
    "&url=https://{host}&size=64",
    "https://icons.duckduckgo.com/ip3/{host}.ico",
)
SITE_ICON_REFRESH_SECONDS = 30 * 24 * 3600
SITE_ICON_MISS_SECONDS = 7 * 24 * 3600  # a site without an icon is asked again after this
SITE_ICON_LIMIT = 256 * 1024
SITE_ICON_TIMEOUT = 8  # slow routes to the services take several seconds per icon
SITE_ICON_HOST_RE = re.compile(r"(?:[a-z0-9-]{1,63}\.)+[a-z0-9-]{1,63}(?::\d{1,5})?")
# Icon requests share the browser's few connections to this service with weather, update and sync
# requests, so none may hold one for long: a lookup still running after this many seconds goes on
# in the background, and the card keeps its letter until the next load.
SITE_ICON_WAIT_SECONDS = 2
# Only this many requests wait at a time; the rest answer at once, leaving connections free.
SITE_ICON_WAITERS = threading.BoundedSemaphore(2)
# Where the icon services cannot be reached (blocked networks, offline), stop asking for a while
# instead of starting lookups that can only time out. One slow site is not a blocked network:
# only several lookups in a row that reach no service at all start the pause.
SITE_ICON_PAUSE_SECONDS = 10 * 60
SITE_ICON_FAILURES_TO_PAUSE = 3
SITE_ICON_FAILURES = 0
SITE_ICON_PAUSED_UNTIL = 0.0
# A first visit asks for many icons at once; a dozen upstream requests at a time is enough.
SITE_ICON_FETCHES = threading.BoundedSemaphore(12)
SITE_ICON_PENDING: dict[str, threading.Thread] = {}  # lookups in progress, one per host
SITE_ICON_LOCK = threading.Lock()


def site_icon_host(value: str) -> str | None:
    """The icon services' form of a bookmark host, or None for hosts they cannot know."""
    host, _, port = value.strip().lower().partition(":")
    host = host.rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # routers and other addresses only reachable from this network
    except ValueError:
        pass
    if host.endswith((".local", ".lan", ".home", ".internal", ".localhost")):
        return None
    host = host + (":" + port if port else "")
    return host if len(host) <= 260 and SITE_ICON_HOST_RE.fullmatch(host) else None


def site_icon_type(data: bytes) -> str | None:
    """Raster formats only: an SVG opened directly from this origin could run script."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def fetch_site_icon(host: str) -> bytes | None:
    """Ask each icon service in turn; None when they answer without an icon, OSError when unreachable."""
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    answered = False
    for source in SITE_ICON_SOURCES:
        request = Request(source.format(host=host), headers={"User-Agent": "Bookmark/1.0"})
        with SITE_ICON_FETCHES:
            # A queued lookup (including a fallback) may get its slot after another host paused us.
            if time.monotonic() < SITE_ICON_PAUSED_UNTIL:
                raise OSError("icon services were unreachable a moment ago")
            try:
                with urlopen(request, timeout=SITE_ICON_TIMEOUT) as response:
                    data = response.read(SITE_ICON_LIMIT + 1)
            except HTTPError as error:
                error.close()
                # Both services answer 404 with a generic picture when a site has no icon.
                answered = answered or error.code == 404
                continue
            except (OSError, ValueError):
                continue
        answered = True
        if len(data) <= SITE_ICON_LIMIT and site_icon_type(data):
            return data
    if not answered:
        raise OSError("icon services unreachable")
    return None


def _recent(path: Path, seconds: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime < seconds
    except OSError:
        return False


def _store_site_icon(host: str, key: str, icon: Path, miss: Path) -> None:
    """Look a host up and keep the answer; runs on its own thread."""
    global SITE_ICON_FAILURES, SITE_ICON_PAUSED_UNTIL
    try:
        try:
            data = fetch_site_icon(host)
        except OSError:
            with SITE_ICON_LOCK:
                # Cancelled queued lookups must not count as new failures or extend the pause.
                if time.monotonic() >= SITE_ICON_PAUSED_UNTIL:
                    SITE_ICON_FAILURES += 1
                    if SITE_ICON_FAILURES >= SITE_ICON_FAILURES_TO_PAUSE:
                        SITE_ICON_FAILURES = 0
                        SITE_ICON_PAUSED_UNTIL = time.monotonic() + SITE_ICON_PAUSE_SECONDS
            return
        with SITE_ICON_LOCK:
            SITE_ICON_FAILURES = 0
        SITE_ICON_DIR.mkdir(parents=True, exist_ok=True)
        if data is not None:
            settings.write_atomic(icon, data)
            miss.unlink(missing_ok=True)
        elif icon.is_file():
            os.utime(icon)  # keep the icon it had rather than drop to a letter
        else:
            miss.touch()
    except OSError:
        pass  # an unwritable cache only means asking again next time
    finally:
        with SITE_ICON_LOCK:
            SITE_ICON_PENDING.pop(key, None)


def site_icon(host: str) -> Path | None:
    """The cached icon for a host, looked up on first use; None when the site has none.

    Raises OSError when there is no icon to show yet: the services are unreachable, or the lookup
    is still running and will be ready on the next request.
    """
    key = hashlib.sha256(host.encode("ascii")).hexdigest()[:40]
    icon = SITE_ICON_DIR / key
    miss = SITE_ICON_DIR / (key + ".miss")
    if _recent(icon, SITE_ICON_REFRESH_SECONDS):
        return icon
    if _recent(miss, SITE_ICON_MISS_SECONDS):
        return None
    stale = icon if icon.is_file() else None
    if time.monotonic() < SITE_ICON_PAUSED_UNTIL:
        if stale:
            return stale
        raise OSError("icon services were unreachable a moment ago")
    # Cards for the same site share one lookup.
    with SITE_ICON_LOCK:
        lookup = SITE_ICON_PENDING.get(key)
        if lookup is None:
            lookup = threading.Thread(target=_store_site_icon, args=(host, key, icon, miss), daemon=True)
            SITE_ICON_PENDING[key] = lookup
            lookup.start()
    if stale:
        return stale  # refreshed in the background; the old icon shows meanwhile
    if SITE_ICON_WAITERS.acquire(blocking=False):
        try:
            lookup.join(SITE_ICON_WAIT_SECONDS)
        finally:
            SITE_ICON_WAITERS.release()
    if _recent(icon, SITE_ICON_REFRESH_SECONDS):
        return icon
    if _recent(miss, SITE_ICON_MISS_SECONDS):
        return None
    raise OSError("icon not ready yet")
