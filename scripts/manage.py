# -*- coding: utf-8 -*-
"""Build bookmark data and serve the local homepage."""
from __future__ import annotations

import html
import hashlib
import io
import json
import math
import os
import plistlib
import re
import socketserver
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections import Counter
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import archive_update
except ModuleNotFoundError as error:
    if error.name != "archive_update":
        raise
    from scripts import archive_update

ROOT = Path(os.environ.get("BOOKMARK_ROOT", Path(__file__).resolve().parent.parent))
WEB_ROOT = ROOT / "web"
DATA_DIR = ROOT / "data"
SRC = DATA_DIR / "bookmarks.html"
EXAMPLE_SRC = DATA_DIR / "bookmarks.example.html"
DATA_JS = WEB_ROOT / "data.js"
WINDOW_STATE = DATA_DIR / ".window-state.json"
PORT = 8765
APP_VERSION = "v1.1.5"
HEALTH_RESPONSE = b"bookmark-weather-v3\n"
UPDATE_SOURCES = (
    ("Gitee", "https://gitee.com/heropml/Bookmark.git"),
    ("GitHub", "https://github.com/heropml/Bookmark.git"),
)
UPDATE_BRANCH = "main"
PACKAGED_RELEASES = {
    "Gitee": "https://gitee.com/heropml/Bookmark/releases",
    "GitHub": "https://github.com/heropml/Bookmark/releases",
}
PACKAGED_REASON = "macOS 安装版请下载新版 DMG 覆盖安装，不会自动改写已安装的应用"
GIT_TIMEOUT_SECONDS = 15
# Pages opened together share one recent check instead of each contacting Gitee/GitHub.
UPDATE_CACHE_SECONDS = 10 * 60
UPDATE_RETRY_SECONDS = 60
UPDATE_LOCK = threading.RLock()
BOOKMARK_SYNC_LOCK = threading.Lock()
# Enough history to undo several imports without letting repeated syncs fill the disk.
BOOKMARK_BACKUP_LIMIT = 20
# Several tabs opening together share one upstream weather lookup.
WEATHER_CACHE_SECONDS = 5 * 60
WEATHER_CACHE: dict[tuple, tuple[float, bytes, str]] = {}
WEATHER_CACHE_LOCK = threading.Lock()
# Page assets referenced from index.html; stamped URLs may be cached until the file changes.
ASSET_REF_RE = re.compile(r'\b(href|src)="((?:css|js)/[^"?#]+)"')
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
PACKAGED_APP = os.environ.get("BOOKMARK_PACKAGED") == "1"
WINDOWS_CHROMIUM_BROWSERS = {
    "brave": ("Brave", "LOCALAPPDATA", (("BraveSoftware", "Brave-Browser", "User Data"),)),
    "vivaldi": ("Vivaldi", "LOCALAPPDATA", (("Vivaldi", "User Data"),)),
    "opera": ("Opera", "APPDATA", (("Opera Software", "Opera Stable"),)),
    "opera-gx": ("Opera GX", "APPDATA", (("Opera Software", "Opera GX Stable"),)),
    "qq": ("QQ浏览器", "LOCALAPPDATA", (("Tencent", "QQBrowser", "User Data"),)),
    "360": ("360极速浏览器", "LOCALAPPDATA", (("360Chrome", "Chrome", "User Data"),)),
    "360-x": ("360极速浏览器X", "LOCALAPPDATA", (("360ChromeX", "Chrome", "User Data"),)),
    "sogou": ("搜狗高速浏览器", "APPDATA", (("SogouExplorer", "Webkit"),)),
    "quark": ("夸克浏览器", "LOCALAPPDATA", (("Quark", "User Data"), ("Quark", "Quark", "User Data"))),
    "uc": ("UC浏览器", "LOCALAPPDATA", (("UCBrowser", "User Data"),)),
}


def installation_id() -> str:
    """Identify this directory without exposing its path to the page."""
    return hashlib.sha256(os.fsencode(os.path.normcase(str(ROOT.resolve())))).hexdigest()


def supported_sync_browsers() -> list[str]:
    if sys.platform == "win32":
        readers = {
            "chrome": chrome_bookmarks_file,
            "edge": edge_bookmarks_file,
            **{browser: lambda browser=browser: chromium_bookmarks_file(browser)
               for browser in WINDOWS_CHROMIUM_BROWSERS},
        }
        available = []
        for browser, reader in readers.items():
            try:
                reader()
            except (SystemExit, OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            available.append(browser)
        return [*available, "html"]
    return {"darwin": ["chrome", "safari", "html"]}.get(sys.platform, [])


# Opens System Settings at Privacy & Security > Full Disk Access.
FULL_DISK_ACCESS_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


def sync_failure(browser: str) -> dict[str, object]:
    """A one-line reason for the dialog, with the fix as separate steps it can fold away."""
    if browser == "html":
        return {"message": "未选择有效的书签 HTML 文件。", "steps": ["在浏览器的书签管理中导出 HTML 文件", "重新同步并选择导出的文件"]}
    if sys.platform == "darwin":
        name = {"chrome": "Chrome", "safari": "Safari"}.get(browser, "所选浏览器")
        return {
            "message": f"macOS 未允许“书签”读取 {name} 数据。",
            "steps": [
                "打开“系统设置 → 隐私与安全性 → 完全磁盘访问权限”",
                "若已有 Bookmark.app，即使开关已开启，也请选中旧条目并点“−”移除",
                "点“＋”重新添加当前 /Applications/Bookmark.app，并开启权限",
                "返回此窗口，点“重启书签”重启后台服务，页面恢复后再同步",
            ],
            "settings": True,
            "restart": True,
        }
    name = {"chrome": "Chrome", "edge": "Edge", **{
        key: value[0] for key, value in WINDOWS_CHROMIUM_BROWSERS.items()
    }}.get(browser, "所选浏览器")
    return {"message": f"无法读取或保存 {name} 书签。", "steps": ["确认浏览器已创建书签", "确认程序所在目录可以写入"]}


class UpdateError(RuntimeError):
    """A repository update cannot safely be completed."""

    def __init__(self, message: str, code: str = "update_failed"):
        super().__init__(message)
        self.code = code


def git_output(*args: str, network_url: str = "") -> str:
    """Run a bounded Git command inside this repository."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    options = []
    if network_url.startswith("https://"):
        # Per-request settings: do not change the user's global Git configuration.
        env.pop("GIT_SSL_NO_VERIFY", None)
        options += ["-c", f"http.{network_url}.sslVerify=true"]
        if sys.platform == "win32":
            options += ["-c", f"http.{network_url}.sslBackend=schannel",
                        "-c", f"http.{network_url}.schannelUseSSLCAInfo=false"]
    try:
        result = subprocess.run(
            ["git", *options, *args],
            cwd=ROOT,
            creationflags=flags,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise UpdateError("无法连接更新服务（请求超时）", "network_timeout") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise UpdateError("无法连接更新服务") from error
    if result.returncode:
        detail = (result.stderr or "").lower()
        if network_url and sys.platform == "win32" and "unsupported ssl backend" in detail:
            raise UpdateError("当前 Git 不支持 Windows 系统证书，请安装支持 Schannel 的 Git for Windows", "tls_backend")
        if network_url and any(marker in detail for marker in (
            "certificate", "cert_e_", "trust_e_", "cert_trust_", "crypt_e_",
            "sec_e_untrusted_root", "sec_e_cert_expired", "sec_e_wrong_principal", "证书",
        )):
            raise UpdateError("证书验证失败，请检查系统时间、系统根证书或公司网络证书配置（未关闭证书校验）", "certificate_error")
        raise UpdateError("无法检查更新，请稍后重试")
    return result.stdout.strip()


def packaged_update_status(progress=None) -> dict[str, object]:
    """Only report that a newer DMG exists: the installed app never rewrites itself."""
    try:
        status = archive_update.update_status(APP_VERSION, progress)
    except archive_update.ArchiveUpdateError as error:
        raise UpdateError(str(error), error.code) from error
    source = str(status.get("source") or "Gitee")
    return {
        "available": bool(status.get("available")),
        "can_update": False,
        "mode": "dmg",
        "version": APP_VERSION,
        "current": APP_VERSION,
        "remote": status.get("remote"),
        "source": source,
        "download": PACKAGED_RELEASES.get(source, PACKAGED_RELEASES["Gitee"]),
        "reason": PACKAGED_REASON,
    }


def repository_update_status(progress=None) -> dict[str, object]:
    """Serialize checks with upgrades so concurrent pages cannot race Git writes."""
    if PACKAGED_APP:
        return packaged_update_status(progress)
    with UPDATE_LOCK:
        if not os.path.lexists(ROOT / ".git"):
            try:
                return archive_update.update_status(APP_VERSION, progress)
            except archive_update.ArchiveUpdateError as error:
                raise UpdateError(str(error), error.code) from error
        return _repository_update_status(progress)


def _repository_update_status(progress=None) -> dict[str, object]:
    """Try Gitee first, then GitHub; never overwrite local code changes."""
    version = {"version": APP_VERSION}
    if progress:
        progress({"stage": "checking", "message": "检查本地修改与升级条件"})
    if not (ROOT / ".git").is_dir():
        raise UpdateError("当前安装不支持在线升级")
    if git_output("branch", "--show-current") != UPDATE_BRANCH:
        return {"available": False, "can_update": False, "reason": "当前不在 main 分支", **version}
    if git_output("status", "--porcelain", "--untracked-files=no"):
        return {"available": False, "can_update": False, "reason": "存在未提交的本地代码修改", **version}

    errors = []
    error_code = "sources_unavailable"
    for source, url in UPDATE_SOURCES:
        # Use isolated refs, not origin/main or the process-shared FETCH_HEAD.
        ref = f"refs/bookmark-updates/{source.lower()}"
        # Domestic updates should not inherit a global overseas proxy.
        options = ("-c", "http.proxy=", "-c", "http.https://gitee.com.proxy=") if source == "Gitee" else ()
        try:
            if progress:
                prefix = "前一更新源不可用，切换至" if errors else "正在连接"
                progress({"stage": "fetching", "source": source, "message": f"{prefix} {source} 同步代码"})
            git_output(*options, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
                       url, f"+refs/heads/{UPDATE_BRANCH}:{ref}", network_url=url)
            target = git_output("rev-parse", ref)
            break
        except UpdateError as error:
            errors.append(f"{source}：{error}")
            if error.code in ("certificate_error", "tls_backend"):
                error_code = error.code
    else:
        raise UpdateError("所有更新源均不可用；" + "；".join(errors), error_code)

    current = git_output("rev-parse", "HEAD")
    details = {"current": current[:7], "remote": target[:7], "target": target, "source": source, **version}
    if current == target:
        return {"available": False, "can_update": True, **details}
    base = git_output("merge-base", "HEAD", target)
    if base == current:
        return {"available": True, "can_update": True, **details}
    if base == target:
        return {"available": False, "can_update": False, "reason": "本地代码领先远程", **details}
    return {"available": False, "can_update": False, "reason": "本地代码与远程存在分叉", **details}


def update_repository(progress=None) -> dict[str, object]:
    """Fast-forward the complete repository after the user confirms an update."""
    if PACKAGED_APP:
        raise UpdateError(PACKAGED_REASON)
    if progress:
        progress({"stage": "waiting", "message": "等待本地升级任务就绪"})
    with UPDATE_LOCK:
        if not os.path.lexists(ROOT / ".git"):
            try:
                return archive_update.install(ROOT, APP_VERSION, progress)
            except archive_update.ArchiveUpdateError as error:
                raise UpdateError(str(error), error.code) from error
        status = repository_update_status(progress)
        if not status.get("can_update"):
            raise UpdateError(str(status.get("reason") or "当前无法升级"))
        if not status.get("available"):
            return {"ok": True, "updated": False, **status}
        if progress:
            progress({"stage": "applying", "source": status["source"], "message": "应用新版代码，保留本地私人书签"})
        git_output("merge", "--ff-only", status["target"])
        return {
            "ok": True,
            "updated": True,
            "previous": status["current"],
            "current": git_output("rev-parse", "HEAD")[:7],
            "source": status["source"],
        }


def installed_version() -> str:
    """Read the installed backend version without executing the updated script."""
    source = Path(__file__).read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.M)
    if not match:
        raise UpdateError("无法读取已安装版本")
    return match.group(1)


def restart_after_update(server: ThreadingHTTPServer) -> None:
    """Finish the response, then ask the main loop to replace this server."""
    time.sleep(0.35)
    server.shutdown()


def file_stamp(path) -> str:
    stat = os.stat(path)
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}"


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
        with UPDATE_LOCK:
            if self.update_check and not refresh:
                checked_at, result = self.update_check
                failed = isinstance(result, UpdateError)
                if time.monotonic() - checked_at < (UPDATE_RETRY_SECONDS if failed else UPDATE_CACHE_SECONDS):
                    if failed:
                        raise UpdateError(str(result), result.code)
                    return dict(result)
            try:
                status = repository_update_status()
            except UpdateError as error:
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
    # Drop "user:password@" so credentials are neither shown nor sent to icon services.
    host = urlparse(href).netloc.rpartition("@")[2].lower()
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


class _NetscapeBookmarkParser(HTMLParser):
    """Read a Netscape bookmark export by tags, so line breaks and attribute order do not matter."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        # One entry per open <DL>: the folder name it belongs to, "" when it adds no category.
        self.stack: list[str] = []
        self.pending: str | None = None  # folder named by the last <H3>, waiting for its <DL>
        self.folder: dict | None = None  # <H3> being read
        self.link: dict | None = None  # <A> being read

    def handle_starttag(self, tag, attrs):
        # Exports may leave <A> unclosed; the next entry or a <DD> description ends its title.
        if tag in ("a", "h3", "dt", "dd", "dl"):
            self.finish_link()
        if tag == "h3":
            self.pending = None
            # Browsers mark their toolbar folder in exports; its localized name is not a category.
            self.folder = {"toolbar": any(
                name == "personal_toolbar_folder" and (value or "").lower() == "true"
                for name, value in attrs), "text": []}
        elif tag == "a":
            self.pending = None
            href = next((value for name, value in attrs if name == "href"), None)
            self.link = {"href": href, "text": []} if href and href.strip() else None
        elif tag == "dl":
            self.stack.append(self.pending or "")
            self.pending = None

    def handle_endtag(self, tag):
        if tag == "a":
            self.finish_link()
        elif tag == "h3" and self.folder is not None:
            name = "".join(self.folder["text"]).strip()
            # An empty name keeps </DL> nesting balanced but leaves the toolbar out of paths.
            self.pending = "" if self.folder["toolbar"] else name
            self.folder = None
        elif tag == "dl":
            self.finish_link()
            self.pending = None
            if self.stack:
                self.stack.pop()

    def handle_data(self, data):
        if self.link is not None:
            self.link["text"].append(data)
        elif self.folder is not None:
            self.folder["text"].append(data)

    def finish_link(self):
        link, self.link = self.link, None
        if link is None:
            return
        href = link["href"].strip()
        title = "".join(link["text"]).strip()
        parts = [name for name in self.stack if name and name != "\u4e66\u7b7e\u680f"]
        other = "\u5176\u4ed6"
        self.items.append({
            "title": title or host_of(href),
            "href": href,
            "path": "/".join(parts) or other,
            "group": parts[0] if parts else other,
            "host": host_of(href),
        })

    def close(self):
        super().close()
        self.finish_link()


def parse_html(text: str) -> list[dict]:
    parser = _NetscapeBookmarkParser()
    parser.feed(text)
    parser.close()
    return parser.items


def dedupe_items(items: list[dict]) -> tuple[list[dict], int]:
    """Keep the first copy of each address; the source file itself is never rewritten."""
    seen: set[str] = set()
    kept = []
    for item in items:
        key = norm_url(item["href"])
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept, len(items) - len(kept)


def environment_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise SystemExit(f"{variable} is not set")
    return Path(value)


def last_used_profile(name: str, user_data: Path) -> str | None:
    """Read the profile a Chromium browser opened last from its Local State."""
    local_state = user_data / "Local State"
    try:
        state = json.loads(local_state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unable to read {name} profile: {local_state}: {exc}") from exc
    # Every detected browser is probed when the sync dialog opens; a malformed file must not break it.
    profile = state.get("profile") if isinstance(state, dict) else None
    return profile.get("last_used") if isinstance(profile, dict) else None


def profile_bookmarks(profile_dir: Path) -> Path | None:
    """Signed-in profiles keep account bookmarks separately; prefer those."""
    for filename in ("AccountBookmarks", "Bookmarks"):
        path = profile_dir / filename
        if path.is_file():
            return path
    return None


def active_profile_bookmarks(name: str, user_data: Path, profile: str | None) -> tuple[str, Path]:
    """Read the requested or last used profile, never another profile's bookmarks."""
    if profile is None:
        if not (user_data / "Local State").is_file():
            raise SystemExit(f"not found: {user_data / 'Local State'}")
        profile = last_used_profile(name, user_data)
    if not profile:
        raise SystemExit(f"{name} active profile was not found")
    path = profile_bookmarks(user_data / profile)
    if path is None:
        raise SystemExit(f"{name} bookmarks were not found in {user_data / profile}")
    return profile, path


def chrome_bookmarks_file(profile: str | None = None) -> tuple[str, Path]:
    if sys.platform == "darwin":
        user_data = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        user_data = environment_path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data"
    return active_profile_bookmarks("Chrome", user_data, profile)


def edge_bookmarks_file(profile: str | None = None) -> tuple[str, Path]:
    user_data = environment_path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data"
    return active_profile_bookmarks("Edge", user_data, profile)


def chromium_bookmarks_file(browser: str) -> tuple[str, Path]:
    name, variable, locations = WINDOWS_CHROMIUM_BROWSERS[browser]
    base = environment_path(variable)
    for parts in locations:
        user_data = base.joinpath(*parts)
        # Some builds lack Local State or keep bookmarks directly in their data folder.
        last_used = last_used_profile(name, user_data) if (user_data / "Local State").is_file() else None
        profiles = [(profile, user_data / profile) for profile in dict.fromkeys(filter(None, (last_used, "Default")))]
        for profile, profile_dir in [*profiles, ("Default", user_data)]:
            path = profile_bookmarks(profile_dir)
            if path:
                return profile, path
    raise SystemExit(f"{name} bookmarks were not found")


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


def backup_files() -> list[Path]:
    """Snapshots this app wrote, newest first."""
    folder = SRC.parent / ".bookmark-backups"
    return sorted((path for path in folder.glob("*.html") if re.fullmatch(r"[a-f0-9]{32}", path.stem)),
                  key=lambda path: path.stat().st_mtime, reverse=True)


def backup_bookmarks() -> None:
    """Keep a private, exact copy before replacing the imported bookmark source."""
    if not SRC.is_file():
        return
    content = SRC.read_bytes()
    existing = backup_files()
    # Re-syncing unchanged bookmarks would otherwise stack identical snapshots.
    if existing and existing[0].read_bytes() == content:
        return
    folder = SRC.parent / ".bookmark-backups"
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


def replace_bookmark_source(text: str) -> None:
    tmp = SRC.with_suffix(SRC.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        # Writing the same bookmarks again replaces nothing, so there is nothing to back up.
        if not (SRC.is_file() and SRC.read_bytes() == tmp.read_bytes()):
            backup_bookmarks()
        tmp.replace(SRC)
    finally:
        tmp.unlink(missing_ok=True)


def restore_bookmarks(snapshot_id: str) -> list[dict]:
    if not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
        raise ValueError("invalid backup id")
    path = SRC.parent / ".bookmark-backups" / (snapshot_id + ".html")
    text = path.read_text(encoding="utf-8")
    items = parse_html(text)
    replace_bookmark_source(text)
    return write_data(dedupe_items(items)[0], SRC.name)


def write_bookmarks_html(items: list[dict]) -> None:
    replace_bookmark_source(render_bookmarks_html(items))
    print(f"wrote {SRC.name}: {len(items)}")


def pick_html() -> Path | None:
    if sys.platform == "darwin":
        # AppKit windows must be created on the main thread, but the service asks from a worker;
        # osascript shows the native picker in its own process instead.
        script = ('activate\n'
                  'POSIX path of (choose file with prompt "\u9009\u62e9\u4e66\u7b7e HTML" '
                  'of type {"public.html"})')
        try:
            result = subprocess.run(["osascript", "-e", script], text=True, check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as error:
            raise SystemExit("file picker unavailable") from error
        path = result.stdout.strip()
        return Path(path) if result.returncode == 0 and path else None
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise SystemExit("file picker unavailable") from error

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
    # A file that yields no links is the wrong file or an unreadable format; keep the current page.
    if not parse_html(text):
        raise SystemExit(f"no bookmarks found in {path.name}")
    if path.resolve() != SRC.resolve():
        replace_bookmark_source(text)
        print(f"copied {path} -> {SRC.name}")


def src_file() -> Path:
    return SRC if SRC.is_file() else EXAMPLE_SRC


def build_stamp_file() -> Path:
    return SRC.with_name(".data-build.json")


def build_stamp(path: Path) -> dict[str, object]:
    """What data.js was generated from: the source file and the code that read it."""
    stat = path.stat()
    try:
        script = Path(__file__).stat().st_mtime_ns
    except OSError:
        script = 0  # packaged builds have no script file; their version still changes
    return {"source": str(path.resolve()), "mtime_ns": stat.st_mtime_ns, "size": stat.st_size,
            "version": APP_VERSION, "script": script}


def write_data(items: list[dict], source_name: str):
    data = ("window.BOOKMARKS = " + json.dumps(items, ensure_ascii=False) + ";\n").encode("utf-8")
    try:
        unchanged = DATA_JS.read_bytes() == data
    except OSError:
        unchanged = False
    # Rewriting identical data would only change its ETag and make open pages download it again.
    if not unchanged:
        write_atomic(DATA_JS, data)
    groups = Counter(x["group"] for x in items)
    print(f"{'kept' if unchanged else 'wrote'} {DATA_JS.name}: {len(items)} from {source_name}")
    for name, n in groups.most_common():
        print(f"  {n:3d}  {name}")
    return items


def build():
    path = src_file()
    if not path.is_file():
        if DATA_JS.is_file():
            print(f"using existing {DATA_JS.name}")
            return None
        raise SystemExit(f"not found: {SRC.name}")
    stamp = build_stamp(path)
    items, dropped = dedupe_items(parse_html(path.read_text(encoding="utf-8")))
    if dropped:
        print(f"skipped {dropped} duplicates from {path.name}")
    write_data(items, path.name)
    try:
        write_atomic(build_stamp_file(), json.dumps(stamp).encode("utf-8"))
    except OSError:
        pass  # only an optimisation: the next launch simply rebuilds
    return items


def build_if_stale():
    """Launchers call this: rebuild only when the source or the reading code changed."""
    path = src_file()
    if path.is_file() and DATA_JS.is_file():
        try:
            if json.loads(build_stamp_file().read_text(encoding="utf-8")) == build_stamp(path):
                return None
        except (OSError, ValueError):
            pass
    return build()


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


def sync_chromium(browser: str):
    profile, path = chromium_bookmarks_file(browser)
    print(f"{WINDOWS_CHROMIUM_BROWSERS[browser][0]} profile: {profile} ({path.name})")
    write_bookmarks_html(parse_chrome(path))
    return build()


def sync_html():
    path = pick_html()
    if path is None:
        raise SystemExit("bookmark HTML was not selected")
    if not path.is_file():
        raise SystemExit("bookmark HTML was not found")
    replace_src(path)
    return build()


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
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

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
            return f'{match.group(1)}="{match.group(2)}?v={file_stamp(asset)}"'

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
            current = file_stamp(path)
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
            data = HEALTH_RESPONSE
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
                if PACKAGED_APP:
                    self.send_json(200, self.server.update_status(refresh))
                elif self.server.restarting or installed_version() != APP_VERSION:
                    self.send_json(200, {
                        "available": False, "can_update": False, "restarting": True,
                        "version": APP_VERSION, "instance": self.server.instance,
                    })
                    self.server.schedule_restart()
                else:
                    self.send_json(200, self.server.update_status(refresh))
            except (UpdateError, OSError) as error:
                self.send_json(503, {"available": False, "can_update": False, "reason": str(error),
                                     "error": getattr(error, "code", "update_failed")})
            return
        if parsed.path == "/__service":
            self.send_json(200, {
                "version": APP_VERSION, "instance": self.server.instance,
                "installation": installation_id(),
                "can_restart": sys.platform in ("win32", "darwin"),
            })
            return
        if parsed.path == "/__bookmarks/sync":
            self.send_json(200, {"browsers": supported_sync_browsers()})
            return
        if parsed.path == "/__bookmarks/backups":
            try:
                self.send_json(200, {"backups": bookmark_backups()})
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

            key = (city, latitude, longitude)
            with WEATHER_CACHE_LOCK:
                cached = WEATHER_CACHE.get(key)
            if cached and time.monotonic() - cached[0] < WEATHER_CACHE_SECONDS:
                self.send_weather(cached[1], cached[2])
                return
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
            with WEATHER_CACHE_LOCK:
                now = time.monotonic()
                for stale in [k for k, v in WEATHER_CACHE.items() if now - v[0] >= WEATHER_CACHE_SECONDS]:
                    del WEATHER_CACHE[stale]
                WEATHER_CACHE[key] = (now, data, source)
            self.send_weather(data, source)
            return
        if parsed.path == "/__favicon":
            skin = (parse_qs(parsed.query).get("skin") or [""])[0]
            try:
                from shortcut import icon_path

                icon = icon_path(skin)
                # Each skin has its own address; revalidate instead of resending ~100 KB each load.
                etag = f'"{file_stamp(icon)}"'
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
            result = update_repository(lambda event: send_event({"type": "progress", **event}))
        except UpdateError as error:
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
                subprocess.run(["open", FULL_DISK_ACCESS_SETTINGS], check=True, timeout=10,
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
                result = update_repository()
            except UpdateError as error:
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
            items = restore_bookmarks(data["id"])
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
                    or data.get("browser") not in supported_sync_browsers()):
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
            action = {
                "chrome": sync_chrome, "edge": sync_edge, "safari": sync_safari, "html": sync_html,
                **{key: lambda key=key: sync_chromium(key) for key in WINDOWS_CHROMIUM_BROWSERS},
            }[browser]
            items = action()
            self.send_json(200, {"ok": True, "count": len(items or []), "browser": browser})
        except (SystemExit, OSError, ValueError, TypeError, KeyError):
            self.send_json(422, {
                "ok": False,
                **sync_failure(browser),
            })
        finally:
            BOOKMARK_SYNC_LOCK.release()


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
        if not index_ok or resp.status != 200 or health != HEALTH_RESPONSE:
            return False
        with urlopen(f"http://127.0.0.1:{port}/__service", timeout=0.8) as resp:
            service = json.loads(resp.read(4096))
        return isinstance(service, dict) and service.get("installation") == installation_id()
    except (OSError, URLError, ValueError):
        return False


def pick_port() -> int:
    from concurrent.futures import ThreadPoolExecutor

    ports = list(range(PORT, PORT + 20))
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


def serve_command(executable: str, port: int) -> list[str]:
    """The packaged app is its own launcher; a source checkout runs this script."""
    if PACKAGED_APP:
        return [executable, "--serve", str(port)]
    return [executable, "-X", "utf8", str(Path(__file__).resolve()), "--serve", str(port)]


def start_hidden_server(port: int) -> subprocess.Popen:
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = str(pyw if pyw.is_file() else py)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.Popen(
        serve_command(exe, port),
        cwd=str(ROOT),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def serve_hidden(port: int) -> None:
    start_hidden_server(port)
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
        (WEB_ROOT / "index.html").stat().st_mtime_ns,
        DATA_JS.stat().st_mtime_ns,
    )
    return f"http://127.0.0.1:{port}/index.html?v={version}"


def main():
    args = sys.argv[1:]
    if args and args[0] == "--serve":
        port = int(args[1]) if len(args) > 1 else PORT
        serve(port)
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
    elif "--build" in args:
        build()
    else:
        build_if_stale()
    if "--build" in args:
        return
    webbrowser.open(local_url())


if __name__ == "__main__":
    main()
