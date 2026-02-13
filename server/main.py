"""FastAPI backend for karaoke song management."""

import os
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import db
import demucs
import export as export_mod
import lrclib
import ytdlp
from models import AddSongRequest, ExportRequest, LyricsSearchResult, SetLyricsRequest, Song, SearchResult

app = FastAPI(title="Karaoke API", version="0.1.0")

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


@app.on_event("startup")
def startup():
    db.init_db()
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search", response_model=list[SearchResult])
def search_videos(q: str = Query(..., min_length=1)):
    """Search YouTube for videos via yt-dlp."""
    try:
        return ytdlp.search(q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


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


@app.post("/api/songs", response_model=Song, status_code=201)
def add_song(req: AddSongRequest):
    """Add a song to the library and start downloading."""
    song_id = uuid.uuid4().hex[:12]
    video_filename = f"{song_id}.mp4"

    song = db.insert_song({
        "id": song_id,
        "title": req.title,
        "artist": req.artist,
        "duration": req.duration,
        "source_url": req.url,
        "video_filename": video_filename,
        "thumbnail_url": req.thumbnail_url,
        "status": "downloading",
    })

    # Download in background thread
    thread = threading.Thread(
        target=_download_worker,
        args=(song_id, req.url, VIDEOS_DIR / video_filename),
        daemon=True,
    )
    thread.start()

    return song


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    """Delete a song and its files."""
    song = db.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Remove video file
    if song.get("video_filename"):
        video_path = VIDEOS_DIR / song["video_filename"]
        if video_path.exists():
            video_path.unlink()

    # Remove audio stems
    for key in ("vocals_filename", "instrumental_filename"):
        if song.get(key):
            audio_path = AUDIO_DIR / song[key]
            if audio_path.exists():
                audio_path.unlink()

    # Remove export file
    if song.get("export_filename"):
        export_path = EXPORTS_DIR / song["export_filename"]
        if export_path.exists():
            export_path.unlink()

    db.delete_song(song_id)
    return {"status": "deleted"}


@app.get("/api/lyrics/search", response_model=list[LyricsSearchResult])
def search_lyrics(q: str = Query(..., min_length=1), duration: float | None = None):
    """Search lrclib.net for lyrics."""
    try:
        return lrclib.search(q, duration=duration)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.put("/api/songs/{song_id}/lyrics", response_model=Song)
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


@app.delete("/api/songs/{song_id}/lyrics", response_model=Song)
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


@app.post("/api/songs/{song_id}/stems", response_model=Song)
def start_stems(song_id: str):
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
        args=(song_id, video_path, AUDIO_DIR / vocals_filename, AUDIO_DIR / instrumental_filename),
        daemon=True,
    )
    thread.start()

    return updated


@app.delete("/api/songs/{song_id}/stems", response_model=Song)
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


@app.post("/api/songs/{song_id}/export", response_model=Song)
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
        ),
        daemon=True,
    )
    thread.start()

    return updated


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

    # Build a friendly download filename
    safe_title = "".join(c for c in (song.get("title") or "export") if c.isalnum() or c in " -_").strip()[:80]
    vocal_pct = int(round((song.get("export_vocal_level") or 0) * 100))
    download_name = f"{safe_title} (vocals {vocal_pct}%).mp4"

    return FileResponse(
        path=str(export_path),
        media_type="video/mp4",
        filename=download_name,
    )


@app.delete("/api/songs/{song_id}/export", response_model=Song)
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


def _export_worker(
    song_id: str, video_path: Path, vocals_path: Path,
    instrumental_path: Path, output_path: Path, vocal_level: float,
) -> None:
    """Background worker for video export."""
    try:
        export_mod.create_export(video_path, vocals_path, instrumental_path, output_path, vocal_level)
        db.update_song(song_id, export_status="ready")
        print(f"Export ready: {song_id}")
    except Exception as e:
        db.update_song(song_id, export_status="error", export_error=str(e)[:500])
        print(f"Export failed for {song_id}: {e}")


def _stems_worker(song_id: str, video_path: Path, vocals_out: Path, instrumental_out: Path) -> None:
    """Background worker for Demucs stem separation."""
    try:
        demucs.separate(video_path, vocals_out, instrumental_out)
        db.update_song(song_id, stems_status="ready")
        print(f"Stems ready: {song_id}")
    except Exception as e:
        db.update_song(song_id, stems_status="error", stems_error=str(e)[:500])
        print(f"Stems failed for {song_id}: {e}")


def _download_worker(song_id: str, url: str, output_path: Path) -> None:
    """Background worker to download a video."""
    try:
        ytdlp.download(url, output_path)
        db.update_song(song_id, status="ready")
        print(f"Download complete: {song_id}")
    except Exception as e:
        db.update_song(song_id, status="error", error_message=str(e)[:500])
        print(f"Download failed for {song_id}: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
