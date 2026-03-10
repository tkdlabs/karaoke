"""FastAPI backend for karaoke song management."""

import os
import re
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import db
from models import (
  AddSongRequest,
  AdjustLyricsRequest,
  ExportRequest,
  LyricsSearchResult,
  OverlayRequest,
  SearchResult,
  SetLyricsRequest,
  Song,
  VariantsRequest,
)

SERVE_MODE = os.environ.get("SERVE_MODE", "").lower() in ("1", "true", "yes")

if not SERVE_MODE:
  import demucs
  import export as export_mod
  import lrclib
  import overlay as overlay_mod
  import ytdlp

app = FastAPI(title="Karaoke API", version="0.1.0")

# Routes registered here are only included in `app` in full mode (see bottom of file).
write_router = APIRouter()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent.parent / "data")))
VIDEOS_DIR = DATA_DIR / "videos"
AUDIO_DIR = DATA_DIR / "audio"
EXPORTS_DIR = DATA_DIR / "exports"
OVERLAYS_DIR = DATA_DIR / "overlays"
VARIANTS_DIR = DATA_DIR / "variants"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

# All supported pitch/vocal combinations for pre-generated audio variants
VARIANT_PITCHES = [-3, -2, -1, 0, 1, 2, 3]
VARIANT_VOCALS = [0, 25, 100]  # percent


@app.on_event("startup")
def startup():
  db.init_db()
  VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
  AUDIO_DIR.mkdir(parents=True, exist_ok=True)
  EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
  OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
  VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
  THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

  if SERVE_MODE:
    print("Running in SERVE_MODE — admin endpoints disabled")
    return

  # Reset any stuck "processing" statuses from a previous interrupted run
  for song in db.list_songs():
    updates = {}
    if song.get("status") == "downloading":
      updates["status"] = "error"
      updates["error_message"] = "Interrupted by server restart"
    if song.get("stems_status") == "processing":
      updates["stems_status"] = "error"
      updates["stems_error"] = "Interrupted by server restart"
    if song.get("overlay_status") == "processing":
      updates["overlay_status"] = "error"
      updates["overlay_error"] = "Interrupted by server restart"
    if song.get("export_status") == "processing":
      updates["export_status"] = "error"
      updates["export_error"] = "Interrupted by server restart"
    if song.get("variants_status") == "processing":
      updates["variants_status"] = "error"
      updates["variants_error"] = "Interrupted by server restart"
    if updates:
      db.update_song(song["id"], **updates)
      print(f"Reset stuck processing for {song['id']}: {list(updates.keys())}")


# ── Always-on routes ──────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
  return {"status": "ok"}


@app.get("/api/songs", response_model=list[Song])
def list_songs():
  """List all songs in the library."""
  return db.list_songs()


@app.get("/api/songs/{song_id}", response_model=Song)
def get_song(song_id: str):
  """Get a single song by ID."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  return song


@app.get("/api/songs/{song_id}/export/download")
def download_export(song_id: str):
  """Download the exported video file."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("export_status") != "ready":
    raise HTTPException(status_code=400, detail="Export not ready")

  export_path = EXPORTS_DIR / song["export_filename"]
  if not export_path.exists():
    raise HTTPException(status_code=404, detail="Export file not found")

  safe_title = "".join(
    c for c in (song.get("title") or "export") if c.isalnum() or c in " -_"
  ).strip()[:80]
  vocal_pct = int(round((song.get("export_vocal_level") or 0) * 100))
  download_name = f"{safe_title} (vocals {vocal_pct}%).mp4"

  return FileResponse(
    path=str(export_path),
    media_type="video/mp4",
    filename=download_name,
  )


@app.get("/api/songs/{song_id}/overlay/download")
def download_overlay(song_id: str, variant: str = "lyrics"):
  """Download the rendered overlay video (lyrics or romanized)."""
  if variant not in ("lyrics", "romanized"):
    raise HTTPException(status_code=400, detail="Variant must be 'lyrics' or 'romanized'")
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("overlay_status") != "ready":
    raise HTTPException(status_code=400, detail="Overlay not ready")

  filename_key = f"overlay_{variant}_filename"
  filename = song.get(filename_key) or song.get("overlay_filename")
  if not filename:
    raise HTTPException(status_code=404, detail="Overlay file not found")
  overlay_path = OVERLAYS_DIR / filename
  if not overlay_path.exists():
    raise HTTPException(status_code=404, detail="Overlay file not found")

  safe_title = "".join(
    c for c in (song.get("title") or "overlay") if c.isalnum() or c in " -_"
  ).strip()[:80]
  download_name = f"{safe_title} (lyrics {variant}).mp4"

  return FileResponse(
    path=str(overlay_path),
    media_type="video/mp4",
    filename=download_name,
  )


@app.get("/api/songs/{song_id}/variants/{pitch}/{vocal}")
def serve_variant(song_id: str, pitch: int, vocal: int):
  """Serve a pre-generated audio variant. Supports HTTP Range requests for seeking."""
  if pitch not in VARIANT_PITCHES:
    raise HTTPException(status_code=400, detail=f"Pitch must be one of {VARIANT_PITCHES}")
  if vocal not in VARIANT_VOCALS:
    raise HTTPException(status_code=400, detail=f"Vocal must be one of {VARIANT_VOCALS}")

  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("variants_status") != "ready":
    raise HTTPException(status_code=400, detail="Variants not ready")

  path = VARIANTS_DIR / song_id / f"p{pitch}_v{vocal}.mp3"
  if not path.exists():
    raise HTTPException(status_code=404, detail="Variant file not found")

  return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/songs/{song_id}/audio/{stem}")
def serve_audio_stem(song_id: str, stem: str):
  """Serve an individual audio stem (vocals or instrumental)."""
  if stem not in ("vocals", "instrumental"):
    raise HTTPException(status_code=400, detail="Stem must be 'vocals' or 'instrumental'")
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("stems_status") != "ready":
    raise HTTPException(status_code=400, detail="Stems must be separated first")

  filename = song[f"{stem}_filename"]
  if not filename:
    raise HTTPException(status_code=404, detail=f"{stem} file not found")
  path = AUDIO_DIR / filename
  if not path.exists():
    raise HTTPException(status_code=404, detail=f"{stem} file not found")

  return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/songs/{song_id}/video/{variant}")
def serve_video(song_id: str, variant: str):
  """Serve a video file (original, overlay_lyrics, or overlay_romanized), without audio."""
  valid = ("original", "overlay", "overlay_lyrics", "overlay_romanized")
  if variant not in valid:
    raise HTTPException(status_code=400, detail=f"Variant must be one of {valid}")
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  if variant in ("overlay", "overlay_lyrics", "overlay_romanized"):
    if song.get("overlay_status") != "ready":
      raise HTTPException(status_code=400, detail="Overlay not ready")
    # Resolve filename: prefer new split filenames, fall back to legacy single file
    if variant == "overlay_romanized":
      filename = song.get("overlay_romanized_filename") or song.get("overlay_filename")
    else:
      # "overlay" and "overlay_lyrics" both resolve to lyrics-only
      filename = song.get("overlay_lyrics_filename") or song.get("overlay_filename")
    if not filename:
      raise HTTPException(status_code=404, detail="Overlay file not found")
    path = OVERLAYS_DIR / filename
  else:
    if song["status"] != "ready":
      raise HTTPException(status_code=400, detail="Video not ready")
    path = VIDEOS_DIR / song["video_filename"]

  if not path.exists():
    raise HTTPException(status_code=404, detail="Video file not found")

  return FileResponse(path, media_type="video/mp4")


@app.get("/api/songs/{song_id}/thumbnail")
def serve_thumbnail(song_id: str):
  """Serve the generated thumbnail for a song."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  thumb_path = THUMBNAILS_DIR / f"{song_id}.jpg"
  if not thumb_path.exists():
    raise HTTPException(status_code=404, detail="Thumbnail not found")

  return FileResponse(thumb_path, media_type="image/jpeg")


# ── Full-mode-only routes (write_router) ──────────────────────────────────────


@write_router.get("/api/search", response_model=list[SearchResult])
def search_videos(q: str = Query(..., min_length=1)):
  """Search YouTube for videos via yt-dlp."""
  try:
    return ytdlp.search(q)
  except Exception as e:
    raise HTTPException(status_code=502, detail=str(e))


@write_router.post("/api/songs", response_model=Song, status_code=201)
def add_song(req: AddSongRequest):
  """Add a song to the library and start downloading."""
  song_id = uuid.uuid4().hex[:12]
  video_filename = f"{song_id}.mp4"

  song = db.insert_song(
    {
      "id": song_id,
      "title": req.title,
      "artist": req.artist,
      "duration": req.duration,
      "source_url": req.url,
      "video_filename": video_filename,
      "thumbnail_url": req.thumbnail_url,
      "status": "downloading",
    }
  )

  thread = threading.Thread(
    target=_download_worker,
    args=(song_id, req.url, VIDEOS_DIR / video_filename),
    daemon=True,
  )
  thread.start()

  return song


@write_router.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
  """Delete a song and its files."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  if song.get("video_filename"):
    video_path = VIDEOS_DIR / song["video_filename"]
    if video_path.exists():
      video_path.unlink()

  for key in ("vocals_filename", "instrumental_filename"):
    if song.get(key):
      audio_path = AUDIO_DIR / song[key]
      if audio_path.exists():
        audio_path.unlink()

  if song.get("export_filename"):
    export_path = EXPORTS_DIR / song["export_filename"]
    if export_path.exists():
      export_path.unlink()

  if song.get("overlay_filename"):
    overlay_path = OVERLAYS_DIR / song["overlay_filename"]
    if overlay_path.exists():
      overlay_path.unlink()

  variants_dir = VARIANTS_DIR / song_id
  if variants_dir.exists():
    shutil.rmtree(variants_dir)

  thumb_path = THUMBNAILS_DIR / f"{song_id}.jpg"
  if thumb_path.exists():
    thumb_path.unlink()

  db.delete_song(song_id)
  return {"status": "deleted"}


@write_router.get("/api/lyrics/search", response_model=list[LyricsSearchResult])
def search_lyrics(q: str = Query(..., min_length=1), duration: float | None = None):
  """Search lrclib.net for lyrics."""
  try:
    return lrclib.search(q, duration=duration)
  except Exception as e:
    raise HTTPException(status_code=502, detail=str(e))


@write_router.put("/api/songs/{song_id}/lyrics", response_model=Song)
def set_song_lyrics(song_id: str, req: SetLyricsRequest):
  """Store lyrics for a song."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  updated = db.update_song(
    song_id,
    lyrics_synced=req.synced_lyrics,
    lyrics_plain=req.plain_lyrics,
    lyrics_source=req.source,
  )
  return updated


@write_router.put("/api/songs/{song_id}/lyrics/adjust", response_model=Song)
def adjust_song_lyrics(song_id: str, req: AdjustLyricsRequest):
  """Adjust synced lyrics timestamps so the anchor line matches the given time.

  All other timestamps are shifted by the same offset (clamped to >= 0).
  """
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if not song.get("lyrics_synced"):
    raise HTTPException(status_code=400, detail="Song has no synced lyrics")

  lrc = song["lyrics_synced"]
  timestamp_re = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2})\]")

  # Collect all timestamped lines to find the anchor
  timestamped_lines: list[float] = []
  for line in lrc.splitlines():
    m = timestamp_re.match(line)
    if m:
      t = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100
      timestamped_lines.append(t)

  if not timestamped_lines:
    raise HTTPException(status_code=400, detail="No timestamped lyric lines found")
  if req.anchor_line_index < 0 or req.anchor_line_index >= len(timestamped_lines):
    raise HTTPException(status_code=400, detail="anchor_line_index out of range")

  old_time = timestamped_lines[req.anchor_line_index]
  offset = req.anchor_time - old_time

  # Only shift the anchor line and everything after it
  line_counter = 0

  def shift_timestamp(m: re.Match) -> str:
    nonlocal line_counter
    idx = line_counter
    line_counter += 1
    mins, secs, centis = int(m.group(1)), int(m.group(2)), int(m.group(3))
    total = mins * 60 + secs + centis / 100
    if idx >= req.anchor_line_index:
      total += offset
    total = max(0, total)
    new_mins = int(total // 60)
    new_secs = total % 60
    whole_secs = int(new_secs)
    centisecs = int(round((new_secs - whole_secs) * 100))
    return f"[{new_mins:02d}:{whole_secs:02d}.{centisecs:02d}]"

  adjusted = timestamp_re.sub(shift_timestamp, lrc)

  updated = db.update_song(song_id, lyrics_synced=adjusted)
  return updated


@write_router.delete("/api/songs/{song_id}/lyrics", response_model=Song)
def delete_song_lyrics(song_id: str):
  """Remove lyrics from a song."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  updated = db.update_song(
    song_id,
    lyrics_synced=None,
    lyrics_plain=None,
    lyrics_source=None,
  )
  return updated


@write_router.post("/api/songs/{song_id}/stems", response_model=Song)
def start_stems(song_id: str, req: VariantsRequest = VariantsRequest()):
  """Run Demucs stem separation in the background."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song["status"] != "ready":
    raise HTTPException(status_code=400, detail="Video must be downloaded first")
  if song.get("stems_status") == "processing":
    raise HTTPException(status_code=409, detail="Stem separation already in progress")

  vocals_filename = f"{song_id}_vocals.mp3"
  instrumental_filename = f"{song_id}_instrumental.mp3"

  updated = db.update_song(
    song_id,
    vocals_filename=vocals_filename,
    instrumental_filename=instrumental_filename,
    stems_status="processing",
    stems_error=None,
  )

  video_path = VIDEOS_DIR / song["video_filename"]
  thread = threading.Thread(
    target=_stems_worker,
    args=(
      song_id,
      video_path,
      AUDIO_DIR / vocals_filename,
      AUDIO_DIR / instrumental_filename,
      req.eq_match,
      req.exciter,
    ),
    daemon=True,
  )
  thread.start()

  return updated


@write_router.delete("/api/songs/{song_id}/stems", response_model=Song)
def delete_stems(song_id: str):
  """Remove stem audio files for a song."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  for key in ("vocals_filename", "instrumental_filename"):
    if song.get(key):
      audio_path = AUDIO_DIR / song[key]
      if audio_path.exists():
        audio_path.unlink()

  updated = db.update_song(
    song_id,
    vocals_filename=None,
    instrumental_filename=None,
    stems_status=None,
    stems_error=None,
  )
  return updated


@write_router.post("/api/songs/{song_id}/variants", response_model=Song)
def start_variants(song_id: str, req: VariantsRequest = VariantsRequest()):
  """Pre-generate all audio variants (pitch × vocal level combinations)."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("stems_status") != "ready":
    raise HTTPException(status_code=400, detail="Stems must be separated first")
  if song.get("variants_status") == "processing":
    raise HTTPException(status_code=409, detail="Variant generation already in progress")

  # Clear previous variants
  variants_dir = VARIANTS_DIR / song_id
  if variants_dir.exists():
    shutil.rmtree(variants_dir)
  variants_dir.mkdir(parents=True)

  updated = db.update_song(
    song_id,
    variants_status="processing",
    variants_error=None,
    variants_progress=0.0,
  )

  thread = threading.Thread(
    target=_variants_worker,
    args=(
      song_id,
      AUDIO_DIR / song["vocals_filename"],
      AUDIO_DIR / song["instrumental_filename"],
      VIDEOS_DIR / song["video_filename"],
      variants_dir,
      req.eq_match,
      req.exciter,
    ),
    daemon=True,
  )
  thread.start()

  return updated


@write_router.delete("/api/songs/{song_id}/variants", response_model=Song)
def delete_variants(song_id: str):
  """Remove all pre-generated audio variants."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  variants_dir = VARIANTS_DIR / song_id
  if variants_dir.exists():
    shutil.rmtree(variants_dir)

  updated = db.update_song(
    song_id,
    variants_status=None,
    variants_error=None,
    variants_progress=None,
  )
  return updated


@write_router.post("/api/songs/{song_id}/overlay", response_model=Song)
def start_overlay(song_id: str):
  """Render both lyrics overlay variants (lyrics-only and romanized)."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song["status"] != "ready":
    raise HTTPException(status_code=400, detail="Video must be downloaded first")
  if not song.get("lyrics_synced"):
    raise HTTPException(status_code=400, detail="Synced lyrics required")
  if song.get("overlay_status") == "processing":
    raise HTTPException(status_code=409, detail="Overlay rendering already in progress")

  lyrics_filename = f"{song_id}_overlay_lyrics.mp4"
  romanized_filename = f"{song_id}_overlay_romanized.mp4"

  # Remove previous overlay files if they exist
  for old_key in (
    "overlay_filename",
    "overlay_lyrics_filename",
    "overlay_romanized_filename",
  ):
    old_name = song.get(old_key)
    if old_name:
      old_path = OVERLAYS_DIR / old_name
      if old_path.exists():
        old_path.unlink()

  updated = db.update_song(
    song_id,
    overlay_lyrics_filename=lyrics_filename,
    overlay_romanized_filename=romanized_filename,
    overlay_filename=None,
    overlay_status="processing",
    overlay_error=None,
    overlay_progress=0.0,
  )

  thread = threading.Thread(
    target=_overlay_worker,
    args=(
      song_id,
      VIDEOS_DIR / song["video_filename"],
      song["lyrics_synced"],
      OVERLAYS_DIR / lyrics_filename,
      OVERLAYS_DIR / romanized_filename,
    ),
    daemon=True,
  )
  thread.start()

  return updated


@write_router.delete("/api/songs/{song_id}/overlay", response_model=Song)
def delete_overlay(song_id: str):
  """Remove all overlay video files."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  for key in (
    "overlay_filename",
    "overlay_lyrics_filename",
    "overlay_romanized_filename",
  ):
    filename = song.get(key)
    if filename:
      path = OVERLAYS_DIR / filename
      if path.exists():
        path.unlink()

  updated = db.update_song(
    song_id,
    overlay_filename=None,
    overlay_lyrics_filename=None,
    overlay_romanized_filename=None,
    overlay_status=None,
    overlay_error=None,
  )
  return updated


@write_router.post("/api/songs/{song_id}/export", response_model=Song)
def start_export(song_id: str, req: ExportRequest):
  """Create an export video with vocals mixed at the requested level."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song.get("stems_status") != "ready":
    raise HTTPException(status_code=400, detail="Stems must be separated first")
  if song.get("export_status") == "processing":
    raise HTTPException(status_code=409, detail="Export already in progress")

  vocal_pct = int(round(req.vocal_level * 100))
  export_filename = f"{song_id}_export_v{vocal_pct}.mp4"

  # Remove previous export file if exists
  if song.get("export_filename"):
    old_path = EXPORTS_DIR / song["export_filename"]
    if old_path.exists():
      old_path.unlink()

  updated = db.update_song(
    song_id,
    export_filename=export_filename,
    export_status="processing",
    export_error=None,
    export_vocal_level=req.vocal_level,
    export_progress=0.0,
  )

  thread = threading.Thread(
    target=_export_worker,
    args=(
      song_id,
      VIDEOS_DIR / song["video_filename"],
      AUDIO_DIR / song["vocals_filename"],
      AUDIO_DIR / song["instrumental_filename"],
      EXPORTS_DIR / export_filename,
      req.vocal_level,
      song.get("duration"),
    ),
    daemon=True,
  )
  thread.start()

  return updated


@write_router.delete("/api/songs/{song_id}/export", response_model=Song)
def delete_export(song_id: str):
  """Remove the exported video file."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")

  if song.get("export_filename"):
    export_path = EXPORTS_DIR / song["export_filename"]
    if export_path.exists():
      export_path.unlink()

  updated = db.update_song(
    song_id,
    export_filename=None,
    export_status=None,
    export_error=None,
    export_vocal_level=None,
  )
  return updated


@write_router.post("/api/songs/{song_id}/thumbnail")
def regenerate_thumbnail(song_id: str):
  """Regenerate the thumbnail from the video."""
  song = db.get_song(song_id)
  if not song:
    raise HTTPException(status_code=404, detail="Song not found")
  if song["status"] != "ready":
    raise HTTPException(status_code=400, detail="Video must be downloaded first")

  video_path = VIDEOS_DIR / song["video_filename"]
  if not video_path.exists():
    raise HTTPException(status_code=404, detail="Video file not found")

  _generate_thumbnail(song_id, video_path)

  thumb_path = THUMBNAILS_DIR / f"{song_id}.jpg"
  if not thumb_path.exists():
    raise HTTPException(status_code=500, detail="Thumbnail generation failed")

  return {"status": "ok"}


# ── Background workers ────────────────────────────────────────────────────────


def _make_progress_cb(song_id: str, field: str, interval: float = 2.0):
  """Create a throttled progress callback that updates the DB at most every `interval` seconds."""
  import time

  last_update = [0.0]

  def callback(progress: float) -> None:
    now = time.monotonic()
    if now - last_update[0] >= interval:
      last_update[0] = now
      db.update_song(song_id, **{field: round(progress, 3)})

  return callback


def _lyrics_need_romanization(lyrics_lrc: str) -> bool:
  """Check if lyrics contain Korean (Hangul) characters that would benefit from romanization."""
  from karaoke_workflows.lyrics import parse_lyrics_content, romanize_korean

  lyrics = parse_lyrics_content(lyrics_lrc)
  return any(romanize_korean(line.text) is not None for line in lyrics)


def _overlay_worker(
  song_id: str,
  video_path: Path,
  lyrics_lrc: str,
  lyrics_output: Path,
  romanized_output: Path,
) -> None:
  """Background worker for lyrics overlay rendering (both variants).

  If lyrics don't need romanization (no Korean/CJK characters), we render
  once and copy the result for both variants to avoid duplicate work.
  """
  try:
    needs_romanization = _lyrics_need_romanization(lyrics_lrc)
    progress_cb = _make_progress_cb(song_id, "overlay_progress")

    if not needs_romanization:
      # Render once and reuse for both variants
      overlay_mod.create_overlay(
        video_path,
        lyrics_lrc,
        lyrics_output,
        on_progress=progress_cb,
        romanize=False,
      )
      shutil.copy2(lyrics_output, romanized_output)
      print(f"Overlay ready (no romanization needed, reused): {song_id}")
    else:
      # 1) Render lyrics-only (no romanization) — 0-50%
      def lyrics_progress(p: float) -> None:
        progress_cb(p * 0.5)

      overlay_mod.create_overlay(
        video_path,
        lyrics_lrc,
        lyrics_output,
        on_progress=lyrics_progress,
        romanize=False,
      )
      print(f"Overlay lyrics variant ready: {song_id}")

      # 2) Render romanized — 50-100%
      def romanized_progress(p: float) -> None:
        progress_cb(0.5 + p * 0.5)

      overlay_mod.create_overlay(
        video_path,
        lyrics_lrc,
        romanized_output,
        on_progress=romanized_progress,
        romanize=True,
      )
      print(f"Overlay romanized variant ready: {song_id}")

    db.update_song(song_id, overlay_status="ready", overlay_progress=1.0)
  except Exception as e:
    db.update_song(song_id, overlay_status="error", overlay_error=str(e)[:500])
    print(f"Overlay failed for {song_id}: {e}")


def _export_worker(
  song_id: str,
  video_path: Path,
  vocals_path: Path,
  instrumental_path: Path,
  output_path: Path,
  vocal_level: float,
  duration: float | None = None,
) -> None:
  """Background worker for video export."""
  try:
    on_progress = _make_progress_cb(song_id, "export_progress")
    export_mod.create_export(
      video_path,
      vocals_path,
      instrumental_path,
      output_path,
      vocal_level,
      duration=duration,
      on_progress=on_progress,
    )
    db.update_song(song_id, export_status="ready", export_progress=1.0)
    print(f"Export ready: {song_id}")
  except Exception as e:
    db.update_song(song_id, export_status="error", export_error=str(e)[:500])
    print(f"Export failed for {song_id}: {e}")


_EQ_BANDS_HZ = [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
_EQ_MAX_GAIN_DB = 12.0

# Per-band correction strength for frequency-dependent EQ matching.
# Vocals mostly occupy 300 Hz–4 kHz, so spectral holes there are expected after
# vocal removal — we correct very lightly.  Outside that range the losses are
# artifacts of the separation process and we can correct more aggressively.
_EQ_BAND_STRENGTH: dict[int, float] = {
  63: 0.5,  # sub-bass — vocals don't live here, losses are artifacts
  125: 0.45,  # bass
  250: 0.35,  # upper bass / low-mid transition
  500: 0.12,  # low-mid — vocal fundamental range starts
  1000: 0.10,  # mid — vocal core
  2000: 0.10,  # upper-mid — vocal presence
  4000: 0.30,  # presence — sibilance removed, partial restore
  8000: 0.40,  # brilliance — breath/air removed by separation
  16000: 0.45,  # air — high-freq artifacts from separation
}


def _read_pcm_mono(path: Path, sample_rate: int = 22050) -> "np.ndarray":
  """Decode audio to a mono float32 numpy array via ffmpeg."""
  import numpy as np
  import subprocess as _sp

  cmd = [
    "ffmpeg",
    "-y",
    "-i",
    str(path),
    "-ac",
    "1",
    "-ar",
    str(sample_rate),
    "-f",
    "f32le",
    "pipe:1",
  ]
  result = _sp.run(cmd, capture_output=True, timeout=300)
  if result.returncode != 0:
    raise RuntimeError(
      f"PCM decode failed: {result.stderr.decode(errors='replace')[-200:]}"
    )
  return np.frombuffer(result.stdout, dtype=np.float32)


def _compute_eq_filter(original_path: Path, instrumental_path: Path) -> str:
  """Measure per-band gain difference between original and instrumental, return ffmpeg filter string.

  Uses 10-second FFT chunks averaged over the whole file.  For each octave-band
  centre frequency the raw correction is scaled by _EQ_BAND_STRENGTH (low in the
  vocal range where spectral holes are expected, higher in bass/treble where losses
  are separation artifacts) then clamped to ±_EQ_MAX_GAIN_DB dB.
  Returns an empty string if numpy is unavailable or analysis fails.
  """
  try:
    import numpy as np
  except ImportError:
    return ""

  try:
    sr = 22050
    orig = _read_pcm_mono(original_path, sr)
    inst = _read_pcm_mono(instrumental_path, sr)

    length = min(len(orig), len(inst))
    orig = orig[:length]
    inst = inst[:length]

    chunk = sr * 10
    n_chunks = max(1, length // chunk)
    half = chunk // 2 + 1
    orig_pwr = np.zeros(half)
    inst_pwr = np.zeros(half)

    for k in range(n_chunks):
      o = orig[k * chunk : (k + 1) * chunk]
      i = inst[k * chunk : (k + 1) * chunk]
      if len(o) < chunk:
        o = np.pad(o, (0, chunk - len(o)))
        i = np.pad(i, (0, chunk - len(i)))
      orig_pwr += np.abs(np.fft.rfft(o)) ** 2
      inst_pwr += np.abs(np.fft.rfft(i)) ** 2

    freqs = np.fft.rfftfreq(chunk, 1.0 / sr)
    parts = []
    for hz in _EQ_BANDS_HZ:
      mask = (freqs >= hz / 1.5) & (freqs <= hz * 1.5)
      if not mask.any():
        continue
      o_band = orig_pwr[mask].mean()
      i_band = inst_pwr[mask].mean()
      if o_band < 1e-12 or i_band < 1e-12:
        continue
      gain_db = 10.0 * np.log10(o_band / i_band)
      gain_db = gain_db * _EQ_BAND_STRENGTH.get(hz, 0.2)
      gain_db = max(-_EQ_MAX_GAIN_DB, min(_EQ_MAX_GAIN_DB, gain_db))
      if abs(gain_db) >= 0.5:
        parts.append(f"equalizer=f={hz}:width_type=o:width=1:g={gain_db:.1f}")

    return ",".join(parts)
  except Exception as e:
    print(f"EQ analysis failed, skipping: {e}")
    return ""


def _build_pitch_filter(semitones: float, sample_rate: int = 44100) -> str:
  """Build ffmpeg filter suffix for pitch shifting without tempo change.

  Uses aformat (to normalize sample rate) + asetrate + aresample + atempo chain.
  The aformat step is critical: input audio may not be at sample_rate (e.g. demucs
  outputs 48kHz), so we must normalize first or the asetrate shift will be wrong.
  """
  if semitones == 0:
    return ""
  factor = 2 ** (semitones / 12)
  shifted_rate = round(sample_rate * factor)
  tempo = 1.0 / factor
  return (
    f",aformat=sample_rates={sample_rate}"
    f",asetrate={shifted_rate}"
    f",aresample={sample_rate}"
    f",atempo={tempo:.6f}"
  )


def _build_exciter_filter() -> str:
  """Build an ffmpeg aexciter filter to restore brightness lost during vocal removal.

  Generates harmonics above the cutoff frequency with moderate drive and blend
  to add perceived air/presence without the artificial feel of static EQ boosting.
  Parameters: freq=4000 (process above 4 kHz), drive=4 (moderate harmonic generation),
  blend=2 (mix harmonics into output), amount=2 (subtle effect level).
  """
  return "aexciter=freq=4000:drive=4:blend=2:amount=2"


def _variants_worker(
  song_id: str,
  vocals_path: Path,
  instrumental_path: Path,
  original_path: Path,
  output_dir: Path,
  eq_match: bool = False,
  exciter: bool = False,
) -> None:
  """Background worker to pre-generate all audio variants (pitch × vocal level)."""
  import subprocess as _sp

  combos = [(p, v) for p in VARIANT_PITCHES for v in VARIANT_VOCALS]
  total = len(combos)
  on_progress = _make_progress_cb(song_id, "variants_progress")

  # Pre-compute the EQ correction filter once for this song (applied to non-100% vocal variants)
  eq_filter = ""
  if eq_match:
    print(f"Computing frequency-dependent EQ correction for {song_id}...")
    eq_filter = _compute_eq_filter(original_path, instrumental_path)
    print(f"EQ filter: {eq_filter or '(none)'}")

  # Harmonic exciter filter for restoring brightness
  exciter_filter = ""
  if exciter:
    exciter_filter = _build_exciter_filter()
    print(f"Exciter filter: {exciter_filter}")

  try:
    for i, (pitch, vocal) in enumerate(combos):
      out_path = output_dir / f"p{pitch}_v{vocal}.mp3"
      vocal_level = vocal / 100.0

      pitch_filter = _build_pitch_filter(pitch)

      # Build instrumental processing chain (EQ + exciter applied when vocals are reduced)
      inst_filters = []
      if eq_filter and vocal < 100:
        inst_filters.append(eq_filter)
      if exciter_filter and vocal < 100:
        inst_filters.append(exciter_filter)

      if inst_filters:
        combined = ",".join(inst_filters)
        inst_chain = f"[0:a]{combined}[inst_proc];[inst_proc]"
      else:
        inst_chain = "[0:a]"

      filter_complex = (
        f"[1:a]volume={vocal_level}[v];"
        f"{inst_chain}[v]amix=inputs=2:duration=longest:normalize=0{pitch_filter}[a]"
      )

      cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(instrumental_path),
        "-i",
        str(vocals_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(out_path),
      ]

      result = _sp.run(cmd, capture_output=True, timeout=300)
      if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg failed for p{pitch}_v{vocal}: {stderr}")

      on_progress((i + 1) / total)

    db.update_song(song_id, variants_status="ready", variants_progress=1.0)
    print(f"Variants ready: {song_id}")
  except Exception as e:
    db.update_song(song_id, variants_status="error", variants_error=str(e)[:500])
    print(f"Variants failed for {song_id}: {e}")


def _stems_worker(
  song_id: str,
  video_path: Path,
  vocals_out: Path,
  instrumental_out: Path,
  eq_match: bool = False,
  exciter: bool = False,
) -> None:
  """Background worker for Demucs stem separation."""
  try:
    demucs.separate(video_path, vocals_out, instrumental_out)
    db.update_song(song_id, stems_status="ready")
    print(f"Stems ready: {song_id}")

    # Auto-trigger variant generation
    variants_dir = VARIANTS_DIR / song_id
    variants_dir.mkdir(parents=True, exist_ok=True)
    db.update_song(song_id, variants_status="processing", variants_progress=0.0)
    _variants_worker(
      song_id,
      vocals_out,
      instrumental_out,
      video_path,
      variants_dir,
      eq_match,
      exciter,
    )
  except Exception as e:
    db.update_song(song_id, stems_status="error", stems_error=str(e)[:500])
    print(f"Stems failed for {song_id}: {e}")


def _generate_thumbnail(song_id: str, video_path: Path) -> None:
  """Extract a thumbnail from a video at ~30% of duration (avoids intros/outros)."""
  import subprocess as _sp

  thumb_path = THUMBNAILS_DIR / f"{song_id}.jpg"

  # Probe duration
  probe = _sp.run(
    [
      "ffprobe",
      "-v",
      "quiet",
      "-print_format",
      "json",
      "-show_format",
      str(video_path),
    ],
    capture_output=True,
    timeout=10,
  )
  seek_time = 10  # fallback
  if probe.returncode == 0:
    import json

    try:
      info = json.loads(probe.stdout)
      duration = float(info["format"]["duration"])
      seek_time = duration * 0.3
    except (KeyError, ValueError, json.JSONDecodeError):
      pass

  # Extract a single keyframe-aligned frame
  result = _sp.run(
    [
      "ffmpeg",
      "-y",
      "-ss",
      str(seek_time),
      "-i",
      str(video_path),
      "-frames:v",
      "1",
      "-q:v",
      "3",
      str(thumb_path),
    ],
    capture_output=True,
    timeout=15,
  )
  if result.returncode == 0:
    print(f"Thumbnail generated: {song_id}")
  else:
    print(
      f"Thumbnail failed for {song_id}: {result.stderr.decode(errors='replace')[-200:]}"
    )


def _download_worker(song_id: str, url: str, output_path: Path) -> None:
  """Background worker to download a video."""
  try:
    ytdlp.download(url, output_path)
    db.update_song(song_id, status="ready")
    print(f"Download complete: {song_id}")

    # Generate thumbnail from downloaded video
    _generate_thumbnail(song_id, output_path)
  except Exception as e:
    db.update_song(song_id, status="error", error_message=str(e)[:500])
    print(f"Download failed for {song_id}: {e}")


# ── Register full-mode router ─────────────────────────────────────────────────

if not SERVE_MODE:
  app.include_router(write_router)

if __name__ == "__main__":
  import uvicorn

  port = int(os.environ.get("PORT", 8001))
  uvicorn.run(app, host="0.0.0.0", port=port)
