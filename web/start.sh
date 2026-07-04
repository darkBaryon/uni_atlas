#!/bin/bash
# 留学申请信息库 · 前端启动脚本
# 用法:
#   ./web/start.sh          刷新数据并用浏览器打开（file:// 即可运行）
#   ./web/start.sh --serve  刷新数据并起本地静态服务器 (http://localhost:8930)
#   ./web/start.sh --no-export   跳过导出直接打开（数据没变时更快）
set -e
cd "$(dirname "$0")"

if [[ "$1" != "--no-export" ]]; then
  echo "▸ 从 MySQL 导出最新数据 ..."
  python3 export.py
fi

if [[ "$1" == "--serve" ]]; then
  PORT=8930
  echo "▸ http://localhost:${PORT} （Ctrl-C 停止）"
  ( sleep 1 && open "http://localhost:${PORT}" ) &
  exec python3 -m http.server "$PORT"
else
  echo "▸ 打开页面: file://$(pwd)/index.html"
  open index.html
fi
