# Serve Mode — Lightweight Broadcast Backend

## Problem

The karaoke backend currently bundles two very different concerns:

1. **Admin**: sourcing songs (yt-dlp), stem separation (Demucs/ffmpeg), variant generation, lyrics editing, overlay rendering — all CPU/GPU-heavy, needs a powerful machine.
2. **Serving**: streaming pre-generated audio variants, videos, thumbnails, and song metadata to TV/phone clients — I/O bound, runs fine on low-spec hardware.

Running everything on the broadcast server is wasteful and adds unnecessary risk (a hung Demucs job could starve client streams).

## Goal

Add a `SERVE_MODE` flag to `server/main.py` that, when set, starts a read-only serving backend with no heavy dependencies and no mutation endpoints. The admin instance continues to run unchanged on the powerful machine.

---

## Endpoint Classification

### Serve endpoints (included in both modes)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/songs` | List song library |
| GET | `/api/songs/{id}` | Single song metadata |
| GET | `/api/songs/{id}/variants/{pitch}/{vocal}` | Stream pre-generated variant MP3 (primary player source) |
| GET | `/api/songs/{id}/audio/{stem}` | Stream vocals/instrumental stem (fallback) |
| GET | `/api/songs/{id}/video/{variant}` | Stream video (original, overlay_lyrics, overlay_romanized) |
| GET | `/api/songs/{id}/thumbnail` | Serve thumbnail JPEG |
| GET | `/api/songs/{id}/overlay/download` | Download overlay MP4 |
| GET | `/api/songs/{id}/export/download` | Download export MP4 |

### Admin endpoints (omitted in serve mode)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/search` | YouTube search (yt-dlp) |
| POST | `/api/songs` | Add song + trigger download |
| DELETE | `/api/songs/{id}` | Delete song + files |
| GET | `/api/lyrics/search` | lrclib.net search |
| PUT | `/api/songs/{id}/lyrics` | Set lyrics |
| PUT | `/api/songs/{id}/lyrics/adjust` | Adjust LRC timestamps |
| DELETE | `/api/songs/{id}/lyrics` | Remove lyrics |
| POST | `/api/songs/{id}/stems` | Start Demucs |
| DELETE | `/api/songs/{id}/stems` | Remove stems |
| POST | `/api/songs/{id}/variants` | Generate all 21 variants |
| DELETE | `/api/songs/{id}/variants` | Remove variants |
| POST | `/api/songs/{id}/overlay` | Render lyrics overlay |
| DELETE | `/api/songs/{id}/overlay` | Remove overlay |
| POST | `/api/songs/{id}/export` | Create export video |
| DELETE | `/api/songs/{id}/export` | Remove export |
| POST | `/api/songs/{id}/thumbnail` | Regenerate thumbnail |

---

## Implementation: SERVE_MODE env var

Single-file approach — no split into separate files. Minimal diff.

### Changes to `server/main.py`

```python
SERVE_MODE = os.environ.get("SERVE_MODE", "").lower() in ("1", "true", "yes")
```

**Conditional imports** — only at module level when NOT in serve mode:
```python
if not SERVE_MODE:
    import demucs
    import export as export_mod
    import overlay as overlay_mod
    import lrclib
    import ytdlp
```

**Startup event** — skip stuck-status recovery in serve mode (no background workers run):
```python
@app.on_event("startup")
def startup():
    db.init_db()
    # ... mkdir calls stay (harmless) ...
    if not SERVE_MODE:
        # reset stuck processing statuses
        ...
```

**Route registration** — wrap admin routes in a guard:
```python
if not SERVE_MODE:
    @app.get("/api/search", ...)
    def search_videos(...): ...

    @app.post("/api/songs", ...)
    def add_song(...): ...
    # ... all other admin routes
```

All serve routes remain unconditional.

### Heavy deps not imported in serve mode
- `demucs` (torch + Demucs model)
- `lrclib` / `lrcup`
- `ytdlp`
- `export` / `overlay` modules
- `karaoke_workflows` (only used by overlay/lyrics workers)
- `numpy` (only used by EQ analysis in `_compute_eq_filter`)

Startup time on serve node goes from ~10-30s (torch load) to near-instant.

---

## Data Synchronisation

The serve node needs a copy of `data/` from the admin machine. It is read-only from the serve node's perspective.

### What to sync

| Directory | Size profile | Notes |
|-----------|-------------|-------|
| `data/karaoke.db` | Small (~KB per song) | Primary metadata |
| `data/variants/{id}/` | ~50 MB per song | Primary audio for player |
| `data/videos/{id}.mp4` | ~100-300 MB per song | Video stream |
| `data/overlays/` | ~100-300 MB per song | Overlay videos |
| `data/thumbnails/` | Small (~100 KB each) | Thumbnails |
| `data/audio/` | ~20 MB per song | Stem fallback only — optional |

### Recommended: rsync over SSH

Run on the serve node via cron or systemd timer (every 5–15 min):

```bash
rsync -avz --delete \
  --exclude 'audio/' \
  admin-host:/path/to/data/ \
  /srv/karaoke/data/
```

Omit `audio/` unless stem fallback streaming is needed (all songs should have variants after admin processing is complete).

The DB is a single file — rsync it atomically. SQLite WAL mode (already enabled) means an in-progress write on admin won't corrupt a concurrent rsync read.

### Alternative: shared NFS mount

Mount `data/` from admin onto serve node. Zero sync lag. Requires reliable network; NFS latency adds ~1-2ms per file open. Acceptable for thumbnails/metadata; fine for large video/audio files since they stream sequentially.

---

## Deployment

### Admin machine (existing, unchanged)
```bash
# .env — no changes needed
BACKEND_PORT=8001
DATA_DIR=~/deployments/karaoke/data
```

### Serve node
```bash
# .env on serve node
BACKEND_PORT=8001
DATA_DIR=/srv/karaoke/data   # wherever synced data lives
SERVE_MODE=1
```

`start.sh` on serve node passes `SERVE_MODE` through the environment — no script changes needed since `main.py` reads it directly.

The serve node does NOT need:
- Python venv with `torch`, `demucs`, `lrcup`, `karaoke_workflows`
- `requirements.txt` dependencies for heavy deps
- GPU / large RAM

Minimal Python deps for serve mode: `fastapi`, `uvicorn`, `sqlite3` (stdlib).

---

## Future: dedicated serve `requirements.txt`

Optionally add `requirements-serve.txt`:
```
fastapi
uvicorn[standard]
```

And a matching `deploy-serve.sh` that installs only these. This makes the serve venv tiny and eliminates torch from the node entirely.

---

## Out of Scope

- **Auth / API keys**: the serve node will be equally open as today. If needed, add a reverse proxy with token auth in front.
- **Push-based sync**: the admin could trigger rsync on `variants_status=ready` transition — more complex, not needed for typical usage where songs are added infrequently.
- **Android TV / iPhone app**: this design defines the backend contract; actual client apps are separate work.
