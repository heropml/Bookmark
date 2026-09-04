"""PyInstaller entry point for the self-contained macOS application."""
from __future__ import annotations

import json
import os
import shutil
import sys
import webbrowser
from pathlib import Path

BUNDLE_TREES = ("web", "assets", "data")
# Records what the previous app bundle installed, so only our own files are pruned.
BUNDLE_MANIFEST = "data/.bundle-files.json"
# Never shipped in a bundle, so never pruned even if a manifest claims otherwise.
PRIVATE_FILES = frozenset({"web/data.js", "data/bookmarks.html", "data/.window-state.json", BUNDLE_MANIFEST})
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


def copy_resources(bundle: Path, root: Path, names: list[str]) -> None:
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle / name, target)


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
    previous = installed_files(root)
    copy_resources(bundle, root, names)
    prune_removed_files(root, previous, set(names))
    manifest = root / BUNDLE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def open_page(manage) -> None:
    manage.build()
    port = manage.pick_port()
    if not manage.page_ok(port):
        manage.serve_hidden(port)
    version = "%s-%s" % (
        manage.WEB_ROOT.joinpath("index.html").stat().st_mtime_ns,
        manage.DATA_JS.stat().st_mtime_ns,
    )
    url = f"http://127.0.0.1:{port}/index.html?v={version}"
    webbrowser.open(url)


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
