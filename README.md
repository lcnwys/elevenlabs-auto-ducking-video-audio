# ElevenLabs Auto Ducking — Video Audio Mixer

**Let the music step back when your characters speak.**

English · [简体中文](README.zh-CN.md) · Originally ElevenLabs Auto Ducking Demo v0.2

Dialogue Duck tackles a familiar editing problem: a soundtrack that buries the dialogue. It connects ElevenLabs video scoring and Scribe speech timestamps to a local FFmpeg mix, lowering added music during speech and bringing it back during pauses.

## Where it fits

| Content | Workflow |
|---|---|
| Motion comics / animated panels | Duck added music beneath character dialogue |
| Explainers / tutorials | Reduce music masking under continuous narration |
| Narrative shorts / trailers | Produce a more intelligible mix for dialogue-heavy scenes |
| Soundtrack experiments | Compare levels and release timing on the same clip |

This is a focused ducking utility. For an editable multitrack timeline, explore the related SoundFlow Studio project.

## Current capabilities

- Included video, music, and speech-timestamp sample for local mixing without a key.
- Upload footage, import an existing track, or generate music with ElevenLabs Video-to-Music.
- Obtain word timestamps with Scribe, or submit manual speech intervals through the API.
- Adjust base music gain, speech attenuation, short-pause merging, pre-roll, hold, attack, and release.
- Render a previewable, downloadable MP4 with local FFmpeg.
- Reusable mixing core and local worker example for future job-based integrations.

> The application UI is currently primarily in Chinese; this README provides English setup and workflow instructions.

## Stack & requirements

| Layer | Implementation |
|---|---|
| UI | Vanilla HTML / CSS / JavaScript single page |
| Service | Python, FastAPI, Uvicorn, Pydantic |
| Online services | HTTPX → ElevenLabs Video-to-Music, Scribe v2 |
| Local media | FFmpeg / ffprobe, interval merging, volume envelopes |
| Storage | Repository `runtime/`; configurable with `DUCKING_DATA_DIR` |
| Recommended setup | Python 3.11 / 3.12, FFmpeg, desktop browser; no database |

## Quick start

Download or clone the repository and enter its root, containing `app.py` and `requirements.txt`. The existing folder is named `elevenlabs-auto-ducking-demo`.

### Install dependencies

Use Python **3.11 or 3.12** and a separate virtual environment for this project. This is a Python application: **Node.js, npm, and an external database are not required**. Use a recent Chrome, Edge, Firefox, or Safari; media decoding depends on the browser.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` directly and use that Python executable for subsequent commands.

Install FFmpeg, for example:

```bash
# macOS with Homebrew
brew install ffmpeg
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install ffmpeg
```

On Windows, install FFmpeg and add its `bin` directory to PATH. Open a new terminal and check:

```bash
ffmpeg -version
ffprobe -version
```

### Start locally

For the included sample without live AI:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

For video scoring or Scribe, configure the environment before starting:

```bash
export ELEVENLABS_API_KEY="<your-elevenlabs-api-key>"
# Optional alternative local data directory
# export DUCKING_DATA_DIR="/absolute/path/to/jobs"
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

In PowerShell, use `$env:ELEVENLABS_API_KEY="<your-elevenlabs-api-key>"`, followed by the same server command.

Open **http://127.0.0.1:8765**. API docs: **http://127.0.0.1:8765/api/docs**. **The application does not load `.env` automatically**; `.env.example` documents the variable names. On macOS, you may run `./启动_Mac.command` from a terminal with the variable set.

## Hear the difference without an API call

1. Load the included sample and listen to the source and music.
2. Set the normal music level and attenuation during speech.
3. Change pause merging and release timing to hear how they affect pacing.
4. Render with FFmpeg, preview, and download the MP4.

For your own footage: **upload video → import or generate music → obtain Scribe speech ranges → tune → mix locally → download MP4**.

## Understanding the controls

| Control | Audible effect |
|---|---|
| Normal music gain | Level when nobody is speaking |
| Attenuation | How far the music falls during speech; excessive reduction can sound unnatural |
| Pause merging | Keeps short gaps inside one speech region to avoid constant level changes |
| Pre-roll / hold | Protects the beginning and end of a line |
| Attack / release | How quickly the music falls and returns; tune against the dialogue |

## Data, costs & limits

Imports and rendering are local. Requesting music or transcription uploads the video file, including its audio and imagery, to ElevenLabs; music descriptions are also sent. The backend reads the key from its environment and sends it only in HTTPS authentication headers to ElevenLabs. `.env`, `runtime/`, and virtual environments are ignored by Git. There is no separate telemetry-upload code, but upstream zero retention is not guaranteed.

Live API calls may incur charges. Start with short footage. `scripts/live_smoke.py` defaults to an authentication check; **`--paid` explicitly enables paid requests for a short sample**. Read the script before using that option.

A source video is limited to **100 MB / 600 seconds**. Ducking affects newly added music; it **does not isolate or reduce music already mixed into the original soundtrack**. It does not provide denoising, speaker separation, translation, or voice cloning. Review detection against the audio. There is no login, multitenancy, automatic cleanup, or production queue.

## Development map

| Path | Role |
|---|---|
| `app.py` | Upload, scoring, recognition, timeline, and render API |
| `core.py` | Timestamp grouping, probing, envelopes, and mixing |
| `elevenlabs_client.py` | Official API client |
| `static/index.html` | Local interactive page |
| `fc_worker.py` / `fc_job.example.json` | Local worker and job format example |
| `tests/` | Core workflow and mocked-request checks |

Developer checks: `python -m pytest -q`. Local worker example: `python fc_worker.py fc_job.example.json`. Alibaba Cloud FC notes describe a possible migration; the current application does not create cloud functions or upload to OSS.

## References

- [ElevenLabs Video-to-Music](https://elevenlabs.io/docs/api-reference/music/video-to-music)
- [ElevenLabs Scribe](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)
- [FFmpeg documentation](https://ffmpeg.org/documentation.html)

## Local deployment & development

The commands above start a **single-user service on your own machine**. Leave the terminal running and press `Ctrl+C` to stop it. To restart, enter the same directory, activate the same environment, and run the start command again. If another project uses the port, stop it or choose a different `--port`.

A process manager can keep the same Uvicorn command running. Before offering this service to a team or the public, add authentication, user isolation, a job queue, usage limits, redacted logs, and file cleanup. These production deployment features are not implemented here.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Missing `uvicorn` or Python module | Activate the virtual environment; run `python -m pip install -r requirements.txt` from the project root |
| FFmpeg missing / media probe fails | Check `ffmpeg -version` and `ffprobe -version`; reopen the terminal after installation |
| API returns 401 / 403 | Check the local key, product permissions, and account status; never paste a full key into an issue |
| API returns 429 / generation times out | Check quota, concurrency, and network access; start with a short clip and inspect upstream job state before resubmitting |
| Preview does not play | Check browser codec support; download the result and try a local player |
| Environment changes do not take effect | Restart Uvicorn from the terminal where the variables are configured |

## Contributing

Reproduction steps, sanitized errors, and feature suggestions are welcome. A concrete case—music masking comic dialogue, subtitle drift after dubbing, or an unsuitable musical mood—is especially useful. Include OS, Python / FFmpeg versions, media format, and a minimal workflow. Confirm sharing rights before providing real media.

This repository does not include a `LICENSE` yet. Public source visibility alone does not grant reuse or redistribution rights; those will be defined when the maintainer selects a license. API terms, generated-content rights, and dependency licenses apply separately.

## ElevenLabs integration & pricing inquiries

Maintained by an independent developer, this project gives motion-comic teams, video creators, and builders a practical way to explore ElevenLabs.

Working on **motion-comic dubbing, short-drama localization, video soundtracks, sound effects, voice products, or batch API integration**? Get in touch to discuss product fit, workflow design, and integration. I can also offer **competitively priced ElevenLabs solutions**; availability, terms, and pricing depend on your requirements and an individual quotation.

**Email: [lcnwys@gmail.com](mailto:lcnwys@gmail.com)**

For a useful first conversation, include:

- Your content or product type and a short, sanitized description of the requirement.
- Estimated monthly audio/video minutes, target languages, team size, and API needs.
- Whether you are testing a pilot or preparing a launch.

Do not send API keys, passwords, or unauthorized customer media by email or in public issues. Use issues for product feedback and email for commercial inquiries.

> An independent community project, not an official ElevenLabs product. Inquiries and quotations do not imply official endorsement. ElevenLabs names and trademarks belong to their respective owners.
