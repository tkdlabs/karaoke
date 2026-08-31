# Karaoke

Web-based karaoke song manager and player. Downloads music videos, separates
audio stems, pre-generates pitch/vocal variants, renders synced lyrics
overlays, and exports videos with a configurable vocal mix.

Streaming API is available for clients such as ExoPlayer/MediaPlayer (configurable
vocal level, on-the-fly pitch shift, original or lyrics-overlay video stream).

**Features:**
- YouTube search/download via yt-dlp (**optional**), or manual local-file import
- Lyrics from lrclib.net (LRC), Korean romanization support, line-by-line timestamp editing
- Stem separation with Demucs (vocals / instrumental)
- 21 pitch×vocal variants per song (7 pitches × 3 vocal levels), pre-generated
- Synced lyrics + romanized overlay videos, rendered client-side
- Video export with configurable vocal mix percentage

## Requirements

- Python 3.10+
- Node.js 18+ (Next.js 16)
- `ffmpeg` / `ffprobe`
- **Optional:** `yt-dlp` binary for YouTube search/download
- **Stems require a CUDA GPU and `torch`/`demucs`** (pulls in heavy CUDA deps);
  everything else works without it

## Quick Start

```bash
# Backend (port 8001)
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py

# Frontend (port 3002, separate terminal)
npm install
npm run dev -- -p 3002
```

Or run both with `./start.sh` (expects `server/.venv` to exist).

## Enabling optional features

```bash
# YouTube search/download (yt-dlp)
pip install -r server/requirements-ytdlp.txt   # or install yt-dlp any other way

# Korean romanization for lyrics overlays
pip install korean_romanizer
```

## Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `PORT` | `8001` | Backend port |
| `DATA_DIR` | `../data` (relative to `server/`) | Where videos/stems/DB are stored |
| `DEMUCS_MODEL` | `htdemucs` | Demucs pretrained model (see license note below) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` | Backend URL used by the frontend |

## Deploy

For server deployment (systemd, backend-only mode), data dir relocation, ports,
and service user, see `deploy.py`:

```bash
python deploy.py --help
# or: ./deploy.sh --help
```

Both a full deploy (frontend + backend via generated `start.sh`/`stop.sh`) and a
serve-only systemd deploy (`--serve --host <server>`) are supported, locally or
over SSH — the script is self-contained (Python stdlib only).

## License & responsible use

This project is MIT-licensed (see `LICENSE`). Third-party dependencies and
pretrained weights carry their own terms — see `THIRD_PARTY_NOTICES.md`.

**Non-commercial stems:** the default Demucs `htdemucs` pretrained weights are
CC-BY-NC 4.0 (trained on research-only MUSDB18 data). Using stems separation
**commercially violates the weights license**. You can switch models with the
`DEMUCS_MODEL` env var (e.g. `htdemucs_ft`), but every Demucs-family checkpoint
is non-commercial. For commercial use, a permissively-licensed separation model
(e.g. Spleeter) is required. The active model is shown in the app UI and
reported by `GET /api/health` as `stems_model`.

**yt-dlp is optional**: search/download only work when the binary is installed.
Without it, use "Import video" to add local files.

**Media ownership:** you are responsible for the videos and lyrics you download
and process, and for clearing rights to them before distribution.

## API

```
GET  /api/health                        # {"status","ytdlp","stems_model"}
GET  /api/capabilities                  # runtime caps incl. ytdlp + stems_model
GET  /api/search?q=<query>              # YouTube search (409 without yt-dlp)
GET  /api/songs                         # list all songs
GET  /api/songs/{id}
POST /api/songs                         # add song from YouTube
POST /api/songs/import                  # import a local video file (no yt-dlp needed)
DEL  /api/songs/{id}

GET  /api/lyrics/search?q=<query>&duration=<sec>
PUT  /api/songs/{id}/lyrics
DEL  /api/songs/{id}/lyrics
PUT  /api/songs/{id}/lyrics/adjust     # anchor-based timestamp shift

POST /api/songs/{id}/stems              # Demucs separation (background)
DEL  /api/songs/{id}/stems
GET  /api/songs/{id}/audio/{stem}       # vocals|instrumental MP3

POST /api/songs/{id}/variants           # generate 21 pitch×vocal variants
DEL  /api/songs/{id}/variants
GET  /api/songs/{id}/variants/{pitch}/{vocal}

POST /api/songs/{id}/overlay            # render lyrics overlay videos
DEL  /api/songs/{id}/overlay

POST /api/songs/{id}/export             # export with vocal mix (background)
DEL  /api/songs/{id}/export

GET  /api/songs/{id}/video/{variant}    # original|overlay_lyrics|overlay_romanized
GET  /api/songs/{id}/thumbnail
POST /api/songs/{id}/thumbnail
```