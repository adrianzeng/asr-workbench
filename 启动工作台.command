#!/bin/bash
# macOS: double-click this file in Finder. Linux: run `bash 启动工作台.command`.
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8

if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  PY=python3
elif python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  PY=python
else
  echo
  echo "  没找到 Python 3.10 或更新版本。"
  echo "  请先到 https://www.python.org/downloads/ 下载安装，"
  echo "  或者用 Homebrew 执行： brew install python"
  echo
  read -r -p "  按回车键关闭窗口" _
  exit 1
fi

"$PY" start.py
echo
read -r -p "  按回车键关闭窗口" _
