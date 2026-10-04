# -*- coding: utf-8 -*-
"""Build bookmark data and serve the local homepage.

This is the command line entry point that launchers and installer shortcuts run. The work is done
by the modules beside it:

- settings: file locations, version and switches shared by everything
- bookmark_formats / bookmark_store: reading bookmark files, backups and web/data.js
- browser_sync: finding and importing each browser's bookmarks
- server: the local homepage service, with weather, site_icons and updates behind its API
"""
from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path

import bookmark_store
import browser_sync
import server
import settings

# Installers, release checks and older ZIP updaters read the version from this exact line.
APP_VERSION = "v1.1.6"
# settings reads the line above from this file; the packaged macOS app has no file to read.
settings.APP_VERSION = APP_VERSION


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def page_ok(port: int) -> bool:
    from urllib.error import URLError
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{port}/index.html", timeout=0.8) as resp:
            chunk = resp.read(64).lower()
            index_ok = resp.status == 200 and b"<html" in chunk
        with urlopen(f"http://127.0.0.1:{port}/__health", timeout=0.8) as resp:
            health = resp.read(64)
        if not index_ok or resp.status != 200 or health != settings.HEALTH_RESPONSE:
            return False
        with urlopen(f"http://127.0.0.1:{port}/__service", timeout=0.8) as resp:
            service = json.loads(resp.read(4096))
        return isinstance(service, dict) and service.get("installation") == settings.installation_id()
    except (OSError, URLError, ValueError):
        return False


def pick_port() -> int:
    from concurrent.futures import ThreadPoolExecutor

    ports = list(range(settings.PORT, settings.PORT + 20))
    # Look for our existing service before choosing a free port, even if a lower port freed up.
    with ThreadPoolExecutor(max_workers=len(ports)) as probes:
        occupied = list(probes.map(port_in_use, ports))
    for port, in_use in zip(ports, occupied):
        if in_use and page_ok(port):
            return port
    for port, in_use in zip(ports, occupied):
        if not in_use:
            return port
    raise SystemExit("no free port")


def serve_hidden(port: int) -> None:
    server.start_hidden_server(port)
    for _ in range(40):
        if page_ok(port):
            return
        time.sleep(0.1)
    raise SystemExit("server did not start")


def local_url() -> str:
    """Reuse this directory's running service or start one, and return the page address."""
    port = pick_port()
    if not page_ok(port):
        serve_hidden(port)
    version = "%s-%s" % (
        (settings.WEB_ROOT / "index.html").stat().st_mtime_ns,
        settings.DATA_JS.stat().st_mtime_ns,
    )
    return f"http://127.0.0.1:{port}/index.html?v={version}"


def main():
    args = sys.argv[1:]
    if args and args[0] == "--serve":
        port = int(args[1]) if len(args) > 1 else settings.PORT
        server.serve(port)
        return
    if args and args[0] == "--url":
        # For launchers that open their own browser window: print the address only.
        print(local_url())
        return
    if "--replace" in args:
        idx = args.index("--replace")
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            path = Path(args[idx + 1])
        else:
            path = browser_sync.pick_html()
        if path is None:
            print("cancelled")
            return
        if not path.is_file():
            print(f"not found: {path}")
            return
        bookmark_store.replace_src(path)
        bookmark_store.build()
        return

    if "--sync-chrome" in args:
        idx = args.index("--sync-chrome")
        profile = None
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            profile = args[idx + 1]
        browser_sync.sync_chrome(profile)
    elif "--sync-edge" in args:
        idx = args.index("--sync-edge")
        profile = None
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            profile = args[idx + 1]
        browser_sync.sync_edge(profile)
    elif "--sync-safari" in args:
        browser_sync.sync_safari()
    elif "--build" in args:
        bookmark_store.build()
    else:
        bookmark_store.build_if_stale()
    if "--build" in args:
        return
    webbrowser.open(local_url())


if __name__ == "__main__":
    main()
