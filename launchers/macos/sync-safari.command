#!/bin/bash
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
python3 -X utf8 "$ROOT/scripts/manage.py" --sync-safari --build
STATUS=$?
echo
if [ "$STATUS" -eq 0 ]; then
  echo "Safari 书签同步完成。"
else
  echo "Safari 书签同步失败。"
  echo "如果提示无权访问，请在系统设置中允许 Terminal 访问 Safari 数据。"
fi
read -r -p "按回车键退出..."
exit "$STATUS"
