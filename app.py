"""Local development demo. Start with `uvicorn app:app --host 127.0.0.1 --port 8765`."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4
import json
import os
import shutil

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core import Segment, group_words, merge_segments, probe_media, render_video
from elevenlabs_client import create_music, transcribe

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DUCKING_DATA_DIR", str(ROOT / "runtime"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 100 * 1024 * 1024
ALLOWED_VIDEO = {".mp4", ".mov", ".webm", ".mkv"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
app = FastAPI(title="ElevenLabs Auto Ducking Demo", docs_url="/api/docs", redoc_url=None)


class MusicOptions(BaseModel):
    description: str = Field(default="", max_length=4100)
    reference_audio: bool = False


class TimelineOptions(BaseModel):
    gap: float = Field(default=1.0, ge=0, le=5)


class MixOptions(BaseModel):
    gap: float = Field(default=1.0, ge=0, le=5)
    reduction_db: float = Field(default=16, ge=0, le=36)
    normal_music_db: float = Field(default=-12, ge=-30, le=0)
    pre: float = Field(default=.15, ge=0, le=1)
    post: float = Field(default=.25, ge=0, le=2)
    attack: float = Field(default=.15, ge=0, le=2)
    release: float = Field(default=.55, ge=0, le=3)
    manual_segments: Optional[list[Segment]] = None


def job_dir(job: str) -> Path:
    if len(job) != 32 or any(c not in "0123456789abcdef" for c in job):
        raise HTTPException(404, "Unknown job")
    folder = DATA / job
    if not folder.is_dir():
        raise HTTPException(404, "Job not found")
    return folder


def details(job: str, folder: Path) -> dict:
    meta = json.loads((folder / "meta.json").read_text())
    return {"job_id": job, **meta, "has_music": (folder / meta.get("music_name", "music.mp3")).exists(),
            "has_transcript": (folder / "words.json").exists(),
            "has_rendered": (folder / "output.mp4").exists()}


def store_upload(upload: UploadFile, target: Path) -> None:
    written = 0
    try:
        with target.open("wb") as f:
            while buf := upload.file.read(1024 * 1024):
                written += len(buf)
                if written > MAX_UPLOAD:
                    raise HTTPException(413, "Demo upload limit: 100 MB")
                f.write(buf)
        if written == 0:
            raise HTTPException(400, "Empty upload")
    except Exception:
        target.unlink(missing_ok=True)
        raise


def video_file(folder: Path) -> Path:
    meta = json.loads((folder / "meta.json").read_text())
    return folder / meta["video_name"]


def require_music(folder: Path) -> Path:
    # files with original extension are renamed to music.mp3 only when actually MP3;
    # when user uploads non-MP3, preserve extension in metadata.
    meta = json.loads((folder / "meta.json").read_text())
    music = folder / meta.get("music_name", "music.mp3")
    if not music.exists():
        raise HTTPException(400, "Please generate or upload music first")
    return music


def load_segments(folder: Path, duration: float, gap: float, manual: Optional[list[Segment]] = None) -> list[Segment]:
    if manual is not None:
        if len(manual) > 1000:
            raise HTTPException(400, "Too many speech segments")
        for s in manual:
            if not (0 <= s.start < s.end <= duration + 0.01):
                raise HTTPException(400, "Invalid manual segment range")
        return merge_segments([Segment(s.start, min(s.end, duration)) for s in manual])
    words = folder / "words.json"
    if words.is_file():
        data = json.loads(words.read_text())
        return group_words(data.get("words", []), gap=gap, duration=duration)
    return []


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {"ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
            "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
            "mode": "local-demo"}


@app.post("/api/video")
def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_VIDEO:
        raise HTTPException(400, "Expected MP4, MOV, WebM or MKV")
    job = uuid4().hex
    folder = DATA / job
    folder.mkdir(parents=True)
    filename = "video" + ext
    target = folder / filename
    try:
        store_upload(file, target)
        info = probe_media(target)
        if not info["has_video"] or info["duration"] > 600:
            raise HTTPException(400, "Video stream is required and duration cannot exceed 600s")
        (folder / "meta.json").write_text(json.dumps({"video_name": filename, **info}, ensure_ascii=False))
        return details(job, folder)
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/sample")
def sample():
    job = uuid4().hex
    folder = DATA / job
    folder.mkdir(parents=True)
    shutil.copy2(ROOT / "samples" / "sample_video.mp4", folder / "video.mp4")
    shutil.copy2(ROOT / "samples" / "sample_music.mp3", folder / "music.mp3")
    shutil.copy2(ROOT / "samples" / "sample_words.json", folder / "words.json")
    info = probe_media(folder / "video.mp4")
    (folder / "meta.json").write_text(json.dumps({"video_name": "video.mp4", "music_name": "music.mp3",
                                                   "sample": True, **info}, ensure_ascii=False))
    return details(job, folder)


@app.post("/api/music/{job}")
def music_generate(job: str, opt: MusicOptions):
    folder = job_dir(job)
    try:
        output = folder / "music.mp3"
        pending = folder / "music.pending.mp3"
        try:
            # Keep existing music until a complete, valid paid API result is received.
            create_music(video_file(folder), pending, description=opt.description,
                         reference_audio=opt.reference_audio)
            info = probe_media(pending)
            if not info["has_audio"]:
                raise ValueError("Generated music has no audio stream")
            pending.replace(output)
        finally:
            pending.unlink(missing_ok=True)
        meta = json.loads((folder / "meta.json").read_text())
        meta["music_name"] = "music.mp3"
        (folder / "meta.json").write_text(json.dumps(meta))
        return {"ok": True, "music_seconds": round(info["duration"], 2), "source": "elevenlabs"}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/music-upload/{job}")
def music_upload(job: str, file: UploadFile = File(...)):
    folder = job_dir(job)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_AUDIO:
        raise HTTPException(400, "Expected MP3/WAV/M4A/AAC/FLAC/OGG")
    target = folder / ("music" + ext)
    try:
        store_upload(file, target)
        info = probe_media(target)
        if not info["has_audio"]:
            raise ValueError("No audio stream")
        meta = json.loads((folder / "meta.json").read_text())
        previous = folder / meta.get("music_name", "music.mp3")
        if previous != target:
            previous.unlink(missing_ok=True)
        meta["music_name"] = target.name
        (folder / "meta.json").write_text(json.dumps(meta))
        return {"ok": True, "music_seconds": round(info["duration"], 2), "source": "upload"}
    except Exception as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/transcribe/{job}")
def speech_recognition(job: str):
    folder = job_dir(job)
    meta = json.loads((folder / "meta.json").read_text())
    if not meta["has_audio"]:
        raise HTTPException(400, "Video has no original audio: use manual segments or music-only mode")
    try:
        payload = transcribe(video_file(folder))
        (folder / "words.json").write_text(json.dumps(payload, ensure_ascii=False))
        return {"ok": True, "text": payload.get("text", ""), "word_count": len(payload.get("words", []))}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/timeline/{job}")
def timeline(job: str, gap: float = 1.0):
    folder = job_dir(job)
    meta = json.loads((folder / "meta.json").read_text())
    try:
        windows = load_segments(folder, meta["duration"], gap)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = json.loads((folder / "words.json").read_text()) if (folder / "words.json").exists() else {}
    return {"segments": [s.as_dict() for s in windows], "text": data.get("text", ""),
            "words": data.get("words", []), "duration": meta["duration"]}


@app.post("/api/render/{job}")
def mix(job: str, opt: MixOptions):
    folder = job_dir(job)
    try:
        meta = json.loads((folder / "meta.json").read_text())
        ranges = load_segments(folder, meta["duration"], opt.gap, opt.manual_segments)
        result = render_video(video_file(folder), require_music(folder), folder / "output.mp4", ranges,
                              reduction_db=opt.reduction_db, normal_music_db=opt.normal_music_db,
                              pre=opt.pre, post=opt.post, attack=opt.attack, release=opt.release)
        result["speech_segments"] = [s.as_dict() for s in ranges]
        return result
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/file/{job}/{kind}")
def read_file(job: str, kind: str):
    folder = job_dir(job)
    if kind == "video":
        path = video_file(folder)
    elif kind == "music":
        path = require_music(folder)
    elif kind == "result":
        path = folder / "output.mp4"
    else:
        raise HTTPException(404, "Unknown file type")
    if not path.exists():
        raise HTTPException(404, "File not ready")
    return FileResponse(path, filename=path.name if kind == "result" else None)
