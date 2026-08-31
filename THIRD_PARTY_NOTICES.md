# Third-Party Notices

This project combines components under different licenses. This file documents
attribution and license obligations. The project itself is MIT (see `LICENSE`);
several bundled runtime dependencies and pretrained weight files carry their own
terms, some of which are **non-commercial**. You are responsible for complying
with the terms that apply to how you use this software.

## Runtime dependencies

| Component | License | Notes |
|-----------|---------|-------|
| FastAPI / uvicorn / pydantic | MIT / BSD-3 / Apache-2.0 | Standard ASF/Encode deps; see `server/requirements.txt` for full list |
| demucs | MIT | Code is MIT |
| **htdemucs (and other pre-trained Demucs weights)** | **CC-BY-NC 4.0 (non-commercial)** | Trained on the MUSDB18 dataset (CC-BY-NC-SA 4.0). Swappable via the `DEMUCS_MODEL` env var, but **all** Demucs-family pretrained checkpoints are non-commercial |
| moviepy | MIT | Video overlay/export |
| lrcup / lrclib.net API | MIT (lrcup) | lrclib.net is a community service with its own rate limits and acceptable-use terms; do not bundle third-party lyrics in your distributions |
| korean_romanizer | MIT | Korean romanization |
| ffmpeg / ffprobe | GPL-2.0+ (build-dependent) | Invoked as external subprocesses; not statically linked. You must obtain an ffmpeg build whose license matches your use |
| yt-dlp | Unlicense / public domain | **Optional**; only installed via `server/requirements-ytdlp.txt` (see feature 39) |
| python-multipart | MIT | Multipart import uploads |

## Media & lyrics terms

- **Stems (vocals separation)** reproduce the original recording. The Demucs
  weights used are non-commercial; separately, you are responsible for the
  media you process and for clearing rights to it.
- **Lyrics** may be copyrighted. The app downloads them from lrclib.net; do not
  redistribute them without authorization.

## Stems model licensing detail

The active model is reported by `GET /api/health` as `stems_model` and shown in
the UI. To select a model, set `DEMUCS_MODEL` before starting the server
(default: `htdemucs`). If you need commercial use of stem separation, use a
permissively-licensed model (e.g. Spleeter's MIT-licensed pretrained models) —
see the project README "License & responsible use" section.