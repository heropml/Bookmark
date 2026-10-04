# -*- coding: utf-8 -*-
"""Online updates: Git checkouts fast-forward main, ZIP installs use archive_update, and the macOS app
only reports a newer DMG."""
from __future__ import annotations

import os
import subprocess
import sys
import threading

import archive_update
import settings

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
            cwd=settings.ROOT,
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
        status = archive_update.update_status(settings.APP_VERSION, progress)
    except archive_update.ArchiveUpdateError as error:
        raise UpdateError(str(error), error.code) from error
    source = str(status.get("source") or "Gitee")
    return {
        "available": bool(status.get("available")),
        "can_update": False,
        "mode": "dmg",
        "version": settings.APP_VERSION,
        "current": settings.APP_VERSION,
        "remote": status.get("remote"),
        "source": source,
        "download": PACKAGED_RELEASES.get(source, PACKAGED_RELEASES["Gitee"]),
        "reason": PACKAGED_REASON,
    }


def repository_update_status(progress=None) -> dict[str, object]:
    """Serialize checks with upgrades so concurrent pages cannot race Git writes."""
    if settings.PACKAGED_APP:
        return packaged_update_status(progress)
    with UPDATE_LOCK:
        if not os.path.lexists(settings.ROOT / ".git"):
            try:
                return archive_update.update_status(settings.APP_VERSION, progress)
            except archive_update.ArchiveUpdateError as error:
                raise UpdateError(str(error), error.code) from error
        return _repository_update_status(progress)


def _repository_update_status(progress=None) -> dict[str, object]:
    """Try Gitee first, then GitHub; never overwrite local code changes."""
    version = {"version": settings.APP_VERSION}
    if progress:
        progress({"stage": "checking", "message": "检查本地修改与升级条件"})
    if not (settings.ROOT / ".git").is_dir():
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
    if settings.PACKAGED_APP:
        raise UpdateError(PACKAGED_REASON)
    if progress:
        progress({"stage": "waiting", "message": "等待本地升级任务就绪"})
    with UPDATE_LOCK:
        if not os.path.lexists(settings.ROOT / ".git"):
            try:
                return archive_update.install(settings.ROOT, settings.APP_VERSION, progress)
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
    match = settings.VERSION_LINE_RE.search(settings.MANAGE_SCRIPT.read_text(encoding="utf-8"))
    if not match:
        raise UpdateError("无法读取已安装版本")
    return match.group(1)
