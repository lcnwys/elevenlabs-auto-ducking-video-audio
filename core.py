"""Speech grouping and local FFmpeg soundtrack ducking; reusable in Alibaba Cloud FC."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import json
import math
import shutil
import struct
import subprocess
import wave


@dataclass(frozen=True)
class Segment:
    start: float
    end: float

    def as_dict(self):
        return {"start": round(self.start, 3), "end": round(self.end, 3)}


def group_words(words: Iterable[dict], gap: float = 1.0, duration: Optional[float] = None) -> list[Segment]:
    """Ignore punctuation/non-speech and merge word intervals that have a small silence gap.

    Operates on intervals, not sentence punctuation. All speakers are duck triggers.
    """
    if not (0 <= gap <= 5):
        raise ValueError("gap must be between 0 and 5 seconds")
    events: list[Segment] = []
    for word in words:
        if word.get("type") != "word":
            continue
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (math.isfinite(start) and math.isfinite(end)) or end <= start:
            continue
        start = max(start, 0.0)
        if duration is not None:
            start, end = min(start, duration), min(end, duration)
        if end > start:
            events.append(Segment(start, end))
    return merge_segments(events, gap=gap)


def merge_segments(segments: Iterable[Segment], gap: float = 0.0) -> list[Segment]:
    items = sorted(segments, key=lambda x: (x.start, x.end))
    result: list[Segment] = []
    for current in items:
        if result and current.start - result[-1].end <= gap + 1e-8:
            last = result.pop()
            result.append(Segment(last.start, max(last.end, current.end)))
        else:
            result.append(current)
    return result


def padded_segments(segments: list[Segment], duration: float, pre: float = .15, post: float = .25) -> list[Segment]:
    if duration <= 0:
        raise ValueError("Video duration must be positive")
    padded = [Segment(max(0, s.start - pre), min(duration, s.end + post)) for s in segments]
    return merge_segments(padded)


def gain_at(t: float, segments: list[Segment], gain_low: float, attack: float = .15, release: float = .55) -> float:
    """Amplitude envelope; segments mark the low-gain plateau with attack before the start.

    Neighboring windows combine via minimum gain. This avoids unexpected volume pumping.
    """
    gain = 1.0
    for s in segments:
        if t < s.start - attack or t > s.end + release:
            continue
        if t < s.start and attack > 0:
            phase = (t - (s.start - attack)) / attack
            candidate = 1.0 - phase * (1.0 - gain_low)
        elif t <= s.end:
            candidate = gain_low
        elif release > 0:
            phase = (t - s.end) / release
            candidate = gain_low + phase * (1.0 - gain_low)
        else:
            candidate = 1.0
        gain = min(gain, candidate)
    return max(gain_low, min(1.0, gain))


def write_envelope(path: Path, duration: float, segments: list[Segment], reduction_db: float = 16,
                   attack: float = .15, release: float = .55, sample_rate: int = 1000) -> Path:
    """Small mono 1 kHz PCM16 gain-control wav. FFmpeg resamples to music rate."""
    if not (0 <= reduction_db <= 36):
        raise ValueError("reduction_db outside 0..36")
    if not (0 <= attack <= 2 and 0 <= release <= 3):
        raise ValueError("Invalid attack/release")
    low = 10 ** (-reduction_db / 20)
    samples = math.ceil(duration * sample_rate)
    # Precalculate intervals for O(sample_count + interval_count) performance.
    starts = sorted(segments, key=lambda s: s.start)
    ptr = 0
    active: list[Segment] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        chunk = bytearray()
        for i in range(samples):
            t = i / sample_rate
            while ptr < len(starts) and starts[ptr].start - attack <= t:
                active.append(starts[ptr])
                ptr += 1
            active = [s for s in active if t <= s.end + release]
            value = gain_at(t, active, low, attack, release)
            chunk += struct.pack("<h", max(0, min(32767, round(value * 32767))))
            if len(chunk) >= 131072:
                out.writeframesraw(chunk)
                chunk.clear()
        if chunk:
            out.writeframesraw(chunk)
    return path


def probe_media(path: Path) -> dict:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode:
        raise ValueError(f"ffprobe cannot parse media: {completed.stderr[-300:]}")
    parsed = json.loads(completed.stdout)
    duration = float(parsed.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Cannot determine media duration")
    streams = parsed.get("streams", [])
    return {"duration": duration, "has_video": any(s.get("codec_type") == "video" for s in streams),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def render_video(video: Path, music: Path, output: Path, segments: list[Segment],
                 reduction_db: float = 16, normal_music_db: float = -12,
                 pre: float = .15, post: float = .25,
                 attack: float = .15, release: float = .55) -> dict:
    """Mix original video audio + new music (ducked using speech timestamps)."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed")
    vinfo, minfo = probe_media(video), probe_media(music)
    if not vinfo["has_video"] or not minfo["has_audio"]:
        raise ValueError("Video must contain video stream and soundtrack must contain an audio stream")
    duration = vinfo["duration"]
    if duration > 600:
        raise ValueError("Video longer than 600 seconds is not supported in demo")
    if not (-30 <= normal_music_db <= 0):
        raise ValueError("normal_music_db outside -30..0")
    if not (0 <= pre <= 1 and 0 <= post <= 2):
        raise ValueError("Invalid pre/post values")
    # An audible music bed starts at normal_music_db; speaking reduction is relative to that bed.
    windows = padded_segments(segments, duration, pre=pre, post=post)
    env = output.with_suffix(".envelope.wav")
    write_envelope(env, duration, windows, reduction_db=reduction_db, attack=attack, release=release)
    base_gain = 10 ** (normal_music_db / 20)
    # Short looping soundtracks are padded with silence instead of repeated; avoids artificial musical jumps.
    filters = (
        f"[1:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad,atrim=duration={duration:.6f},volume={base_gain:.7f}[bed];"
        "[2:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[env];"
        "[bed][env]amultiply[ducked];"
    )
    if vinfo["has_audio"]:
        filters += (
            "[0:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[original];"
            "[original][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[outa]"
        )
    else:
        filters += "[ducked]alimiter=limit=0.95[outa]"
    command = ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(video), "-i", str(music), "-i", str(env),
               "-filter_complex", filters, "-map", "0:v:0", "-map", "[outa]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", "-t", f"{duration:.6f}", str(output)]
    try:
        output.unlink(missing_ok=True)
        proc = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        if proc.returncode != 0:
            # MOV/WebM may use video codecs that cannot be copied into MP4.
            # Prefer stream copy for speed and FC cost; encode H.264 only on incompatibility.
            fallback = command.copy()
            pos = fallback.index("copy")
            fallback[pos:pos + 1] = ["libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
            proc = subprocess.run(fallback, capture_output=True, text=True, timeout=900, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg failure: {proc.stderr[-1200:]}")
        return {"duration": round(duration, 3), "has_original_audio": vinfo["has_audio"],
                "segments": [s.as_dict() for s in windows], "rendered_file": str(output)}
    finally:
        env.unlink(missing_ok=True)
