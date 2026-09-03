"""Git-free updates for ZIP installations; never replace personal data."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

SOURCES = ("Gitee", "GitHub")
API_ROOTS = {"Gitee": "https://gitee.com/api/v5/repos/heropml/Bookmark",
             "GitHub": "https://api.github.com/repos/heropml/Bookmark"}
RAW_ROOTS = {"Gitee": "https://gitee.com/heropml/Bookmark/raw",
             "GitHub": "https://raw.githubusercontent.com/heropml/Bookmark"}
HOSTS = {"gitee.com", "raw.giteeusercontent.com", "api.github.com", "raw.githubusercontent.com"}
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
TIMEOUT = 15
DOWNLOAD_SECONDS = 180
REQUIRED = {"scripts/manage.py", "scripts/archive_update.py", "web/index.html", "web/js/update.js"}


class ArchiveUpdateError(RuntimeError):
    def __init__(self, message, code="archive_update_failed"):
        super().__init__(message)
        self.code = code


def _trusted(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ArchiveUpdateError("更新地址不可信，已停止下载")


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _trusted(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(source, url, limit, deadline=None):
    """Use system trust, bounded reads, and only the official HTTPS hosts."""
    _trusted(url)
    deadline = deadline if deadline is not None else time.monotonic() + TIMEOUT
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        proxy = ProxyHandler({}) if source == "Gitee" else ProxyHandler()
        opener = build_opener(proxy, HTTPSHandler(context=ssl.create_default_context()), _SafeRedirect())
        request = Request(url, headers={"User-Agent": "Bookmark-Updater", "Cache-Control": "no-cache"})
        with opener.open(request, timeout=min(TIMEOUT, remaining)) as response:
            _trusted(response.geturl())
            data = bytearray()
            read = getattr(response, "read1", response.read)
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                chunk = read(min(65536, limit + 1 - len(data)))
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
                if len(data) > limit:
                    raise ArchiveUpdateError("更新文件超出大小限制")
    except (OSError, URLError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise ArchiveUpdateError("证书验证失败，请检查系统时间、系统根证书或公司网络证书配置（未关闭证书校验）", "certificate_error") from error
        raise ArchiveUpdateError("更新源连接失败或请求超时", "sources_unavailable") from error


def _json(source, url, deadline=None):
    try:
        return json.loads(read_url(source, url, 4 * 1024 * 1024, deadline))
    except (ValueError, UnicodeError) as error:
        raise ArchiveUpdateError("更新源返回的版本信息无效") from error


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ArchiveUpdateError("更新源返回的校验值无效")
    return value


def _version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ArchiveUpdateError("版本号格式无效")
    return tuple(map(int, match.groups()))


def _source_version(data):
    try:
        match = re.search(r'^APP_VERSION\s*=\s*["\'](v?\d+\.\d+\.\d+)["\']\s*$', data.decode("utf-8"), re.M)
    except UnicodeError:
        match = None
    if not match:
        raise ArchiveUpdateError("更新源缺少有效版本号")
    return match.group(1)


def _raw(source, commit, path):
    return f"{RAW_ROOTS[source]}/{commit}/{quote(path, safe='/')}"


def _report(progress, stage, message, source=""):
    if progress:
        progress({"stage": stage, "message": message, "source": source})


def update_status(version, progress=None):
    _report(progress, "checking", "检查 ZIP 安装的可用版本")
    current = _version(version)
    errors, error_code = [], "sources_unavailable"
    for source in SOURCES:
        try:
            info = _json(source, f"{API_ROOTS[source]}/commits/main")
            commit = _sha(info["sha"])
            tree = _sha(info["commit"]["tree"]["sha"])
            remote = _source_version(read_url(source, _raw(source, commit, "scripts/manage.py"), 512 * 1024))
            return {"available": _version(remote) > current, "can_update": True, "mode": "archive",
                    "version": version, "current": version, "remote": remote,
                    "target": commit, "tree": tree, "source": source}
        except (ArchiveUpdateError, KeyError, TypeError) as error:
            errors.append(f"{source}：{error}" if isinstance(error, ArchiveUpdateError) else f"{source}：版本信息不完整")
            if getattr(error, "code", "") == "certificate_error":
                error_code = error.code
    raise ArchiveUpdateError("所有更新源均不可用；" + "；".join(errors), error_code)


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ArchiveUpdateError("更新清单包含无效路径")
    parts = value.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part.endswith((" ", "."))
                or any(ord(char) < 32 or char in '\\:<>"|?*' for char in part)
                or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ArchiveUpdateError("更新清单包含不安全路径")
    return value


def _managed(path):
    lower = path.casefold()
    if lower == "web/data.js" or lower.endswith((".pyc", ".pyo", ".lnk")) or "/__pycache__/" in lower:
        return False
    return lower.startswith(("web/", "scripts/", "assets/", "launchers/")) or lower in {
        "readme.md", "license", "data/bookmarks.example.html"}


def _destination(root, path):
    dest = root
    parts = _path(path).split("/")
    for index, part in enumerate(parts):
        dest = dest / part
        if dest.is_symlink() or getattr(dest, "is_junction", lambda: False)():
            raise ArchiveUpdateError("程序目录包含链接，已停止覆盖")
        if dest.exists() and (not dest.is_file() if index == len(parts) - 1 else not dest.is_dir()):
            raise ArchiveUpdateError("程序文件与现有目录冲突，已停止覆盖")
    return dest


def blob_hash(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _file_hash(path):
    if not path.exists():
        return None
    digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(info):
    if not isinstance(info, dict) or info.get("truncated") is not False or not isinstance(info.get("tree"), list) or len(info["tree"]) > 10000:
        raise ArchiveUpdateError("更新文件清单不完整，已停止升级")
    files, seen = {}, set()
    for item in info["tree"]:
        try:
            path = _path(item["path"])
            if path.casefold() in seen:
                raise ArchiveUpdateError("更新清单包含重复路径")
            seen.add(path.casefold())
            if item["type"] == "tree":
                continue
            if not (_managed(path) or path.startswith("runtime/")):
                continue
            if item["type"] != "blob" or item["mode"] not in ("100644", "100755"):
                raise ArchiveUpdateError("更新清单包含不支持的链接或文件类型")
            size = item["size"]
            if type(size) is not int or not 0 <= size <= MAX_FILE:
                raise ArchiveUpdateError("更新文件超出大小限制")
            files[path] = {"sha": _sha(item["sha"]), "size": size, "mode": item["mode"]}
        except (KeyError, TypeError) as error:
            raise ArchiveUpdateError("更新文件清单格式无效") from error
    if not REQUIRED.issubset(files):
        raise ArchiveUpdateError("更新清单缺少必要的程序文件")
    return files


def _from_sources(primary, operation, progress):
    errors, code = [], "sources_unavailable"
    order = SOURCES[SOURCES.index(primary):]
    for source in order:
        try:
            return operation(source), source
        except ArchiveUpdateError as error:
            errors.append(f"{source}：{error}")
            if error.code == "certificate_error":
                code = error.code
            if source != order[-1]:
                _report(progress, "fetching", "Gitee 下载不可用，切换 GitHub 下载同一版本", "GitHub")
    raise ArchiveUpdateError("下载失败；" + "；".join(errors), code)


def _apply(root, stage, changes, originals, progress, source):
    if os.path.lexists(root / ".git"):
        raise ArchiveUpdateError("安装目录已变为 Git 仓库，已取消 ZIP 升级")
    # Backups live outside web/. All original files are copied before any replacement.
    _destination(root, "data/.update-backups/placeholder")
    backup_root = root / "data/.update-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="backup-", dir=backup_root))
    order = sorted(changes, key=lambda path: (path == "scripts/manage.py", path == "web/index.html", path))
    for path in order:
        dest = _destination(root, path)
        if _file_hash(dest) != originals[path]:
            raise ArchiveUpdateError("下载期间程序文件发生变化，已取消升级")
        if dest.exists():
            saved = backup / path
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
    (backup / "files.json").write_text(json.dumps(originals, ensure_ascii=False, indent=2), encoding="utf-8")
    applied = []
    try:
        for index, path in enumerate(order, 1):
            dest = _destination(root, path)
            if _file_hash(dest) != originals[path]:
                raise ArchiveUpdateError("程序文件发生变化，已停止升级")
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / path, dest)
            applied.append(path)
            _report(progress, "applying", f"应用程序文件 {index}/{len(order)}，保留私人书签", source)
    except (OSError, ArchiveUpdateError) as error:
        failed = []
        for path in reversed(applied):
            try:
                dest = _destination(root, path)
                if _file_hash(dest) != changes[path]["sha"]:
                    failed.append(path)
                    continue
                if originals[path] is None:
                    dest.unlink()
                else:
                    shutil.copy2(backup / path, dest)
            except (OSError, ArchiveUpdateError):
                failed.append(path)
        suffix = f"部分文件恢复失败，请保留备份：{backup}" if failed else f"已恢复原文件，备份位于：{backup}"
        raise ArchiveUpdateError("升级未完成；" + suffix) from error
    return str(backup)


def install(root, version, progress=None):
    root = Path(root).resolve()
    status = update_status(version, progress)
    if not status["available"]:
        return {"ok": True, "updated": False, **status}
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    source = status["source"]
    _report(progress, "fetching", "读取新版程序文件清单", source)

    def read_manifest(candidate):
        return _manifest(_json(candidate, f"{API_ROOTS[candidate]}/git/trees/{status['tree']}?recursive=1", deadline))

    files, source = _from_sources(source, read_manifest, progress)
    changes, originals = {}, {}
    try:
        for path, item in files.items():
            if path.startswith("runtime/") and sys.platform != "win32":
                continue
            dest = _destination(root, path)
            previous = _file_hash(dest)
            if previous == item["sha"]:
                continue
            if path.startswith("runtime/"):
                raise ArchiveUpdateError("新版便携 Python 运行时有变化，请下载完整安装包；当前程序未改动")
            changes[path], originals[path] = item, previous
        if sum(item["size"] for item in changes.values()) > MAX_TOTAL:
            raise ArchiveUpdateError("本次更新文件总量超出限制")
        _destination(root, "data/.update-stage/placeholder")
        (root / "data").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".update-stage-", dir=root / "data") as temporary:
            stage = Path(temporary)
            for index, (path, item) in enumerate(changes.items(), 1):
                _report(progress, "fetching", f"下载并校验程序文件 {index}/{len(changes)}：{path}", source)

                def download(candidate):
                    data = read_url(candidate, _raw(candidate, status["target"], path), item["size"], deadline)
                    if len(data) != item["size"] or blob_hash(data) != item["sha"]:
                        raise ArchiveUpdateError("下载文件校验失败，未应用更新")
                    return data

                data, source = _from_sources(source, download, progress)
                target = stage / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if item["mode"] == "100755" else 0o644)
            backend = (stage / "scripts/manage.py") if "scripts/manage.py" in changes else root / "scripts/manage.py"
            if _source_version(backend.read_bytes()) != status["remote"]:
                raise ArchiveUpdateError("下载的版本与已确认版本不一致")
            _report(progress, "applying", "备份现有程序，准备应用新版文件", source)
            backup = _apply(root, stage, changes, originals, progress, source)
    except OSError as error:
        raise ArchiveUpdateError("程序文件无法读写或磁盘空间不足，升级未完成") from error
    return {"ok": True, "updated": True, "mode": "archive", "previous": version,
            "current": status["remote"], "source": source, "backup": backup}
