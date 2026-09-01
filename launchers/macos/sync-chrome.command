#!/bin/bash
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
python3 -X utf8 "$ROOT/scripts/manage.py" --sync-chrome --build
STATUS=$?
echo
if [ "$STATUS" -eq 0 ]; then
  echo "Google Chrome 书签同步完成。"
else
  echo "Google Chrome 书签同步失败。"
fi
read -r -p "按回车键退出..."
exit "$STATUS"
