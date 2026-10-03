# -*- coding: utf-8 -*-
"""Create the Bookmark shortcuts and update their icon."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("BOOKMARK_ROOT", Path(__file__).resolve().parent.parent))
ICON_DIR = ROOT / "assets" / "icons"
WINDOWS_DIR = ROOT / "launchers" / "windows"
LNK = ROOT / ("\u4e66\u7b7e" + ".lnk")
LAUNCH = WINDOWS_DIR / "start.bat"
HIDDEN_LAUNCH = WINDOWS_DIR / "start.vbs"
MANAGE = ROOT / "scripts" / "manage.py"
SKINS = (
    "aurora", "cyber", "ember", "paper", "nebula", "prism", "obsidian", "abyss",
    "snow", "sakura", "celadon", "shuimo", "daiqing", "zhusha", "yemo",
)


def icon_path(skin: str = "aurora") -> Path:
    if skin not in SKINS:
        skin = "aurora"
    path = ICON_DIR / ("icon-%s.ico" % skin)
    return path if path.is_file() else ICON_DIR / "bookmark.ico"


def shortcut_files() -> list[Path]:
    desk = Path.home() / "Desktop" / LNK.name
    return [LNK, desk] if desk.parent.is_dir() else [LNK]


def shortcut_state() -> tuple:
    """Changes whenever a shortcut is written, recreated or removed, by this app or anything else."""
    state = []
    for path in shortcut_files():
        try:
            stat = path.stat()
            state.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            state.append((str(path), None, None))
    return tuple(state)


def write_lnk(icon: Path) -> None:
    target, arguments = launch_command()
    targets = shortcut_files()
    lines = ['Set w = CreateObject("WScript.Shell")']
    for dest in targets:
        lines += [
            'Set s = w.CreateShortcut("%s")' % _vbs_str(dest),
            's.TargetPath = "%s"' % _vbs_str(target),
            's.Arguments = "%s"' % _vbs_str(arguments),
            's.WorkingDirectory = "%s"' % _vbs_str(ROOT),
            's.IconLocation = "%s"' % _vbs_str(str(icon) + ",0"),
            "s.WindowStyle = 1",
            "s.Save",
        ]
    vbs = tempfile.NamedTemporaryFile("wb", suffix=".vbs", delete=False)
    try:
        vbs.write(b"\xff\xfe" + "\r\n".join(lines).encode("utf-16-le"))
        vbs.close()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [r"C:\Windows\System32\cscript.exe", "//nologo", vbs.name],
            creationflags=flags,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).strip())
    finally:
        os.unlink(vbs.name)


def launch_command() -> tuple[Path, str]:
    if HIDDEN_LAUNCH.is_file():
        wscript = Path(r"C:\Windows\System32\wscript.exe")
        return wscript, '//nologo "%s"' % HIDDEN_LAUNCH
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.is_file() and MANAGE.is_file():
        return pythonw, '-X utf8 "%s"' % MANAGE
    if not LAUNCH.is_file():
        raise SystemExit("missing start.bat")
    return LAUNCH, ""


def set_icon(skin: str) -> Path:
    icon = icon_path(skin)
    if not icon.is_file():
        raise SystemExit("missing " + icon.name)
    write_lnk(icon)
    return icon


def main() -> None:
    print(set_icon("aurora"))


def _vbs_str(path: Path | str) -> str:
    return str(path).replace('"', '""')


if __name__ == "__main__":
    main()
