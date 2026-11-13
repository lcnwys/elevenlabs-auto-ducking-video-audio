"""Short, explicitly authorized ElevenLabs integration smoke test.

Default: no billable calls. --paid: at most one Scribe request and one
Video-to-Music request for a video trimmed to 8 seconds. No automatic retries.
No key is saved to disk or printed to stdout/stderr.
"""
from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import group_words, probe_media, render_video  # noqa: E402
from elevenlabs_client import create_music, transcribe  # noqa: E402


def _configure_secret():
    key = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not key:
        key = getpass('ElevenLabs API Key（输入不会显示，也不会写入文件）: ').strip()
    if not key:
        raise ValueError('No key provided')
    os.environ['ELEVENLABS_API_KEY'] = key


def check_access() -> tuple[int, str]:
    """Non-billable auth check. 403 can also mean key scope restrictions."""
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            res = client.get('https://api.elevenlabs.io/v1/user',
                             headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']})
        if res.status_code == 200:
            return (200, '可访问 /v1/user（身份验证通过）')
        if res.status_code == 401:
            return (401, '认证拒绝；请检查密钥是否有效')
        if res.status_code == 403:
            return (403, '此 Key 无权访问 /v1/user；若只授权 Music/Scribe，不代表 Key 无效')
        return (res.status_code, f'/v1/user 状态码 {res.status_code}（无付费请求）')
    except httpx.RequestError as exc:
        return (0, f'网络错误：{type(exc).__name__}（无付费请求）')


def run_paid(out_dir: Path, seconds: int = 8):
    """Exactly one call per capability, no retries and no fallback model calls."""
    src = ROOT / 'samples' / 'sample_video.mp4'
    video = out_dir / 'probe_8s.mp4'
    subprocess.run(['ffmpeg', '-y', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-i', str(src), '-t', str(seconds), '-map', '0:v:0', '-map', '0:a:0?',
                    '-c:v', 'copy', '-c:a', 'copy', str(video)], check=True, timeout=40)
    duration = probe_media(video)['duration']
    if duration > seconds + 1:
        raise RuntimeError('Clip not short enough; refusing API calls')
    print(f'测试视频：{duration:.2f} 秒（合成样例，非客户数据）')
    print('1/2 请求 Scribe v2（仅调用一次，无重试）...')
    words = transcribe(video)
    (out_dir / 'scribe_result.json').write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding='utf-8')
    intervals = group_words(words['words'], gap=1.0, duration=duration)
    print(f'   Scribe 返回 {len(words["words"])} 个条目，合并出 {len(intervals)} 段讲话')
    print('2/2 请求 Video-to-Music music_v2_5（仅调用一次，无重试）...')
    music = out_dir / 'generated_music.mp3'
    create_music(video, music, description='Subtle clean cinematic instrumental background music, no vocals.')
    music_duration = probe_media(music)['duration']
    print(f'   返回有效 MP3：{music_duration:.2f} 秒')
    print('本地 FFmpeg 混音（不收费）...')
    output = out_dir / 'ducked_8s.mp4'
    render_video(video, music, output, intervals)
    print(f'   已输出：{output}')
    print(f'   结果目录：{out_dir}')


def main():
    ap = argparse.ArgumentParser(description='ElevenLabs 最小规模真实接口测试')
    ap.add_argument('--paid', action='store_true', help='明确授权每种接口最多发出一次 8 秒请求；可能扣费')
    ap.add_argument('--output', type=Path, default=ROOT / 'runtime' / 'live-smoke')
    args = ap.parse_args()
    try:
        _configure_secret()
        status, message = check_access()
        print(message)
        if not args.paid:
            print('未指定 --paid：没有发起 Scribe 或生成音乐调用。')
            return 0 if status == 200 else (2 if status == 0 else 0)
        if status == 401:
            print('因认证失败停止，未进行付费测试。')
            return 2
        args.output.mkdir(parents=True, exist_ok=True)
        run_paid(args.output)
        return 0
    except Exception as exc:
        # The API error body could echo a request or private data: never print it.
        if isinstance(exc, httpx.HTTPError):
            detail = 'HTTP transport error'
        elif isinstance(exc, subprocess.CalledProcessError):
            detail = 'FFmpeg exited with an error'
        else:
            detail = type(exc).__name__
        print(f'测试中止：{detail}。如需排查，请检查本地服务日志。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
