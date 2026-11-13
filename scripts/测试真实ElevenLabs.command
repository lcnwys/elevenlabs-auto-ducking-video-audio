#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then echo '请先安装 FFmpeg'; exit 1; fi
python3 -m pip show httpx >/dev/null 2>&1 || python3 -m pip install -r requirements.txt
printf '\n第一步：免费检查授权（不生成媒体）\n'
python3 scripts/live_smoke.py
printf '\n如确认测试费用与 API Key 权限，可再次运行：\n'
printf '  python3 scripts/live_smoke.py --paid\n'
