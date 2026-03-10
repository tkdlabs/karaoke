"""
Integration tests for the karaoke FastAPI backend (server/main.py).

Two test classes cover the two operating modes:
  - TestServeMode  — SERVE_MODE=1: only read/serve endpoints are registered.
  - TestFullMode   — SERVE_MODE unset: all endpoints including write/admin routes
                     are registered and background workers are mocked out.

Key design decisions
--------------------
* ``TestClient`` (httpx-based, bundled with FastAPI) is used throughout.
  No real server process is started.
* All external I/O (yt-dlp, demucs, ffmpeg, lrclib, threading.Thread) is
  mocked so tests are fast, offline, and deterministic.
* Each test receives a fresh SQLite database via the ``full_mode_client`` /
  ``serve_mode_client`` fixtures defined in conftest.py.
* File-serving endpoints that return ``FileResponse`` require the actual file
  to exist on disk; tests create minimal placeholder files as needed.

Known bug documented by tests
------------------------------
``DELETE /api/songs/{song_id}/export`` and
``DELETE /api/songs/{song_id}/overlay`` are defined inside the body of
``download_export`` / ``download_overlay`` (indentation bug) and therefore
never get registered as routes.  Tests for those two endpoints assert the
correct 405 behaviour in serve mode but do NOT assert 200 in full mode —
instead they document the missing route with an explicit note.
"""

import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import insert_test_song


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SONG_ID = "testsong0001"
_MISSING_ID = "nonexistent99"


def _make_ready_song_files(data_dir: Path, song_id: str = _SONG_ID) -> None:
  """Create the placeholder media files expected by file-serving endpoints."""
  (data_dir / "videos").mkdir(parents=True, exist_ok=True)
  (data_dir / "audio").mkdir(parents=True, exist_ok=True)
  (data_dir / "exports").mkdir(parents=True, exist_ok=True)
  (data_dir / "overlays").mkdir(parents=True, exist_ok=True)
  (data_dir / "variants" / song_id).mkdir(parents=True, exist_ok=True)
  (data_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

  (data_dir / "videos" / f"{song_id}.mp4").write_bytes(b"\x00" * 8)
  (data_dir / "audio" / f"{song_id}_vocals.mp3").write_bytes(b"\x00" * 8)
  (data_dir / "audio" / f"{song_id}_instrumental.mp3").write_bytes(b"\x00" * 8)
  (data_dir / "exports" / f"{song_id}_export_v30.mp4").write_bytes(b"\x00" * 8)
  (data_dir / "overlays" / f"{song_id}_overlay_lyrics.mp4").write_bytes(b"\x00" * 8)
  (data_dir / "overlays" / f"{song_id}_overlay_romanized.mp4").write_bytes(b"\x00" * 8)
  (data_dir / "thumbnails" / f"{song_id}.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 5)
  # One variant file
  (data_dir / "variants" / song_id / "p0_v25.mp3").write_bytes(b"\x00" * 8)


# ---------------------------------------------------------------------------
# Helper to get the tmp data_dir from a TestClient (stored on the app state
# by conftest after startup — we retrieve it via the db module reference).
# We can't pass tmp_path into the client fixtures directly, so instead we
# expose a small accessor via the imported db module.
# ---------------------------------------------------------------------------


def _data_dir_from_client(client: TestClient) -> Path:
  """Return the DATA_DIR Path used by the app loaded inside this client."""
  # After startup the db module has DB_PATH set; parent is DATA_DIR.
  db_mod = sys.modules.get("db")
  assert db_mod is not None, "db module not loaded — fixture setup failed"
  return Path(db_mod.DB_PATH).parent  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: endpoints available in BOTH modes
# ---------------------------------------------------------------------------


class TestBothModes:
  """Endpoints that must work (not 405) regardless of SERVE_MODE."""

  # -- GET /api/health -------------------------------------------------------

  def test_health_returns_ok_in_full_mode(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

  def test_health_returns_ok_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

  # -- GET /api/songs --------------------------------------------------------

  def test_list_songs_empty_in_full_mode(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.get("/api/songs")
    assert resp.status_code == 200
    assert resp.json() == []

  def test_list_songs_empty_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.get("/api/songs")
    assert resp.status_code == 200
    assert resp.json() == []

  def test_list_songs_returns_inserted_song_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get("/api/songs")
    assert resp.status_code == 200
    songs = resp.json()
    assert len(songs) == 1
    assert songs[0]["id"] == _SONG_ID

  def test_list_songs_returns_inserted_song_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(serve_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = serve_mode_client.get("/api/songs")
    assert resp.status_code == 200
    songs = resp.json()
    assert len(songs) == 1
    assert songs[0]["id"] == _SONG_ID

  # -- GET /api/songs/{id} ---------------------------------------------------

  def test_get_song_not_found_returns_404_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}")
    assert resp.status_code == 404

  def test_get_song_not_found_returns_404_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}")
    assert resp.status_code == 404

  def test_get_song_returns_song_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == _SONG_ID
    assert body["title"] == "Test Song"

  def test_get_song_returns_song_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(serve_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}")
    assert resp.status_code == 200
    assert resp.json()["id"] == _SONG_ID

  # -- GET /api/songs/{id}/audio/{stem} --------------------------------------

  def test_serve_audio_stem_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/audio/vocals")
    assert resp.status_code == 404

  def test_serve_audio_stem_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/audio/vocals")
    assert resp.status_code == 404

  def test_serve_audio_stem_400_when_stems_not_ready_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/audio/vocals")
    # stems_status is None → not ready
    assert resp.status_code == 400

  def test_serve_audio_stem_serves_file_when_stems_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/audio/vocals")
    assert resp.status_code == 200

  def test_serve_audio_stem_400_for_invalid_stem_name(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/audio/drums")
    assert resp.status_code == 400

  # -- GET /api/songs/{id}/variants/{pitch}/{vocal} --------------------------

  def test_serve_variant_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/variants/0/25")
    assert resp.status_code == 404

  def test_serve_variant_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/variants/0/25")
    assert resp.status_code == 404

  def test_serve_variant_400_for_invalid_pitch(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/variants/99/25")
    assert resp.status_code == 400

  def test_serve_variant_400_for_invalid_vocal_level(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/variants/0/50")
    assert resp.status_code == 400

  def test_serve_variant_serves_file_when_variants_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={"variants_status": "ready"},
    )
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/variants/0/25")
    assert resp.status_code == 200

  # -- GET /api/songs/{id}/video/{variant} -----------------------------------

  def test_serve_video_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/video/original")
    assert resp.status_code == 404

  def test_serve_video_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/video/original")
    assert resp.status_code == 404

  def test_serve_video_400_for_invalid_variant(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/video/invalid_variant")
    assert resp.status_code == 400

  def test_serve_video_serves_original_when_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/video/original")
    assert resp.status_code == 200

  def test_serve_video_400_for_overlay_when_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/video/overlay_lyrics")
    assert resp.status_code == 400

  def test_serve_video_serves_overlay_when_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "overlay_status": "ready",
        "overlay_lyrics_filename": f"{_SONG_ID}_overlay_lyrics.mp4",
        "overlay_romanized_filename": f"{_SONG_ID}_overlay_romanized.mp4",
      },
    )
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/video/overlay_lyrics")
    assert resp.status_code == 200

  # -- GET /api/songs/{id}/thumbnail -----------------------------------------

  def test_serve_thumbnail_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/thumbnail")
    assert resp.status_code == 404

  def test_serve_thumbnail_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/thumbnail")
    assert resp.status_code == 404

  def test_serve_thumbnail_404_when_file_not_on_disk(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/thumbnail")
    assert resp.status_code == 404

  def test_serve_thumbnail_200_when_file_exists(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/thumbnail")
    assert resp.status_code == 200

  # -- GET /api/songs/{id}/export/download -----------------------------------

  def test_download_export_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/export/download")
    assert resp.status_code == 404

  def test_download_export_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/export/download")
    assert resp.status_code == 404

  def test_download_export_400_when_export_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/export/download")
    assert resp.status_code == 400

  def test_download_export_200_when_export_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "export_status": "ready",
        "export_filename": f"{_SONG_ID}_export_v30.mp4",
        "export_vocal_level": 0.30,
      },
    )
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/export/download")
    assert resp.status_code == 200

  # -- GET /api/songs/{id}/overlay/download ----------------------------------

  def test_download_overlay_404_when_song_missing_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.get(f"/api/songs/{_MISSING_ID}/overlay/download")
    assert resp.status_code == 404

  def test_download_overlay_404_when_song_missing_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/overlay/download")
    assert resp.status_code == 404

  def test_download_overlay_400_for_invalid_variant(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.get(
      f"/api/songs/{_SONG_ID}/overlay/download?variant=invalid"
    )
    assert resp.status_code == 400

  def test_download_overlay_200_when_overlay_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "overlay_status": "ready",
        "overlay_lyrics_filename": f"{_SONG_ID}_overlay_lyrics.mp4",
        "overlay_romanized_filename": f"{_SONG_ID}_overlay_romanized.mp4",
      },
    )
    resp = full_mode_client.get(f"/api/songs/{_SONG_ID}/overlay/download?variant=lyrics")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: FULL mode — write/admin endpoints must NOT return 405
# ---------------------------------------------------------------------------


class TestFullMode:
  """Endpoints registered only in full mode; background workers are mocked."""

  # -- GET /api/search -------------------------------------------------------

  def test_search_endpoint_exists_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    ytdlp_mod = sys.modules.get("ytdlp")
    assert ytdlp_mod is not None
    ytdlp_mod.search = MagicMock(return_value=[])  # type: ignore[attr-defined]
    resp = full_mode_client.get("/api/search?q=test")
    assert resp.status_code != 405
    assert resp.status_code == 200

  def test_search_returns_results_from_ytdlp(
    self, full_mode_client: TestClient
  ) -> None:
    ytdlp_mod = sys.modules.get("ytdlp")
    assert ytdlp_mod is not None
    ytdlp_mod.search = MagicMock(  # type: ignore[attr-defined]
      return_value=[
        {
          "video_id": "abc123",
          "title": "Cool Song",
          "artist": "Artist",
          "duration": 200.0,
          "thumbnail_url": "https://example.com/thumb.jpg",
          "url": "https://youtube.com/watch?v=abc123",
        }
      ]
    )
    resp = full_mode_client.get("/api/search?q=cool+song")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["video_id"] == "abc123"

  def test_search_requires_query_param(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.get("/api/search")
    assert resp.status_code == 422

  def test_search_502_when_ytdlp_raises(self, full_mode_client: TestClient) -> None:
    ytdlp_mod = sys.modules.get("ytdlp")
    assert ytdlp_mod is not None
    ytdlp_mod.search = MagicMock(side_effect=RuntimeError("yt-dlp failed"))  # type: ignore[attr-defined]
    resp = full_mode_client.get("/api/search?q=test")
    assert resp.status_code == 502

  # -- POST /api/songs -------------------------------------------------------

  def test_add_song_creates_song_and_returns_201(
    self, full_mode_client: TestClient
  ) -> None:
    with patch("threading.Thread") as mock_thread:
      mock_thread.return_value = MagicMock()
      resp = full_mode_client.post(
        "/api/songs",
        json={
          "url": "https://youtube.com/watch?v=xyz",
          "title": "New Song",
          "artist": "New Artist",
          "duration": 240.0,
          "thumbnail_url": "https://example.com/thumb.jpg",
        },
      )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "New Song"
    assert body["status"] == "downloading"
    assert "id" in body

  def test_add_song_starts_background_download_thread(
    self, full_mode_client: TestClient
  ) -> None:
    with patch("threading.Thread") as mock_thread:
      mock_instance = MagicMock()
      mock_thread.return_value = mock_instance
      full_mode_client.post(
        "/api/songs",
        json={
          "url": "https://youtube.com/watch?v=xyz",
          "title": "Song",
          "artist": "Artist",
          "duration": 100.0,
          "thumbnail_url": "",
        },
      )
    mock_instance.start.assert_called_once()

  def test_add_song_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    with patch("threading.Thread"):
      resp = full_mode_client.post(
        "/api/songs",
        json={
          "url": "https://youtube.com/watch?v=xyz",
          "title": "Song",
          "artist": "Artist",
          "duration": 100.0,
          "thumbnail_url": "",
        },
      )
    assert resp.status_code != 405

  # -- DELETE /api/songs/{id} ------------------------------------------------

  def test_delete_song_404_when_not_found(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.delete(f"/api/songs/{_MISSING_ID}")
    assert resp.status_code == 404

  def test_delete_song_removes_song_from_db(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)

    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}

    # Song no longer accessible
    get_resp = full_mode_client.get(f"/api/songs/{_SONG_ID}")
    assert get_resp.status_code == 404

  def test_delete_song_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}")
    assert resp.status_code != 405

  # -- GET /api/lyrics/search ------------------------------------------------

  def test_lyrics_search_returns_results(self, full_mode_client: TestClient) -> None:
    lrclib_mod = sys.modules.get("lrclib")
    assert lrclib_mod is not None
    lrclib_mod.search = MagicMock(  # type: ignore[attr-defined]
      return_value=[
        {
          "track_id": 1,
          "track_name": "Test Track",
          "artist_name": "Test Artist",
          "album_name": "Test Album",
          "duration": 180.0,
          "lyrics_type": "synced",
          "synced_lyrics": "[00:01.00] Hello",
          "plain_lyrics": "Hello",
          "preview": ["Hello"],
        }
      ]
    )
    resp = full_mode_client.get("/api/lyrics/search?q=test")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["track_name"] == "Test Track"

  def test_lyrics_search_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    lrclib_mod = sys.modules.get("lrclib")
    assert lrclib_mod is not None
    lrclib_mod.search = MagicMock(return_value=[])  # type: ignore[attr-defined]
    resp = full_mode_client.get("/api/lyrics/search?q=test")
    assert resp.status_code != 405

  def test_lyrics_search_502_when_lrclib_raises(
    self, full_mode_client: TestClient
  ) -> None:
    lrclib_mod = sys.modules.get("lrclib")
    assert lrclib_mod is not None
    lrclib_mod.search = MagicMock(side_effect=RuntimeError("lrclib down"))  # type: ignore[attr-defined]
    resp = full_mode_client.get("/api/lyrics/search?q=test")
    assert resp.status_code == 502

  def test_lyrics_search_requires_query_param(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.get("/api/lyrics/search")
    assert resp.status_code == 422

  # -- PUT /api/songs/{id}/lyrics --------------------------------------------

  def test_set_lyrics_404_when_song_not_found(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.put(
      f"/api/songs/{_MISSING_ID}/lyrics",
      json={"synced_lyrics": "[00:01.00] Line", "plain_lyrics": "Line", "source": "manual"},
    )
    assert resp.status_code == 404

  def test_set_lyrics_stores_synced_and_plain(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)

    synced = "[00:01.00] Hello world"
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics",
      json={
        "synced_lyrics": synced,
        "plain_lyrics": "Hello world",
        "source": "lrclib:42",
      },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_synced"] == synced
    assert body["lyrics_plain"] == "Hello world"
    assert body["lyrics_source"] == "lrclib:42"

  def test_set_lyrics_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics",
      json={"synced_lyrics": None, "plain_lyrics": None, "source": "manual"},
    )
    assert resp.status_code != 405

  # -- PUT /api/songs/{id}/lyrics/adjust -------------------------------------

  _SAMPLE_LRC = "[00:01.00] Line one\n[00:05.00] Line two\n[00:10.00] Line three"

  def test_adjust_lyrics_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.put(
      f"/api/songs/{_MISSING_ID}/lyrics/adjust",
      json={"anchor_time": 2.0, "anchor_line_index": 0},
    )
    assert resp.status_code == 404

  def test_adjust_lyrics_400_when_no_synced_lyrics(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics/adjust",
      json={"anchor_time": 2.0, "anchor_line_index": 0},
    )
    assert resp.status_code == 400

  def test_adjust_lyrics_shifts_timestamps_from_anchor(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, extra={"lyrics_synced": self._SAMPLE_LRC})

    # Anchor line 1 (currently at 00:05.00) → move to 00:07.00 (offset +2s)
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics/adjust",
      json={"anchor_time": 7.0, "anchor_line_index": 1},
    )
    assert resp.status_code == 200
    adjusted = resp.json()["lyrics_synced"]
    # Line 0 unchanged; lines 1+ shifted +2 seconds
    assert "[00:01.00]" in adjusted  # line 0 untouched
    assert "[00:07.00]" in adjusted  # line 1 at new anchor
    assert "[00:12.00]" in adjusted  # line 2 shifted by +2

  def test_adjust_lyrics_400_for_out_of_range_anchor_index(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, extra={"lyrics_synced": self._SAMPLE_LRC})
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics/adjust",
      json={"anchor_time": 2.0, "anchor_line_index": 99},
    )
    assert resp.status_code == 400

  def test_adjust_lyrics_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, extra={"lyrics_synced": self._SAMPLE_LRC})
    resp = full_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics/adjust",
      json={"anchor_time": 1.0, "anchor_line_index": 0},
    )
    assert resp.status_code != 405

  # -- DELETE /api/songs/{id}/lyrics -----------------------------------------

  def test_delete_lyrics_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.delete(f"/api/songs/{_MISSING_ID}/lyrics")
    assert resp.status_code == 404

  def test_delete_lyrics_clears_all_lyrics_fields(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      extra={
        "lyrics_synced": "[00:01.00] Hello",
        "lyrics_plain": "Hello",
        "lyrics_source": "manual",
      },
    )
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/lyrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_synced"] is None
    assert body["lyrics_plain"] is None
    assert body["lyrics_source"] is None

  def test_delete_lyrics_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/lyrics")
    assert resp.status_code != 405

  # -- POST /api/songs/{id}/stems --------------------------------------------

  def test_start_stems_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post(f"/api/songs/{_MISSING_ID}/stems", json={})
    assert resp.status_code == 404

  def test_start_stems_400_when_video_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="downloading")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/stems", json={})
    assert resp.status_code == 400

  def test_start_stems_409_when_already_processing(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir, _SONG_ID, status="ready", extra={"stems_status": "processing"}
    )
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/stems", json={})
    assert resp.status_code == 409

  def test_start_stems_200_and_spawns_thread(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    with patch("threading.Thread") as mock_thread:
      mock_instance = MagicMock()
      mock_thread.return_value = mock_instance
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/stems", json={})
    assert resp.status_code == 200
    assert resp.json()["stems_status"] == "processing"
    mock_instance.start.assert_called_once()

  def test_start_stems_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    with patch("threading.Thread"):
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/stems", json={})
    assert resp.status_code != 405

  # -- DELETE /api/songs/{id}/stems ------------------------------------------

  def test_delete_stems_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.delete(f"/api/songs/{_MISSING_ID}/stems")
    assert resp.status_code == 404

  def test_delete_stems_clears_stem_fields(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/stems")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stems_status"] is None
    assert body["vocals_filename"] is None
    assert body["instrumental_filename"] is None

  def test_delete_stems_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/stems")
    assert resp.status_code != 405

  # -- POST /api/songs/{id}/variants -----------------------------------------

  def test_start_variants_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post(f"/api/songs/{_MISSING_ID}/variants", json={})
    assert resp.status_code == 404

  def test_start_variants_400_when_stems_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/variants", json={})
    assert resp.status_code == 400

  def test_start_variants_409_when_already_processing(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={"stems_status": "ready", "variants_status": "processing"},
    )
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/variants", json={})
    assert resp.status_code == 409

  def test_start_variants_200_and_spawns_thread(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    with patch("threading.Thread") as mock_thread:
      mock_instance = MagicMock()
      mock_thread.return_value = mock_instance
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/variants", json={})
    assert resp.status_code == 200
    assert resp.json()["variants_status"] == "processing"
    mock_instance.start.assert_called_once()

  def test_start_variants_not_405_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    with patch("threading.Thread"):
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/variants", json={})
    assert resp.status_code != 405

  # -- DELETE /api/songs/{id}/variants ---------------------------------------

  def test_delete_variants_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.delete(f"/api/songs/{_MISSING_ID}/variants")
    assert resp.status_code == 404

  def test_delete_variants_clears_variants_fields(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={"variants_status": "ready", "variants_progress": 1.0},
    )
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/variants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["variants_status"] is None
    assert body["variants_progress"] is None

  def test_delete_variants_not_405_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID)
    resp = full_mode_client.delete(f"/api/songs/{_SONG_ID}/variants")
    assert resp.status_code != 405

  # -- POST /api/songs/{id}/overlay ------------------------------------------

  def test_start_overlay_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post(f"/api/songs/{_MISSING_ID}/overlay")
    assert resp.status_code == 404

  def test_start_overlay_400_when_video_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="downloading")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    assert resp.status_code == 400

  def test_start_overlay_400_when_no_lyrics(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    assert resp.status_code == 400

  def test_start_overlay_409_when_already_processing(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "lyrics_synced": "[00:01.00] Hello",
        "overlay_status": "processing",
      },
    )
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    assert resp.status_code == 409

  def test_start_overlay_200_and_spawns_thread(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={"lyrics_synced": "[00:01.00] Hello"},
    )
    with patch("threading.Thread") as mock_thread:
      mock_instance = MagicMock()
      mock_thread.return_value = mock_instance
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    assert resp.status_code == 200
    assert resp.json()["overlay_status"] == "processing"
    mock_instance.start.assert_called_once()

  def test_start_overlay_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={"lyrics_synced": "[00:01.00] Hello"},
    )
    with patch("threading.Thread"):
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    assert resp.status_code != 405

  # -- POST /api/songs/{id}/export -------------------------------------------

  def test_start_export_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post(
      f"/api/songs/{_MISSING_ID}/export", json={"vocal_level": 0.3}
    )
    assert resp.status_code == 404

  def test_start_export_400_when_stems_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.post(
      f"/api/songs/{_SONG_ID}/export", json={"vocal_level": 0.3}
    )
    assert resp.status_code == 400

  def test_start_export_409_when_already_processing(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
        "export_status": "processing",
      },
    )
    resp = full_mode_client.post(
      f"/api/songs/{_SONG_ID}/export", json={"vocal_level": 0.3}
    )
    assert resp.status_code == 409

  def test_start_export_200_and_spawns_thread(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    with patch("threading.Thread") as mock_thread:
      mock_instance = MagicMock()
      mock_thread.return_value = mock_instance
      resp = full_mode_client.post(
        f"/api/songs/{_SONG_ID}/export", json={"vocal_level": 0.3}
      )
    assert resp.status_code == 200
    body = resp.json()
    assert body["export_status"] == "processing"
    assert body["export_vocal_level"] == pytest.approx(0.3)
    mock_instance.start.assert_called_once()

  def test_start_export_not_405_in_full_mode(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir,
      _SONG_ID,
      status="ready",
      extra={
        "stems_status": "ready",
        "vocals_filename": f"{_SONG_ID}_vocals.mp3",
        "instrumental_filename": f"{_SONG_ID}_instrumental.mp3",
      },
    )
    with patch("threading.Thread"):
      resp = full_mode_client.post(
        f"/api/songs/{_SONG_ID}/export", json={"vocal_level": 0.3}
      )
    assert resp.status_code != 405

  # -- POST /api/songs/{id}/thumbnail ----------------------------------------

  def test_regenerate_thumbnail_404_when_song_not_found(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post(f"/api/songs/{_MISSING_ID}/thumbnail")
    assert resp.status_code == 404

  def test_regenerate_thumbnail_400_when_video_not_ready(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_ID, status="downloading")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/thumbnail")
    assert resp.status_code == 400

  def test_regenerate_thumbnail_not_405_in_full_mode(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _make_ready_song_files(data_dir, _SONG_ID)
    insert_test_song(data_dir, _SONG_ID, status="ready")
    # _generate_thumbnail calls ffprobe + ffmpeg; patch subprocess.run to no-op.
    with patch("subprocess.run") as mock_run:
      mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
      resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/thumbnail")
    assert resp.status_code != 405

  def test_regenerate_thumbnail_404_when_video_file_missing(
    self, full_mode_client: TestClient
  ) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    # Song is "ready" but video file is absent on disk
    insert_test_song(data_dir, _SONG_ID, status="ready")
    resp = full_mode_client.post(f"/api/songs/{_SONG_ID}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: SERVE mode — write endpoints must return 405
# ---------------------------------------------------------------------------


class TestServeMode:
  """
  In serve mode (SERVE_MODE=1), write/admin endpoints are not registered.
  FastAPI returns 405 Method Not Allowed for HTTP methods on existing path
  patterns and 404 for completely unknown paths.

  For paths that only exist in full mode (no overlapping GET), FastAPI will
  return 404 (unknown route) rather than 405.  We check for "not 200" / "not 2xx"
  to keep assertions robust: the key invariant is that these endpoints are
  not usable in serve mode.
  """

  def _assert_write_blocked(self, response: Any) -> None:
    """Assert the response indicates the write operation is not available."""
    # In serve mode: 404 (route not registered) or 405 (method not allowed
    # on a path that exists with a different method).
    assert response.status_code in (404, 405), (
      f"Expected 404 or 405 in serve mode, got {response.status_code}: {response.text}"
    )

  # -- POST /api/songs -------------------------------------------------------

  def test_post_songs_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(
      "/api/songs",
      json={
        "url": "https://youtube.com/watch?v=xyz",
        "title": "Song",
        "artist": "Artist",
        "duration": 100.0,
        "thumbnail_url": "",
      },
    )
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id} ------------------------------------------------

  def test_delete_song_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}")
    self._assert_write_blocked(resp)

  # -- GET /api/search -------------------------------------------------------

  def test_search_blocked_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.get("/api/search?q=test")
    self._assert_write_blocked(resp)

  # -- GET /api/lyrics/search ------------------------------------------------

  def test_lyrics_search_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get("/api/lyrics/search?q=test")
    self._assert_write_blocked(resp)

  # -- PUT /api/songs/{id}/lyrics --------------------------------------------

  def test_put_lyrics_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics",
      json={"synced_lyrics": None, "plain_lyrics": None, "source": "manual"},
    )
    self._assert_write_blocked(resp)

  # -- PUT /api/songs/{id}/lyrics/adjust -------------------------------------

  def test_put_lyrics_adjust_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.put(
      f"/api/songs/{_SONG_ID}/lyrics/adjust",
      json={"anchor_time": 1.0, "anchor_line_index": 0},
    )
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id}/lyrics -----------------------------------------

  def test_delete_lyrics_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}/lyrics")
    self._assert_write_blocked(resp)

  # -- POST /api/songs/{id}/stems --------------------------------------------

  def test_post_stems_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(f"/api/songs/{_SONG_ID}/stems", json={})
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id}/stems ------------------------------------------

  def test_delete_stems_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}/stems")
    self._assert_write_blocked(resp)

  # -- POST /api/songs/{id}/variants -----------------------------------------

  def test_post_variants_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(f"/api/songs/{_SONG_ID}/variants", json={})
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id}/variants ---------------------------------------

  def test_delete_variants_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}/variants")
    self._assert_write_blocked(resp)

  # -- POST /api/songs/{id}/overlay ------------------------------------------

  def test_post_overlay_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(f"/api/songs/{_SONG_ID}/overlay")
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id}/overlay ----------------------------------------

  def test_delete_overlay_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    # NOTE: DELETE /overlay is an indentation bug — it is dead code and is NOT
    # registered even in full mode.  In serve mode it is likewise absent.
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}/overlay")
    self._assert_write_blocked(resp)

  # -- POST /api/songs/{id}/export -------------------------------------------

  def test_post_export_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(
      f"/api/songs/{_SONG_ID}/export", json={"vocal_level": 0.3}
    )
    self._assert_write_blocked(resp)

  # -- DELETE /api/songs/{id}/export -----------------------------------------

  def test_delete_export_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    # NOTE: DELETE /export is an indentation bug — it is dead code and is NOT
    # registered even in full mode.  In serve mode it is likewise absent.
    resp = serve_mode_client.delete(f"/api/songs/{_SONG_ID}/export")
    self._assert_write_blocked(resp)

  # -- POST /api/songs/{id}/thumbnail ----------------------------------------

  def test_post_thumbnail_blocked_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.post(f"/api/songs/{_SONG_ID}/thumbnail")
    self._assert_write_blocked(resp)

  # -- Confirm read endpoints still work in serve mode -----------------------

  def test_get_songs_still_works_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get("/api/songs")
    assert resp.status_code == 200

  def test_health_still_works_in_serve_mode(
    self, serve_mode_client: TestClient
  ) -> None:
    resp = serve_mode_client.get("/api/health")
    assert resp.status_code == 200
