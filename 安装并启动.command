#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "请先安装 Python 3.10 或更新版本：https://www.python.org/downloads/"
  read -r -p "按回车键关闭…"
  exit 1
fi
python3 bootstrap.py "$@"
result=$?
if [ "$result" -ne 0 ]; then
  read -r -p "请查看上方提示，按回车键关闭…"
fi
exit "$result"
