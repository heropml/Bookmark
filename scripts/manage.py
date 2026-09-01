# -*- coding: utf-8 -*-
"""Build bookmark data and serve the local homepage."""
from __future__ import annotations

import html
import json
import os
import re
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
HREF_RE = re.compile(r'<A HREF="([^"]+)"', re.I)


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
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise SystemExit("LOCALAPPDATA is not set")
    user_data = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if profile is None:
        local_state = user_data / "Local State"
        if not local_state.is_file():
            raise SystemExit(f"not found: {local_state}")
        state = json.loads(local_state.read_text(encoding="utf-8"))
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            data = b"bookmark\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
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

        if urlparse(self.path).path != "/__window_state":
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
            return resp.status == 200 and b"<html" in chunk
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
