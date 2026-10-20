"""Opt-in check of the built macOS app using an isolated application support folder."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_installer import app_version  # noqa: E402


def main():
    app = ROOT / "dist/Bookmark.app"
    resources = app / "Contents/Resources/bookmark"
    for name in ("web/data.js", "data/bookmarks.html", "data/preferences.json", "data/.preferences-backups"):
        assert not (resources / name).exists(), f"Private content in bundle: {name}"
    for name in ("web/js/preferences.js", "web/js/preferences-ui.js"):
        assert (resources / name).is_file(), f"Missing resource: {name}"
    version = "v" + app_version(ROOT)
    with tempfile.TemporaryDirectory(prefix="bookmark-macos-smoke-") as folder:
        support = Path(folder)
        private = {
            "data/preferences.json": json.dumps({
                "format": 1, "revision": "a" * 32, "updated": 0,
                "values": {"bm-skin": "celadon", "bm-pins": '["https://example.com/"]'},
            }).encode("utf-8"),
            "data/.preferences-backups/fixture.json": b"private backup fixture",
            "data/bookmarks.html": b'<DL><DT><A HREF="https://example.com/">Private fixture</A></DL>',
        }
        for name, data in private.items():
            target = support / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        env = {**os.environ, "BOOKMARK_APP_SUPPORT": str(support)}
        # Launch twice: both initial bundle installation and reuse must preserve private data.
        for _ in range(2):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            process = subprocess.Popen([str(app / "Contents/MacOS/Bookmark"), "--serve", str(port)],
                                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/__service", timeout=1) as response:
                            assert json.load(response)["version"] == version
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError("Packaged app exited before serving") from None
                        time.sleep(.1)
                else:
                    raise RuntimeError("Packaged service failed to start")
                with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    page = response.read()
                    assert version.encode() in page
                    assert b'"bm-skin": "celadon"' in page
                for name, data in private.items():
                    assert (support / name).read_bytes() == data, name
            finally:
                process.terminate()
                process.wait(timeout=10)
    print(f"{version}: packaged service, resources and private configuration preservation passed")


if __name__ == "__main__":
    main()
