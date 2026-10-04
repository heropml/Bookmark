# -*- coding: utf-8 -*-
"""The local homepage service: static files, the page's API, and restarting after an update."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bookmark_store
import browser_sync
import settings
import site_icons
import updates
import weather

BOOKMARK_SYNC_LOCK = threading.Lock()
# Page assets referenced from index.html; stamped URLs may be cached until the file changes.
ASSET_REF_RE = re.compile(r'\b(href|src)="((?:css|js)/[^"?#]+)"')
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def restart_after_update(server: ThreadingHTTPServer) -> None:
    """Finish the response, then ask the main loop to replace this server."""
    time.sleep(0.35)
    server.shutdown()


class BookmarkServer(ThreadingHTTPServer):
    # A page load opens several connections at once; the default backlog of 5 resets some of them.
    request_queue_size = 64

    def server_bind(self):
        # HTTPServer looks up the host's full name here, before listening. That reverse DNS lookup
        # can stall startup for many seconds (seen on macOS), longer than launchers wait for the
        # page, and nothing here reads the name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = uuid.uuid4().hex
        self.restarting = False
        self.restart_lock = threading.Lock()
        self.update_check = None  # (checked_at, status or UpdateError)
        # (skin, shortcut files' state) after this service last set the icon; a repeat costs nothing,
        # but a shortcut recreated by an installer or launcher is rewritten again.
        self.icon_applied = None

    def update_status(self, refresh: bool = False) -> dict[str, object]:
        """Reuse this service's recent update check; retry a failed one sooner."""
        with updates.UPDATE_LOCK:
            if self.update_check and not refresh:
                checked_at, result = self.update_check
                failed = isinstance(result, updates.UpdateError)
                if time.monotonic() - checked_at < (updates.UPDATE_RETRY_SECONDS if failed else updates.UPDATE_CACHE_SECONDS):
                    if failed:
                        raise updates.UpdateError(str(result), result.code)
                    return dict(result)
            try:
                status = updates.repository_update_status()
            except updates.UpdateError as error:
                self.update_check = (time.monotonic(), error)
                raise
            self.update_check = (time.monotonic(), status)
            return dict(status)

    def schedule_restart(self) -> None:
        with self.restart_lock:
            if self.restarting:
                return
            self.restarting = True
            threading.Thread(target=restart_after_update, args=(self,), daemon=False).start()


def serve(port: int) -> None:
    server = BookmarkServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    if server.restarting:
        # Replace on the main thread before interpreter shutdown clears globals.
        if sys.platform == "win32":
            # Popen quotes paths containing spaces correctly on Windows.
            start_hidden_server(port)
        else:
            os.execv(sys.executable, serve_command(sys.executable, port))


def serve_command(executable: str, port: int) -> list[str]:
    """The packaged app is its own launcher; a source checkout runs this script."""
    if settings.PACKAGED_APP:
        return [executable, "--serve", str(port)]
    return [executable, "-X", "utf8", str(settings.MANAGE_SCRIPT), "--serve", str(port)]


def start_hidden_server(port: int) -> subprocess.Popen:
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = str(pyw if pyw.is_file() else py)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.Popen(
        serve_command(exe, port),
        cwd=str(settings.ROOT),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class Handler(SimpleHTTPRequestHandler):
    # Windows registry mappings can label SVGs as image/svg, which browsers reject.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".svg": "image/svg+xml"}
    # Keep-alive lets one page load reuse a few connections instead of opening one per file.
    protocol_version = "HTTP/1.1"
    timeout = 30  # an idle kept-alive connection releases its thread
    etag = None  # set by send_head for the response being written
    immutable = False  # set by send_head for a stamped asset URL
    connection_header = False  # whether this response already says how the connection ends

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(settings.WEB_ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def log_error(self, fmt, *args):
        # Browsers keep idle connections open; closing them after `timeout` is routine.
        if fmt.startswith("Request timed out"):
            return
        super().log_error(fmt, *args)

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def local_host(self) -> str | None:
        """The Host header when it names this service; any other name may be DNS rebinding."""
        host = self.headers.get("Host", "").lower()
        port = self.server.server_port
        return host if host in (f"127.0.0.1:{port}", f"localhost:{port}") else None

    def same_origin(self) -> bool:
        """Other sites can also post to 127.0.0.1; only this homepage may change local state."""
        host = self.local_host()
        return host is not None and self.headers.get("Origin") == f"http://{host}"

    def cross_site_subresource(self) -> bool:
        """Another site embedding or fetching from this service; following a link to it is fine."""
        return (self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site")
                and self.headers.get("Sec-Fetch-Mode") != "navigate")

    def revalidated(self) -> bool:
        path = urlparse(getattr(self, "path", "")).path
        return (
            path in ("/", "/index.html", "/data.example.js", "/data.js")
            or path.startswith(("/js/", "/css/", "/weather/"))
        )

    def stamped_index(self, path: str) -> bytes:
        """index.html with each script and stylesheet addressed by its current version."""
        def stamp(match):
            asset = os.path.join(self.directory, *match.group(2).split("/"))
            if not os.path.isfile(asset):
                return match.group(0)
            return f'{match.group(1)}="{match.group(2)}?v={settings.file_stamp(asset)}"'

        with open(path, encoding="utf-8") as stream:
            return ASSET_REF_RE.sub(stamp, stream.read()).encode("utf-8")

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if self.revalidated() and os.path.isfile(path):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                body = self.stamped_index(path)
                # The page changes whenever any asset it names changes, so hash what is sent.
                self.etag = '"%s"' % hashlib.sha1(body).hexdigest()[:24]
                if self.etag in self.headers.get("If-None-Match", ""):
                    self.send_response(304)
                    self.end_headers()
                    return None
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return io.BytesIO(body)
            # Size plus nanosecond mtime changes whenever an upgrade, installer or sync rewrites
            # a file, even when the new copy carries an older timestamp.
            current = settings.file_stamp(path)
            self.etag = f'"{current}"'
            # Only the address index.html hands out may be cached for good; any other stays fresh.
            self.immutable = parse_qs(parsed.query).get("v") == [current]
            if self.etag in self.headers.get("If-None-Match", ""):
                self.send_response(304)
                self.end_headers()
                return None
        return super().send_head()

    def send_header(self, keyword, value):
        if keyword.lower() == "connection":
            self.connection_header = True
        super().send_header(keyword, value)

    def end_headers(self):
        etag, self.etag = self.etag, None
        immutable, self.immutable = self.immutable, False
        if self.command == "POST" and not self.connection_header:
            # Rejected requests leave their body unread; never parse it as the next request.
            self.send_header("Connection", "close")
        self.connection_header = False
        # Other sites may not embed these files, e.g. <script src=".../data.js"> to read bookmarks.
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if self.revalidated():
            # Revalidate on every load so upgrades and syncs show at once; unchanged files answer
            # 304 and keep the browser's compiled script cache. Stamped assets need no check.
            self.send_header("Cache-Control", IMMUTABLE_CACHE if immutable else "no-cache")
            if etag:
                self.send_header("ETag", etag)
        super().end_headers()

    def do_HEAD(self):
        if not self.local_host() or self.cross_site_subresource():
            self.send_error(403)
            return
        super().do_HEAD()

    def do_GET(self):
        if not self.local_host():
            self.send_error(403)
            return
        if self.cross_site_subresource():
            self.send_json(403, {"ok": False, "message": "请从本地书签主页打开。"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            data = settings.HEALTH_RESPONSE
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/__update":
            # Only this page's explicit "check again" skips the cache; other sites cannot force fetches.
            refresh = (parse_qs(parsed.query).get("refresh") == ["1"]
                       and self.headers.get("Sec-Fetch-Site", "same-origin") == "same-origin")
            try:
                if settings.PACKAGED_APP:
                    self.send_json(200, self.server.update_status(refresh))
                elif self.server.restarting or updates.installed_version() != settings.APP_VERSION:
                    # The restart waits a moment before stopping, so the reply below still goes out;
                    # a kept-alive client may act on the reply before this handler returns.
                    self.server.schedule_restart()
                    self.send_json(200, {
                        "available": False, "can_update": False, "restarting": True,
                        "version": settings.APP_VERSION, "instance": self.server.instance,
                    })
                else:
                    self.send_json(200, self.server.update_status(refresh))
            except (updates.UpdateError, OSError) as error:
                self.send_json(503, {"available": False, "can_update": False, "reason": str(error),
                                     "error": getattr(error, "code", "update_failed")})
            return
        if parsed.path == "/__service":
            self.send_json(200, {
                "version": settings.APP_VERSION, "instance": self.server.instance,
                "installation": settings.installation_id(),
                "can_restart": sys.platform in ("win32", "darwin"),
            })
            return
        if parsed.path == "/__bookmarks/sync":
            self.send_json(200, {"browsers": browser_sync.supported_sync_browsers()})
            return
        if parsed.path == "/__bookmarks/backups":
            try:
                self.send_json(200, {"backups": bookmark_store.bookmark_backups()})
            except (OSError, ValueError, UnicodeError):
                self.send_json(500, {"ok": False, "message": "无法读取书签备份，请检查目录权限。"})
            return
        if parsed.path == "/__weather":
            query = parse_qs(parsed.query)
            city = ((query.get("city") or [""])[0]).strip()[:80]
            if not city:
                self.send_error(400)
                return
            try:
                latitude = float((query.get("lat") or [""])[0])
                longitude = float((query.get("lon") or [""])[0])
            except ValueError:
                latitude = longitude = None

            try:
                data, source = weather.current_weather(city, latitude, longitude)
            except LookupError:
                self.send_error(502)
                return
            self.send_weather(data, source)
            return
        if parsed.path == "/__siteicon":
            self.send_site_icon(site_icons.site_icon_host((parse_qs(parsed.query).get("host") or [""])[0]))
            return
        if parsed.path == "/__favicon":
            skin = (parse_qs(parsed.query).get("skin") or [""])[0]
            try:
                from shortcut import icon_path

                icon = icon_path(skin)
                # Each skin has its own address; revalidate instead of resending ~100 KB each load.
                etag = f'"{settings.file_stamp(icon)}"'
                if etag in self.headers.get("If-None-Match", ""):
                    self.send_response(304)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("ETag", etag)
                    self.end_headers()
                    return
                data = icon.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.send_error(404)
            return
        return super().do_GET()

    def send_site_icon(self, host: str | None) -> None:
        # An error makes the page keep the card's letter.
        if host is None:
            self.send_error(404)
            return
        try:
            icon = site_icons.site_icon(host)
            if icon is None:
                self.send_error(404)
                return
            etag = f'"{settings.file_stamp(icon)}"'
            data = None if etag in self.headers.get("If-None-Match", "") else icon.read_bytes()
        except OSError:
            self.send_error(502)
            return
        kind = site_icons.site_icon_type(data) if data is not None else None
        if data is not None and kind is None:
            self.send_error(404)
            return
        self.send_response(304 if data is None else 200)
        if data is not None:
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
        # Icons rarely change; a day without asking keeps hundreds of cards from revalidating.
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("ETag", etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if data is not None:
            self.wfile.write(data)

    def send_weather(self, data: bytes, source: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Weather-Source", source)
        self.end_headers()
        self.wfile.write(data)

    def stream_update(self):
        """Report actual upgrade stages; older clients keep the JSON endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        connected = True

        def send_event(event):
            nonlocal connected
            if not connected:
                return
            try:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except OSError:
                # Closing the page must not interrupt an accepted Git upgrade.
                connected = False

        try:
            result = updates.update_repository(lambda event: send_event({"type": "progress", **event}))
        except updates.UpdateError as error:
            send_event({"type": "error", "message": str(error), "error": error.code})
            return
        finally:
            # Whatever the outcome, the check made before this upgrade is stale.
            self.server.update_check = None
        send_event({"type": "result", **result, "instance": self.server.instance})
        if result.get("updated"):
            self.server.schedule_restart()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self.same_origin():
            self.send_json(403, {"ok": False, "message": "请从本地书签主页操作。"})
            return
        if path == "/__bookmarks/sync":
            self.sync_bookmarks()
            return
        if path == "/__bookmarks/restore":
            self.restore_bookmark_backup()
            return
        if path == "/__bookmarks/settings":
            # Only macOS has a settings page that grants browser-bookmark access.
            if sys.platform != "darwin":
                self.send_error(404)
                return
            try:
                subprocess.run(["open", browser_sync.FULL_DISK_ACCESS_SETTINGS], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                self.send_json(502, {"ok": False, "message": "无法打开系统设置，请手动打开。"})
                return
            self.send_response(204)
            self.end_headers()
            return
        if path == "/__bookmarks/restart":
            if sys.platform not in ("win32", "darwin"):
                self.send_error(404)
                return
            if self.headers.get("X-Bookmark-Sync") != "1":
                self.send_json(403, {"ok": False, "message": "请从本地书签主页重启。"})
                return
            if not BOOKMARK_SYNC_LOCK.acquire(blocking=False):
                self.send_json(409, {"ok": False, "message": "已有书签同步正在进行，请完成后再重启。"})
                return
            try:
                if self.server.restarting:
                    self.send_json(409, {"ok": False, "message": "服务正在重启，请稍后再试。"})
                    return
                self.send_json(200, {"ok": True, "instance": self.server.instance})
                self.server.schedule_restart()
            finally:
                BOOKMARK_SYNC_LOCK.release()
            return
        if path == "/__icon":
            if sys.platform != "win32":
                # Only Windows has a shortcut whose icon can follow the skin.
                self.send_response(204)
                self.end_headers()
                return
            skin = (parse_qs(parsed.query).get("skin") or [""])[0]
            try:
                # Rewriting the shortcut starts cscript; the same icon again changes nothing.
                from shortcut import set_icon, shortcut_state

                if self.server.icon_applied != (skin, shortcut_state()):
                    set_icon(skin)
                    self.server.icon_applied = (skin, shortcut_state())
                self.send_response(204)
                self.end_headers()
            except (Exception, SystemExit):
                # A missing icon file exits with SystemExit, which is not an Exception.
                self.send_error(400)
            return
        if path == "/__update":
            if "application/x-ndjson" in self.headers.get("Accept", ""):
                self.stream_update()
                return
            try:
                result = updates.update_repository()
            except updates.UpdateError as error:
                self.send_json(409, {"ok": False, "message": str(error)})
                return
            finally:
                self.server.update_check = None
            # The restart waits a moment before stopping, so the reply below still goes out.
            if result.get("updated"):
                self.server.schedule_restart()
            self.send_json(200, {**result, "instance": self.server.instance})
            return
        if path != "/__window_state":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise ValueError
            state = json.loads(self.rfile.read(length))
            width = int(state["width"])
            height = int(state["height"])
            maximized = state.get("maximized", False)
            if not 320 <= width <= 10000 or not 240 <= height <= 10000:
                raise ValueError
            if not isinstance(maximized, bool):
                raise ValueError
            settings.WINDOW_STATE.write_text(
                json.dumps({"width": width, "height": height, "maximized": maximized}),
                encoding="utf-8",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            self.send_error(400)
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


    def restore_bookmark_backup(self):
        if (self.headers.get("X-Bookmark-Sync") != "1"
                or self.headers.get_content_type() != "application/json"):
            self.send_json(403, {"ok": False, "message": "请从本地书签主页确认恢复。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            if (not isinstance(data, dict) or data.get("confirmed") is not True
                    or not isinstance(data.get("id"), str)
                    or not re.fullmatch(r"[a-f0-9]{32}", data["id"])):
                raise ValueError
        except (ValueError, TypeError, UnicodeDecodeError):
            self.send_json(400, {"ok": False, "message": "请选择备份并确认恢复。"})
            return
        if not BOOKMARK_SYNC_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "message": "已有书签操作正在进行，请稍后恢复。"})
            return
        try:
            if self.server.restarting:
                self.send_json(409, {"ok": False, "message": "服务正在重启，请稍后恢复。"})
                return
            items = bookmark_store.restore_bookmarks(data["id"])
            self.send_json(200, {"ok": True, "count": len(items)})
        except FileNotFoundError:
            self.send_json(404, {"ok": False, "message": "备份文件不存在，请重新打开备份列表。"})
        except (OSError, ValueError, UnicodeError):
            self.send_json(422, {"ok": False, "message": "恢复失败，请检查备份文件和目录写入权限。"})
        finally:
            BOOKMARK_SYNC_LOCK.release()

    def sync_bookmarks(self):
        # do_POST already required this page's origin; the JSON type and custom header also
        # rule out plain form posts that could overwrite bookmarks.
        if (self.headers.get("X-Bookmark-Sync") != "1"
                or self.headers.get_content_type() != "application/json"):
            self.send_json(403, {"ok": False, "message": "请从本地书签主页确认同步。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            if (not isinstance(data, dict) or data.get("confirmed") is not True
                    or data.get("browser") not in browser_sync.supported_sync_browsers()):
                raise ValueError
        except (ValueError, TypeError, UnicodeDecodeError):
            self.send_json(400, {"ok": False, "message": "请选择支持的浏览器，并确认同步。"})
            return
        browser = data["browser"]
        if not BOOKMARK_SYNC_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "message": "已有书签同步正在进行，请稍后再试。"})
            return
        try:
            if self.server.restarting:
                self.send_json(409, {"ok": False, "message": "服务正在重启，请稍后再同步。"})
                return
            items = browser_sync.sync(browser)
            self.send_json(200, {"ok": True, "count": len(items or []), "browser": browser})
        except (SystemExit, OSError, ValueError, TypeError, KeyError):
            self.send_json(422, {
                "ok": False,
                **browser_sync.sync_failure(browser),
            })
        finally:
            BOOKMARK_SYNC_LOCK.release()
