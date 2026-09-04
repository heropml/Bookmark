#!/usr/bin/env bash
# Build the arm64 macOS app bundle, optionally wrapped in a drag-to-Applications DMG.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_NAME="Bookmark"
VERSION="$(python3.11 - <<'PY'
import re
from pathlib import Path

source = Path("scripts/manage.py").read_text(encoding="utf-8")
match = re.search(r'^APP_VERSION\s*=\s*"v([^"]+)"', source, re.M)
if not match:
    raise SystemExit("Could not read APP_VERSION from scripts/manage.py")
print(match.group(1))
PY
)"
BUILD_DIR="build_macos"
DIST_DIR="dist"
VENV="$BUILD_DIR/.venv"
APP="$DIST_DIR/$APP_NAME.app"
RESOURCE_STAGE="$BUILD_DIR/resources"

if [ "$(uname -m)" != "arm64" ]; then
    echo "Official macOS builds must run on an Apple Silicon (arm64) host."
    exit 1
fi

if ! command -v python3.11 >/dev/null 2>&1; then
    echo "Need Python 3.11 to build the macOS release."
    exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
    python3.11 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install 'PyInstaller>=6.0' >/dev/null

rm -rf "$RESOURCE_STAGE"
while IFS= read -r path; do
    case "$path" in
        web/*|assets/*|data/bookmarks.example.html)
            mkdir -p "$RESOURCE_STAGE/$(dirname "$path")"
            cp -p "$path" "$RESOURCE_STAGE/$path"
            ;;
    esac
done < <(git ls-files)

rm -rf "$APP"
"$VENV/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --icon "$PWD/launchers/macos/Bookmark.app/Contents/Resources/AppIcon.icns" \
    --osx-bundle-identifier local.bookmark.homepage \
    --target-architecture arm64 \
    --add-data "$PWD/$RESOURCE_STAGE/web:bookmark/web" \
    --add-data "$PWD/$RESOURCE_STAGE/assets:bookmark/assets" \
    --add-data "$PWD/$RESOURCE_STAGE/data/bookmarks.example.html:bookmark/data" \
    --paths scripts \
    --distpath "$DIST_DIR" \
    --specpath "$BUILD_DIR/pyinstaller" \
    --workpath "$BUILD_DIR/pyinstaller" \
    scripts/macos_app.py

test ! -e "$APP/Contents/Resources/bookmark/web/data.js"
test ! -e "$APP/Contents/Resources/bookmark/data/bookmarks.html"
plutil -replace CFBundleDisplayName -string "书签" "$APP/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool true "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

if [ "${1:-}" = "--dmg" ]; then
    STAGE="$BUILD_DIR/dmg"
    DMG="$DIST_DIR/${APP_NAME}_v${VERSION}_macos_arm64.dmg"
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    ditto "$APP" "$STAGE/$APP_NAME.app"
    ln -s /Applications "$STAGE/Applications"
    rm -f "$DMG"
    hdiutil create -volname "书签" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
    hdiutil verify "$DMG" >/dev/null
    # Record the bare file name, as the Windows installer does, so the checksum
    # verifies wherever the user saved the DMG.
    (cd "$DIST_DIR" && shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256")
    echo "DMG: $DMG"
fi

echo "App: $APP"
