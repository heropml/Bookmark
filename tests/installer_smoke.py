"""Opt-in Windows installer lifecycle test; uses a separate test AppId and folder.

Run: runtime/python/python.exe -B -X utf8 tests/installer_smoke.py
Installs only a test product for the current user; never opens a browser.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
import winreg

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_installer", ROOT / "scripts/build_installer.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
TEST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{B4B29C9F-9207-4F89-9527-08E353DE5D29}_is1"


def installed():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY):
            return True
    except FileNotFoundError:
        return False


def run(command):
    result = subprocess.run(command, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}")


def main():
    if installed():
        raise RuntimeError("A previous test product is registered; refusing to replace it")
    (ROOT / "installer").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="verify-", dir=ROOT / "installer"))
    target = work / "书签 安装测试"
    print(f"Test directory: {work}", flush=True)
    setup = builder.build(ROOT, work, builder.find_compiler(), test_install=True)
    flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER"]
    install_args = [str(setup), *flags, f"/DIR={target}", "/GROUP=Bookmark Installer Test", "/TASKS=", "/LANG=chinesesimp"]
    service = None
    uninstaller = target / "unins000.exe"
    report = {}
    try:
        run([*install_args, f"/LOG={work / 'install.log'}"])
        assert installed(), "Test uninstall registration missing"
        manifest = json.loads((work / "Bookmark_TestSetup.manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files"].items():
            assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest, name
        assert not (target / ".git").exists()
        assert not (target / "data/bookmarks.html").exists()
        assert not (target / "web/data.js").exists()
        report["installation"] = f"{len(manifest['files'])} public files match SHA-256"
        print(report["installation"], flush=True)
        menu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Bookmark Installer Test"
        assert len(list(menu.glob("*.lnk"))) == 5, "Start menu entries missing"
        report["start_menu"] = "5 shortcuts created in the isolated test group"

        shutil.copy2(target / "data/bookmarks.example.html", target / "data/bookmarks.html")
        private = {
            "data/.window-state.json": b'{"test":true}',
            "data/.update-backups/fixture/old.txt": b"previous application fixture",
        }
        for name, content in private.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        python = target / "runtime/python/python.exe"
        manage = target / "scripts/manage.py"
        run([str(python), "-B", "-X", "utf8", str(manage), "--build"])
        for name in ("data/bookmarks.html", "web/data.js"):
            private[name] = (target / name).read_bytes()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        service = subprocess.Popen(
            [str(python), "-B", "-X", "utf8", str(manage), "--serve", str(port)],
            cwd=target, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                with urlopen(f"http://127.0.0.1:{port}/__service", timeout=1) as response:
                    status = json.load(response)
                break
            except OSError:
                if service.poll() is not None:
                    raise RuntimeError("Installed service exited before startup")
                time.sleep(.1)
        else:
            raise RuntimeError("Installed service did not become ready")
        assert status["version"] == "v" + manifest["version"]
        with urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as response:
            assert response.status == 200
        report["service"] = f"Installed Python serves v{manifest['version']} on isolated port {port}"
        print(report["service"], flush=True)

        # A running embedded Python must be closed by Restart Manager only for this install.
        run([*install_args, f"/LOG={work / 'reinstall.log'}"])
        service.wait(timeout=15)
        service = None
        for name, content in private.items():
            assert (target / name).read_bytes() == content, name
        report["reinstall"] = "Running test service closed; all private fixtures preserved"
        print(report["reinstall"], flush=True)
        run([str(python), "-B", "-X", "utf8", str(manage), "--build"])
        service = subprocess.Popen(
            [str(python), "-B", "-X", "utf8", str(manage), "--serve", str(port)],
            cwd=target, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                with urlopen(f"http://127.0.0.1:{port}/__service", timeout=1) as response:
                    assert json.load(response)["version"] == "v" + manifest["version"]
                break
            except OSError:
                if service.poll() is not None:
                    raise RuntimeError("Reinstalled service exited before startup")
                time.sleep(.1)
        else:
            raise RuntimeError("Reinstalled service did not become ready")
        run([str(uninstaller), *flags[:3], f"/LOG={work / 'uninstall.log'}"])
        assert service.poll() is not None, "Uninstall left the installed service running"
        service = None
        for name, content in private.items():
            assert (target / name).read_bytes() == content, name
        assert not python.exists(), "Installed runtime was not removed"
        assert not manage.exists(), "Installed application was not removed"
        assert not installed(), "Test uninstall registration remains"
        assert not list(menu.glob("*.lnk")), "Test shortcuts remain"
        report["uninstall"] = "Running service, application and shortcuts removed; all private fixtures preserved"
        print(report["uninstall"], flush=True)
    finally:
        if service is not None and service.poll() is None:
            service.terminate()
            service.wait(timeout=10)
        if installed() and uninstaller.is_file():
            run([str(uninstaller), *flags[:3], f"/LOG={work / 'cleanup.log'}"])
        (work / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Logs retained: {work}", flush=True)


if __name__ == "__main__":
    main()
