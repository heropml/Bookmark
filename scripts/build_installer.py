"""Build a Windows installer from public files, never local bookmarks/settings."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TREES = ("web/", "assets/icons/", "runtime/python/", "launchers/windows/")
PUBLIC_FILES = {
    "README.md", "LICENSE", "data/bookmarks.example.html",
    "scripts/manage.py", "scripts/archive_update.py", "scripts/shortcut.py",
}
REQUIRED = PUBLIC_FILES | {
    "web/index.html", "web/data.example.js", "web/js/update.js",
    "web/js/bookmark-sync.js", "web/css/bookmark-sync.css",
    "runtime/python/python.exe", "runtime/python/pythonw.exe",
    "assets/icons/bookmark.ico", "assets/icons/icon-aurora.ico",
    "launchers/windows/start.vbs", "launchers/windows/replace.bat",
    "launchers/windows/sync-chrome.bat", "launchers/windows/sync-edge.bat",
}


def public_file(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        return False
    if "\\" in name or ":" in name or name.lower() in (
        "web/data.js", "launchers/windows/build-installer.bat",
    ):
        return False
    if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
        return False
    if path.suffix.lower() in (".pyc", ".pyo", ".lnk"):
        return False
    return name in PUBLIC_FILES or name.startswith(PUBLIC_TREES)


def package_files(root: Path) -> list[str]:
    # Git is a build-time dependency only. Do not sweep untracked user files.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"], cwd=root, check=True,
        stdout=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    tracked = result.stdout.decode("utf-8").split("\0")
    names = sorted({name for name in tracked if public_file(name)} | REQUIRED)
    for name in names:
        source = root / name
        if not source.is_file():
            raise ValueError(f"Missing package file: {name}")
        for part in (source, *source.parents):
            if part == root:
                break
            if part.is_symlink() or part.is_junction():
                raise ValueError(f"Package file uses a link: {name}")
    return names


def app_version(root: Path) -> str:
    source = (root / "scripts/manage.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION = "v(\d+\.\d+\.\d+)"$', source, re.M)
    if not match:
        raise ValueError("Cannot read APP_VERSION from scripts/manage.py")
    version = match[1]
    page = (root / "web/index.html").read_text(encoding="utf-8")
    page_version = re.search(r'<div\b[^>]*\bid="appVersion"[^>]*>\s*v(\d+\.\d+\.\d+)\s*</div>', page)
    if not page_version or page_version[1] != version:
        raise ValueError("web/index.html and scripts/manage.py versions disagree")
    return version


def find_compiler(explicit: str | None = None) -> Path:
    candidates = [Path(explicit)] if explicit else []
    if not explicit:
        if found := shutil.which("ISCC.exe"):
            candidates.append(Path(found))
        for variable, suffix in (
            ("LOCALAPPDATA", "Programs/Inno Setup 6/ISCC.exe"),
            ("ProgramFiles(x86)", "Inno Setup 6/ISCC.exe"),
            ("ProgramFiles", "Inno Setup 6/ISCC.exe"),
        ):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / suffix)
    for candidate in candidates:
        if candidate.is_file():
            if not (candidate.parent / "Languages/ChineseSimplified.isl").is_file():
                raise ValueError("Inno Setup needs Languages/ChineseSimplified.isl (see README)")
            return candidate.resolve()
    raise ValueError("Install Inno Setup 6, or pass --iscc C:/path/to/ISCC.exe")


def runtime_payload(root: Path) -> dict[str, bytes]:
    # Older Windows checkouts can retain CRLF despite the current -text attribute.
    # Ship canonical Git bytes so the online updater's blob checks agree.
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", "HEAD", "runtime/python"], cwd=root,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        for member in stream:
            if not member.isfile() or not public_file(member.name):
                continue
            data = stream.extractfile(member).read()
            local = (root / member.name).read_bytes()
            if local != data and local.replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                raise ValueError(f"Commit runtime changes before packaging: {member.name}")
            result[member.name] = data
    return result


def build(root: Path, output: Path, compiler: Path, *, test_install: bool = False) -> Path:
    root, output = root.resolve(), output.resolve()
    version = app_version(root)
    names = package_files(root)
    runtime = runtime_payload(root)
    output.mkdir(parents=True, exist_ok=True)
    filename = "Bookmark_TestSetup" if test_install else f"Bookmark_Setup_v{version}"
    installer = output / f"{filename}.exe"
    with tempfile.TemporaryDirectory(prefix="bookmark-installer-") as staging:
        payload = Path(staging) / "payload"
        manifest = {}
        for name in names:
            destination = payload / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name.startswith("runtime/python/"):
                if name not in runtime:
                    raise ValueError(f"Runtime file is not committed: {name}")
                destination.write_bytes(runtime[name])
            else:
                shutil.copy2(root / name, destination)
            manifest[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
        command = [
            str(compiler), "/Qp", f"/DAppVersion={version}", f"/DPayloadDir={payload}",
            f"/DOutputPath={output}",
        ]
        if test_install:
            command.append("/DTestInstall=1")
        command.append(str(root / "scripts/Bookmark.iss"))
        subprocess.run(command, check=True)
    if not installer.is_file():
        raise ValueError("Compiler returned without producing an installer")
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    (output / f"{filename}.sha256").write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
    (output / f"{filename}.manifest.json").write_text(
        json.dumps({"version": version, "files": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Built {installer} ({installer.stat().st_size:,} bytes; {len(names)} public files)")
    return installer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", help="Path to Inno Setup 6 ISCC.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "installer")
    args = parser.parse_args()
    try:
        build(ROOT, args.output, find_compiler(args.iscc))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Installer build failed: {error}\n")


if __name__ == "__main__":
    main()
