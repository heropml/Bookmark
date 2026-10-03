"""PyInstaller entry point for the self-contained macOS application."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
import webbrowser
from pathlib import Path

BUNDLE_TREES = ("web", "assets", "data")
# Records what the previous app bundle installed, so only our own files are pruned.
BUNDLE_MANIFEST = "data/.bundle-files.json"
# Fingerprint of the bundle last copied; an unchanged app skips copying on every launch.
BUNDLE_STAMP = "data/.bundle-stamp"
# Never shipped in a bundle, so never pruned even if a manifest claims otherwise.
PRIVATE_FILES = frozenset({"web/data.js", "data/bookmarks.html", "data/.window-state.json",
                           "data/.data-build.json", BUNDLE_MANIFEST, BUNDLE_STAMP})
PRIVATE_TREES = ("data/.update-backups/", "data/.update-stage-")


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "bookmark"


def user_root() -> Path:
    override = os.environ.get("BOOKMARK_APP_SUPPORT")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Bookmark"


def bundle_files(bundle: Path) -> list[str]:
    """Public files this app bundle ships, as root-relative POSIX paths."""
    names = []
    for tree in BUNDLE_TREES:
        source = bundle / tree
        if not source.is_dir():
            continue
        names += [f"{tree}/{path.relative_to(source).as_posix()}"
                  for path in source.rglob("*") if path.is_file()]
    return sorted(names)


def bundle_fingerprint(bundle: Path, names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        stat = (bundle / name).stat()
        digest.update(f"{name}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()


def copy_resources(bundle: Path, root: Path, names: list[str]) -> None:
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # A running service may be sending this file; swap it in whole rather than overwrite it.
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            shutil.copy2(bundle / name, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def installed_files(root: Path) -> list[str]:
    """Read the previous manifest; anything unreadable simply prunes nothing."""
    try:
        recorded = json.loads((root / BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(recorded, list):
        return []
    return [name for name in recorded if isinstance(name, str) and prunable(name)]


def prunable(name: str) -> bool:
    """Only public files inside the bundle trees may be removed on an upgrade."""
    if not name.startswith(tuple(tree + "/" for tree in BUNDLE_TREES)) or name.endswith("/"):
        return False
    if any(part in ("", ".", "..") for part in name.split("/")):
        return False
    return name not in PRIVATE_FILES and not name.startswith(PRIVATE_TREES)


def prune_removed_files(root: Path, previous: list[str], current: set[str]) -> None:
    """Drop files an older bundle installed. Private data is never in a manifest."""
    for name in sorted(set(previous) - current, reverse=True):
        target = root / name
        try:
            if target.is_file() and not target.is_symlink():
                target.unlink()
            for parent in target.parents:
                if parent == root or not parent.is_dir():
                    break
                parent.rmdir()
        except OSError:
            # A leftover file or a non-empty directory must not block startup.
            continue


def prepare_runtime() -> Path:
    root = user_root()
    bundle = bundle_root()
    names = bundle_files(bundle)
    fingerprint = bundle_fingerprint(bundle, names)
    stamp = root / BUNDLE_STAMP
    try:
        current = stamp.read_text(encoding="utf-8") == fingerprint
    except OSError:
        current = False
    # Both the launcher and its background service start here; copy only when the app changed
    # or a public file went missing.
    if current and all((root / name).is_file() for name in names):
        return root
    previous = installed_files(root)
    copy_resources(bundle, root, names)
    prune_removed_files(root, previous, set(names))
    manifest = root / BUNDLE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    stamp.write_text(fingerprint, encoding="utf-8")
    return root


def open_page(manage) -> None:
    manage.build_if_stale()
    webbrowser.open(manage.local_url())


def main() -> None:
    os.environ["BOOKMARK_ROOT"] = str(prepare_runtime())
    os.environ["BOOKMARK_PACKAGED"] = "1"
    import manage

    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        manage.main()
    else:
        open_page(manage)


if __name__ == "__main__":
    main()
