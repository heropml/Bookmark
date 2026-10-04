# -*- coding: utf-8 -*-
"""Find each browser's bookmarks on this computer and import them into the homepage."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import bookmark_store
from bookmark_formats import parse_chrome, parse_safari


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


def safari_bookmarks_file() -> Path:
    return Path.home() / "Library" / "Safari" / "Bookmarks.plist"


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


def sync_chrome(profile: str | None = None):
    profile, path = chrome_bookmarks_file(profile)
    print(f"Chrome profile: {profile} ({path.name})")
    bookmark_store.write_bookmarks_html(parse_chrome(path))
    return bookmark_store.build()


def sync_edge(profile: str | None = None):
    profile, path = edge_bookmarks_file(profile)
    print(f"Edge profile: {profile} ({path.name})")
    bookmark_store.write_bookmarks_html(parse_chrome(path))
    return bookmark_store.build()


def sync_safari():
    path = safari_bookmarks_file()
    print(f"Safari bookmarks: {path}")
    bookmark_store.write_bookmarks_html(parse_safari(path))
    return bookmark_store.build()


def sync_chromium(browser: str):
    profile, path = chromium_bookmarks_file(browser)
    print(f"{WINDOWS_CHROMIUM_BROWSERS[browser][0]} profile: {profile} ({path.name})")
    bookmark_store.write_bookmarks_html(parse_chrome(path))
    return bookmark_store.build()


def sync_html():
    path = pick_html()
    if path is None:
        raise SystemExit("bookmark HTML was not selected")
    if not path.is_file():
        raise SystemExit("bookmark HTML was not found")
    bookmark_store.replace_src(path)
    return bookmark_store.build()


def sync(browser: str):
    """Replace the homepage bookmarks from one of supported_sync_browsers()."""
    action = {
        "chrome": sync_chrome, "edge": sync_edge, "safari": sync_safari, "html": sync_html,
        **{key: lambda key=key: sync_chromium(key) for key in WINDOWS_CHROMIUM_BROWSERS},
    }[browser]
    return action()
