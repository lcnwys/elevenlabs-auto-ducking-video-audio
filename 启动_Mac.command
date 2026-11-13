#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "未检测到 FFmpeg。可先通过 Homebrew 安装： brew install ffmpeg"
  read -r -p "按回车关闭…" _
  exit 1
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
printf '\nDemo 已准备启动，请在浏览器打开 http://127.0.0.1:8765\n'
printf '按 Ctrl+C 可以关闭服务。\n\n'
exec python -m uvicorn app:app --host 127.0.0.1 --port 8765
