# frontends/karaoke — Agent Guide

Web-based karaoke song manager and player. Downloads music videos from YouTube, separates audio stems with Demucs, pre-generates 21 pitch/vocal variants, renders synced lyrics overlays, and exports videos with configurable vocal mix.

## Process

- Commit after working on feature / bug / design.
- Directories:
  - bugs/ will contain open and fixed issues in .md format
  - features/ will contain feature requests in .md format
  - designs/ will contain engineering designs in .md format
- Try to work on one item at the time.
- If item is large in scope, feel free to break it down to more bugs/features/designs.
- Naming conventions:
  - Open bugs/, features/ files should be of nn_{bug|feature}_description.md format
  - Resolved bugs/, features/ files should be of fixed_nn_{bug|feature}_description.md format
  - Designs can be in free form format.
- When you finish working on bug or feature, remember to rename if to fixed_ format on commit.


## Stack

- **Frontend**: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS 4, port 3002
- **Backend**: FastAPI + SQLite (WAL mode) + uvicorn, port 8001
- **System deps**: ffmpeg/ffprobe, demucs
- **External**: yt-dlp (YouTube), lrclib.net (lyrics), karaoke_workflows (local package at `workflows/karaoke`)

## Quick Start

```bash
./start.sh          # starts both frontend (3002) and backend (8001)
# or separately:
cd server && source .venv/bin/activate && python main.py
npm install && npm run dev -- -p 3002
```

## Directory Layout

```
frontends/karaoke/
├── app/
│   ├── page.tsx              # Main page — orchestrates all components, polls /api/songs every 3s
│   ├── layout.tsx
│   └── globals.css
├── components/
│   ├── SongLibrary.tsx       # Grid of songs with collapsible processing controls (stems/variants/overlay/export)
│   ├── SongPlayer.tsx        # Audio+video player — dual-buffer crossfade, 21 variants (7 pitch × 3 vocal)
│   ├── LyricsEditor.tsx      # Adjust LRC timestamps line-by-line with anchor-based offset
│   ├── LyricsSearchModal.tsx # Search & preview lrclib.net results
│   └── SearchResults.tsx     # YouTube search result cards
├── lib/
│   └── api.ts                # All fetch calls to backend (API_BASE = http://localhost:8001)
├── types/
│   └── karaoke.ts            # Shared TypeScript interfaces: Song, SearchResult, LyricsSearchResult
├── server/
│   ├── main.py               # FastAPI app — all endpoints + background thread workers (1,196 lines)
│   ├── db.py                 # SQLite abstraction — songs table with auto-migration (139 lines)
│   ├── models.py             # Pydantic request/response models
│   ├── demucs.py             # Demucs stem separation wrapper (htdemucs model)
│   ├── overlay.py            # Bridges to karaoke_workflows.video.create_lyrics_overlay_video
│   ├── export.py             # Video export with mixed audio
│   ├── lrclib.py             # lrclib.net lyrics search via lrcup
│   ├── ytdlp.py              # YouTube search + video/thumbnail download via yt-dlp
│   └── requirements.txt
└── data/                     # git-ignored, auto-created
    ├── karaoke.db
    ├── videos/{id}.mp4
    ├── audio/{id}_vocals.mp3 / {id}_instrumental.mp3
    ├── variants/{id}/p{pitch}_v{vocal}.mp3   # e.g. p-3_v0.mp3
    ├── overlays/{id}_overlay_lyrics.mp4 / {id}_overlay_romanized.mp4
    ├── exports/{id}_export_v{vocal_pct}.mp4
    └── thumbnails/{id}.jpg
```

## Data Model

**Song** (29 DB columns, defined in `server/models.py` and `types/karaoke.ts`):

| Group | Fields |
|-------|--------|
| Identity | `id`, `title`, `artist`, `duration`, `source_url` |
| Files | `video_filename`, `thumbnail_url` |
| Status | `status` (pending\|downloading\|ready\|error), `error_message` |
| Lyrics | `lyrics_synced` (LRC format), `lyrics_plain`, `lyrics_source` |
| Stems | `vocals_filename`, `instrumental_filename`, `stems_status`, `stems_error` |
| Variants | `variants_status`, `variants_error`, `variants_progress` |
| Overlay | `overlay_lyrics_filename`, `overlay_romanized_filename`, `overlay_status`, `overlay_error`, `overlay_progress` |
| Export | `export_filename`, `export_status`, `export_error`, `export_vocal_level`, `export_progress` |
| Timestamps | `created_at`, `updated_at` |

## API Endpoints (server/main.py)

```
GET  /api/health
GET  /api/search?q=<query>                          # YouTube search via yt-dlp
GET  /api/songs                                     # list all songs
GET  /api/songs/{id}                                # single song
POST /api/songs                                     # add song (triggers download background thread)
DEL  /api/songs/{id}                                # delete song + all files

GET  /api/lyrics/search?q=<query>&duration=<sec>    # search lrclib.net
PUT  /api/songs/{id}/lyrics                         # set synced/plain lyrics
DEL  /api/songs/{id}/lyrics
PUT  /api/songs/{id}/lyrics/adjust                  # anchor-based timestamp shift

POST /api/songs/{id}/stems                          # start Demucs (background); auto-triggers variants after
DEL  /api/songs/{id}/stems
GET  /api/songs/{id}/audio/{stem}                   # serve vocals|instrumental MP3

POST /api/songs/{id}/variants                       # generate all 21 variants (background)
DEL  /api/songs/{id}/variants
GET  /api/songs/{id}/variants/{pitch}/{vocal}       # serve variant MP3 (supports HTTP Range)

POST /api/songs/{id}/overlay                        # render lyrics overlay (background)
DEL  /api/songs/{id}/overlay
GET  /api/songs/{id}/overlay/download?variant=lyrics|romanized

POST /api/songs/{id}/export                         # export with mixed audio (background)
DEL  /api/songs/{id}/export
GET  /api/songs/{id}/export/download

GET  /api/songs/{id}/video/{variant}                # serve video: original|overlay_lyrics|overlay_romanized
GET  /api/songs/{id}/thumbnail
POST /api/songs/{id}/thumbnail                      # regenerate from video
```

## Background Workers (all in server/main.py)

All long-running tasks run as `threading.Thread(daemon=True)`:

| Worker | Trigger | What it does |
|--------|---------|--------------|
| `_download_worker` | POST /songs | yt-dlp download + thumbnail extraction |
| `_stems_worker` | POST /stems | Demucs separation → auto-calls `_variants_worker` |
| `_variants_worker` | POST /variants or after stems | Generates 21 pitch×vocal MP3 variants via ffmpeg |
| `_overlay_worker` | POST /overlay | Renders lyrics+romanized overlay videos; copies if no CJK detected |
| `_export_worker` | POST /export | Mixes vocal+instrumental at specified level, remuxes with video |

Progress throttled to DB writes every 2s. On restart, stuck "processing" statuses reset to "error".

## Audio Processing Pipeline

**Stem separation** (`demucs.py`):
1. Extract WAV from video (ffmpeg)
2. Demucs htdemucs → vocals, bass, drums, other stems
3. Mix bass+drums+other → `instrumental.mp3` via ffmpeg amix

**Variant generation** (pitch × vocal, `main.py` ~line 1002):
- Pitch shift: `aformat → asetrate(rate×2^(semitones/12)) → aresample(back) → atempo(1/factor)`
- Vocal mix: `vocals × vocal_level + instrumental × (1 - vocal_level)`
- Optional EQ matching: spectral analysis of original vs instrumental; applies ±12 dB correction per band (vocal range strength 0.10–0.12, bass/treble 0.30–0.50)
- Optional exciter: `aexciter(freq=4000, drive=4, blend=2, amount=2)` — restores brightness above 4 kHz

**Variant naming**: `p{semitones}_v{vocal_pct}.mp3` where pitch ∈ {-3,-2,-1,0,1,2,3} and vocal ∈ {0,25,100}

## SongPlayer.tsx — Key Concepts

- **Dual audio buffers** (`audioA` / `audioB`): active buffer plays, inactive loads next variant
- **Crossfade**: 1s / 20-step volume ramp when switching pitch or vocal level during playback
- **Lookahead**: loads variant 3s ahead of playback position to avoid gaps
- **Video sync**: tolerates ±0.1s drift before correcting; pauses video if audio not ready
- **Variant source priority**: pre-generated file in `data/variants/` → streaming from `/api/songs/{id}/audio/{stem}` as fallback

## Lyrics

- Format: LRC (`[MM:SS.CC] line text`)
- Source: lrclib.net search (via `lrclib.py` + `lrcup` library)
- Manual adjustment: anchor-based offset — pick a reference line + timestamp, all lines from that point shift
- Korean (Hangul) detected via Unicode range; if present, overlay renders two variants (lyrics + romanized)

## Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add/modify API endpoint | `server/main.py`, `lib/api.ts`, `types/karaoke.ts` |
| Change UI layout/controls | `components/SongLibrary.tsx` |
| Modify player behavior | `components/SongPlayer.tsx` |
| Change audio processing | `server/main.py` (_variants_worker, EQ/exciter logic) |
| Change stem separation | `server/demucs.py` |
| Change lyrics overlay | `server/overlay.py`, `workflows/karaoke/` |
| DB schema changes | `server/db.py` (add column + migration in `_migrate_db`) |
| Change data file paths | `server/main.py` (DATA_DIR constants near top) |

## Environment Variables

| Var | Default | Used in |
|-----|---------|---------|
| `DATA_DIR` | `../data` (relative to `server/`) | `server/main.py` |
| `PORT` | `8001` | `server/main.py` / `start.sh` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` | `lib/api.ts` |

## External Dependency: karaoke_workflows

The backend depends on `workflows/karaoke` (installed as editable package `-e ../../../workflows/karaoke`). This package provides `karaoke_workflows.video.create_lyrics_overlay_video`. If overlay rendering breaks, check that package first.
