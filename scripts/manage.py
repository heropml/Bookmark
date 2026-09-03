# -*- coding: utf-8 -*-
"""Build bookmark data and serve the local homepage."""
from __future__ import annotations

import html
import json
import math
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
DATA_DIR = ROOT / "data"
SRC = DATA_DIR / "bookmarks.html"
EXAMPLE_SRC = DATA_DIR / "bookmarks.example.html"
DATA_JS = WEB_ROOT / "data.js"
WINDOW_STATE = DATA_DIR / ".window-state.json"
PORT = 8765
APP_VERSION = "v1.0.1"
HEALTH_RESPONSE = b"bookmark-weather-v3\n"
HREF_RE = re.compile(r'<A HREF="([^"]+)"', re.I)
UPDATE_REMOTE = "origin"
UPDATE_BRANCH = "main"
GIT_TIMEOUT_SECONDS = 15


class UpdateError(RuntimeError):
    """A repository update cannot safely be completed."""


def git_output(*args: str) -> str:
    """Run a bounded Git command inside this repository."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise UpdateError("无法连接更新服务") from error
    if result.returncode:
        raise UpdateError("无法检查更新，请稍后重试")
    return result.stdout.strip()


def repository_update_status() -> dict[str, object]:
    """Check whether main can fast-forward to origin/main without data loss."""
    version = {"version": APP_VERSION}
    if not (ROOT / ".git").is_dir():
        raise UpdateError("当前安装不支持在线升级")
    if git_output("branch", "--show-current") != UPDATE_BRANCH:
        return {"available": False, "can_update": False, "reason": "当前不在 main 分支", **version}
    if git_output("status", "--porcelain", "--untracked-files=no"):
        return {"available": False, "can_update": False, "reason": "存在未提交的本地代码修改", **version}

    git_output("fetch", "--quiet", UPDATE_REMOTE, UPDATE_BRANCH)
    current = git_output("rev-parse", "HEAD")
    remote = git_output("rev-parse", f"{UPDATE_REMOTE}/{UPDATE_BRANCH}")
    base = git_output("merge-base", "HEAD", f"{UPDATE_REMOTE}/{UPDATE_BRANCH}")
    if current == remote:
        return {"available": False, "can_update": True, "current": current[:7], "remote": remote[:7], **version}
    if base == current:
        return {"available": True, "can_update": True, "current": current[:7], "remote": remote[:7], **version}
    if base == remote:
        return {"available": False, "can_update": False, "reason": "本地代码领先远程", **version}
    return {"available": False, "can_update": False, "reason": "本地代码与远程存在分叉", **version}


def update_repository() -> dict[str, object]:
    """Fast-forward the complete repository after the user confirms an update."""
    status = repository_update_status()
    if not status.get("can_update"):
        raise UpdateError(str(status.get("reason") or "当前无法升级"))
    if not status.get("available"):
        return {"ok": True, "updated": False, **status}
    git_output("merge", "--ff-only", f"{UPDATE_REMOTE}/{UPDATE_BRANCH}")
    return {
        "ok": True,
        "updated": True,
        "previous": status["current"],
        "current": git_output("rev-parse", "HEAD")[:7],
    }


def restart_after_update() -> None:
    """Allow the HTTP response to finish before replacing this server process."""
    time.sleep(0.35)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def weather_code(description: str) -> int:
    """Map the Chinese fallback provider's condition text to a WMO-style code."""
    if "雷" in description:
        return 96 if "冰雹" in description else 95
    if "雪" in description:
        if "大" in description or "暴" in description:
            return 75
        return 71
    if "雨" in description:
        if "阵" in description:
            return 80
        if "大" in description or "暴" in description:
            return 65
        if "中" in description:
            return 63
        return 61
    if any(word in description for word in ("雾", "霾", "沙尘")):
        return 45
    if "阴" in description:
        return 3
    if "云" in description:
        return 2
    if "晴" in description:
        return 0
    return 3


def weather_description(code: int) -> str:
    """Use the same concise labels as the page for Open-Meteo responses."""
    if code == 0:
        return "晴"
    if code in (1, 2):
        return "多云"
    if code == 3:
        return "阴"
    if code in (45, 48):
        return "雾"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "雨"
    if 71 <= code <= 77 or code in (85, 86):
        return "雪"
    if code >= 95:
        return "雷雨"
    return "天气"


def weather_from_uapis(city: str) -> tuple[float, int, str]:
    """Get Chinese city weather from the primary provider."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    url = "https://uapis.cn/api/v1/misc/weather?" + urlencode({"city": city})
    request = Request(url, headers={"User-Agent": "Bookmark/1.0"})
    with urlopen(request, timeout=2.5) as response:
        upstream = json.load(response)
    temperature = float(upstream["temperature"])
    description = str(upstream["weather"]).strip()
    if not description or not math.isfinite(temperature):
        raise ValueError("invalid UAPIs weather response")
    return temperature, weather_code(description), description


def weather_from_open_meteo(
    city: str, latitude: float | None, longitude: float | None
) -> tuple[float, int, str]:
    """Independent fallback: resolve a city if needed, then fetch Open-Meteo."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    valid_coordinates = (
        latitude is not None and longitude is not None
        and math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    )
    if not valid_coordinates:
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
            {"name": city, "count": 1, "language": "zh"}
        )
        request = Request(geocode_url, headers={"User-Agent": "Bookmark/1.0"})
        with urlopen(request, timeout=2.5) as response:
            geocode = json.load(response)
        hit = (geocode.get("results") or [None])[0]
        if not isinstance(hit, dict):
            raise ValueError("Open-Meteo city not found")
        latitude = float(hit["latitude"])
        longitude = float(hit["longitude"])

    weather_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
    )
    request = Request(weather_url, headers={"User-Agent": "Bookmark/1.0"})
    with urlopen(request, timeout=2.5) as response:
        upstream = json.load(response)
    current = upstream["current"]
    temperature = float(current["temperature_2m"])
    code = int(current["weather_code"])
    if not math.isfinite(temperature):
        raise ValueError("invalid Open-Meteo weather response")
    return temperature, code, weather_description(code)


def host_of(href: str) -> str:
    host = urlparse(href).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def norm_url(href: str) -> str:
    p = urlparse(href.strip())
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/") or "/"
    params = f";{p.params}" if p.params else ""
    query = f"?{p.query}" if p.query else ""
    fragment = f"#{p.fragment}" if p.fragment else ""
    return f"{p.scheme.lower()}://{host}{path}{params}{query}{fragment}"


def parse_html(text: str) -> list[dict]:
    stack = []
    items = []
    bar = "\u4e66\u7b7e\u680f"
    other = "\u5176\u4ed6"
    for line in text.splitlines():
        h3 = re.search(r"<H3[^>]*>(.*?)</H3>", line, re.I)
        a = re.search(r'<A HREF="([^"]+)"[^>]*>(.*?)</A>', line, re.I)
        if h3:
            name = html.unescape(re.sub(r"<[^>]+>", "", h3.group(1))).strip()
            stack.append(name)
        elif a:
            href = html.unescape(a.group(1))
            title = html.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
            parts = [x for x in stack if x and x != bar]
            path = "/".join(parts) or other
            items.append(
                {
                    "title": title or host_of(href),
                    "href": href,
                    "path": path,
                    "group": parts[0] if parts else other,
                    "host": host_of(href),
                }
            )
        if re.search(r"</DL>", line, re.I) and stack:
            stack.pop()
    return items


def chrome_bookmarks_file(profile: str | None = None) -> tuple[str, Path]:
    if sys.platform == "darwin":
        user_data = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise SystemExit("LOCALAPPDATA is not set")
        user_data = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if profile is None:
        local_state = user_data / "Local State"
        if not local_state.is_file():
            raise SystemExit(f"not found: {local_state}")
        try:
            state = json.loads(local_state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"unable to read Chrome profile: {local_state}: {exc}") from exc
        profile = state.get("profile", {}).get("last_used")
    if not profile:
        raise SystemExit("Chrome active profile was not found")
    profile_dir = user_data / profile
    for name in ("AccountBookmarks", "Bookmarks"):
        path = profile_dir / name
        if path.is_file():
            return profile, path
    raise SystemExit(f"Chrome bookmarks were not found in {profile_dir}")


def edge_bookmarks_file(profile: str | None = None) -> tuple[str, Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise SystemExit("LOCALAPPDATA is not set")
    user_data = Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    if profile is None:
        local_state = user_data / "Local State"
        if not local_state.is_file():
            raise SystemExit(f"not found: {local_state}")
        state = json.loads(local_state.read_text(encoding="utf-8"))
        profile = state.get("profile", {}).get("last_used")
    if not profile:
        raise SystemExit("Edge active profile was not found")
    profile_dir = user_data / profile
    for name in ("AccountBookmarks", "Bookmarks"):
        path = profile_dir / name
        if path.is_file():
            return profile, path
    raise SystemExit(f"Edge bookmarks were not found in {profile_dir}")


def parse_chrome(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    roots = document.get("roots")
    if not isinstance(roots, dict):
        raise SystemExit(f"invalid Chrome bookmarks file: {path}")
    items = []
    other = "\u5176\u4ed6"

    def walk(node: dict, parents: list[str]) -> None:
        if node.get("type") == "url":
            href = str(node.get("url", "")).strip()
            if not href:
                return
            title = str(node.get("name", "")).strip()
            path_name = "/".join(parents) or other
            items.append(
                {
                    "title": title or host_of(href),
                    "href": href,
                    "path": path_name,
                    "group": parents[0] if parents else other,
                    "host": host_of(href),
                }
            )
            return
        if node.get("type") != "folder":
            return
        name = str(node.get("name", "")).strip()
        next_parents = parents + [name] if name else parents
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, next_parents)

    for root_name, root in roots.items():
        if not isinstance(root, dict):
            continue
        parents = []
        if root_name != "bookmark_bar":
            name = str(root.get("name", "")).strip()
            if name:
                parents.append(name)
        for child in root.get("children") or []:
            if isinstance(child, dict):
                walk(child, parents)
    return items


def safari_bookmarks_file() -> Path:
    return Path.home() / "Library" / "Safari" / "Bookmarks.plist"


def parse_safari(path: Path) -> list[dict]:
    try:
        with path.open("rb") as stream:
            document = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise SystemExit(f"invalid Safari bookmarks file: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise SystemExit(f"invalid Safari bookmarks file: {path}")

    items = []
    other = "\u5176\u4ed6"
    folder_names = {
        "BookmarksBar": "\u4e2a\u4eba\u6536\u85cf",
        "BookmarksMenu": "\u4e66\u7b7e\u83dc\u5355",
        "ReadingList": "\u9605\u8bfb\u5217\u8868",
    }

    def walk(node: dict, parents: list[str]) -> None:
        href = str(node.get("URLString", "")).strip()
        if href:
            uri = node.get("URIDictionary")
            title = str(uri.get("title", "")).strip() if isinstance(uri, dict) else ""
            title = title or str(node.get("Title", "")).strip()
            path_name = "/".join(parents) or other
            items.append(
                {
                    "title": title or host_of(href),
                    "href": href,
                    "path": path_name,
                    "group": parents[0] if parents else other,
                    "host": host_of(href),
                }
            )
            return

        children = node.get("Children")
        if not isinstance(children, list):
            return
        name = str(node.get("Title", "")).strip()
        name = folder_names.get(name, name)
        next_parents = parents + [name] if name else parents
        for child in children:
            if isinstance(child, dict):
                walk(child, next_parents)

    for child in document.get("Children") or []:
        if isinstance(child, dict):
            walk(child, [])
    return items


def render_bookmarks_html(items: list[dict]) -> str:
    root = {"children": [], "folders": {}}
    for item in items:
        node = root
        for name in filter(None, item["path"].split("/")):
            folder = node["folders"].get(name)
            if folder is None:
                folder = {"name": name, "children": [], "folders": {}}
                node["folders"][name] = folder
                node["children"].append(("folder", folder))
            node = folder
        node["children"].append(("url", item))

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
    ]

    def emit(node: dict, level: int) -> None:
        pad = "    " * level
        lines.append(pad + "<DL><p>")
        for kind, child in node["children"]:
            if kind == "folder":
                lines.append(pad + "    <DT><H3>" + html.escape(child["name"]) + "</H3>")
                emit(child, level + 1)
            else:
                title = html.escape(child["title"])
                href = html.escape(child["href"], quote=True)
                lines.append(pad + '    <DT><A HREF="' + href + '">' + title + "</A>")
        lines.append(pad + "</DL><p>")

    emit(root, 0)
    return "\n".join(lines) + "\n"


def write_bookmarks_html(items: list[dict]) -> None:
    tmp = SRC.with_suffix(SRC.suffix + ".tmp")
    tmp.write_text(render_bookmarks_html(items), encoding="utf-8", newline="\n")
    tmp.replace(SRC)
    print(f"wrote {SRC.name}: {len(items)}")


def dedupe_html(text: str) -> tuple[str, int]:
    seen: set[str] = set()
    dropped = 0
    out = []
    for line in text.splitlines(keepends=True):
        m = HREF_RE.search(line)
        if m:
            key = norm_url(m.group(1))
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
        out.append(line)
    new = "".join(out)
    if text.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    return new, dropped


def pick_html() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    path = filedialog.askopenfilename(
        title="\u9009\u62e9\u4e66\u7b7e HTML",
        filetypes=[("HTML", "*.html *.htm"), ("All", "*.*")],
    )
    root.destroy()
    return Path(path) if path else None


def replace_src(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if path.resolve() != SRC.resolve():
        SRC.write_text(text, encoding="utf-8", newline="\n")
        print(f"copied {path} -> {SRC.name}")


def src_file() -> Path:
    return SRC if SRC.is_file() else EXAMPLE_SRC


def write_data(items: list[dict], source_name: str):
    seen: dict[str, int] = {}
    for it in items:
        key = norm_url(it["href"])
        seen[key] = seen.get(key, 0) + 1
    out = []
    for i, it in enumerate(items):
        out.append({**it, "id": i, "dupe": seen[norm_url(it["href"])] > 1})
    DATA_JS.write_text(
        "window.BOOKMARKS = " + json.dumps(out, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    groups = Counter(x["group"] for x in out)
    print(f"wrote {DATA_JS.name}: {len(out)} from {source_name}")
    for name, n in groups.most_common():
        print(f"  {n:3d}  {name}")
    return out


def build():
    path = src_file()
    if not path.is_file():
        if DATA_JS.is_file():
            print(f"using existing {DATA_JS.name}")
            return None
        raise SystemExit(f"not found: {SRC.name}")
    text = path.read_text(encoding="utf-8")
    text, dropped = dedupe_html(text)
    if dropped:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"removed {dropped} duplicates from {path.name}")
    return write_data(parse_html(text), path.name)


def sync_chrome(profile: str | None = None):
    profile, path = chrome_bookmarks_file(profile)
    print(f"Chrome profile: {profile} ({path.name})")
    write_bookmarks_html(parse_chrome(path))
    return build()


def sync_edge(profile: str | None = None):
    profile, path = edge_bookmarks_file(profile)
    print(f"Edge profile: {profile} ({path.name})")
    write_bookmarks_html(parse_chrome(path))
    return build()


def sync_safari():
    path = safari_bookmarks_file()
    print(f"Safari bookmarks: {path}")
    write_bookmarks_html(parse_safari(path))
    return build()


class Handler(SimpleHTTPRequestHandler):
    # Windows registry mappings can label SVGs as image/svg, which browsers reject.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".svg": "image/svg+xml"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        path = self.path.split("?", 1)[0]
        if (
            path in ("/", "/index.html", "/data.example.js", "/data.js")
            or path.startswith(("/js/", "/css/", "/weather/"))
        ):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            data = HEALTH_RESPONSE
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/__update":
            try:
                self.send_json(200, repository_update_status())
            except UpdateError as error:
                self.send_json(503, {"available": False, "can_update": False, "reason": str(error)})
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

            source = "uapis"
            try:
                temperature, code, description = weather_from_uapis(city)
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                source = "open-meteo"
                try:
                    temperature, code, description = weather_from_open_meteo(
                        city, latitude, longitude
                    )
                except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                    self.send_error(502)
                    return
            data = json.dumps(
                {
                    "current": {"temperature_2m": temperature, "weather_code": code},
                    "description": description,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Weather-Source", source)
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/__favicon":
            skin = (parse_qs(parsed.query).get("skin") or [""])[0]
            try:
                from shortcut import icon_path

                data = icon_path(skin).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.send_error(404)
            return
        if parsed.path == "/__icon":
            skin = (parse_qs(parsed.query).get("skin") or [""])[0]
            try:
                from shortcut import set_icon

                set_icon(skin)
                self.send_response(204)
                self.end_headers()
            except Exception:
                self.send_error(400)
            return
        return super().do_GET()

    def do_POST(self):
        from urllib.parse import urlparse

        path = urlparse(self.path).path
        if path == "/__update":
            try:
                result = update_repository()
            except UpdateError as error:
                self.send_json(409, {"ok": False, "message": str(error)})
                return
            self.send_json(200, result)
            if result.get("updated"):
                threading.Thread(target=restart_after_update, daemon=True).start()
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
            WINDOW_STATE.write_text(
                json.dumps({"width": width, "height": height, "maximized": maximized}),
                encoding="utf-8",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            self.send_error(400)
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


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
        return index_ok and resp.status == 200 and health == HEALTH_RESPONSE
    except (OSError, URLError):
        return False


def pick_port() -> int:
    if page_ok(PORT) or not port_in_use(PORT):
        return PORT
    for port in range(PORT + 1, PORT + 20):
        if not port_in_use(port):
            return port
    raise SystemExit("no free port")


def serve_hidden(port: int) -> None:
    import subprocess
    import sys
    import time

    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = str(pyw if pyw.is_file() else py)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    subprocess.Popen(
        [exe, "-X", "utf8", str(Path(__file__).resolve()), "--serve", str(port)],
        cwd=str(ROOT),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if page_ok(port):
            return
        time.sleep(0.1)
    raise SystemExit("server did not start")


def main():
    import sys

    args = sys.argv[1:]
    if args and args[0] == "--serve":
        port = int(args[1]) if len(args) > 1 else PORT
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
        return
    if "--replace" in args:
        idx = args.index("--replace")
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            path = Path(args[idx + 1])
        else:
            path = pick_html()
        if path is None:
            print("cancelled")
            return
        if not path.is_file():
            print(f"not found: {path}")
            return
        replace_src(path)
        build()
        return

    if "--sync-chrome" in args:
        idx = args.index("--sync-chrome")
        profile = None
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            profile = args[idx + 1]
        sync_chrome(profile)
    elif "--sync-edge" in args:
        idx = args.index("--sync-edge")
        profile = None
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            profile = args[idx + 1]
        sync_edge(profile)
    elif "--sync-safari" in args:
        sync_safari()
    else:
        build()
    if "--build" in args:
        return
    port = pick_port()
    version = "%s-%s" % (
        (WEB_ROOT / "index.html").stat().st_mtime_ns,
        DATA_JS.stat().st_mtime_ns,
    )
    url = f"http://127.0.0.1:{port}/index.html?v={version}"
    if not page_ok(port):
        serve_hidden(port)
    webbrowser.open(url)


if __name__ == "__main__":
    main()
