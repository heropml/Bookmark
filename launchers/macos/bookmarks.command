#!/bin/bash
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
if [ -z "$1" ]; then
  python3 -X utf8 "$ROOT/scripts/manage.py" --replace "$ROOT/data/bookmarks.html"
else
  python3 -X utf8 "$ROOT/scripts/manage.py" --replace "$1"
fi
echo
read -r -p "按回车键退出..."
