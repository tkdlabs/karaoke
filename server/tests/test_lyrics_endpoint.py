"""Tests for GET /api/songs/{song_id}/lyrics."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import insert_test_song

_SONG_ID = "lyricssong001"
_MISSING_ID = "nosonghere99"

_LRC = (
  "[ti:Test Song]\n"
  "[ar:Test Artist]\n"
  "[00:01.00]Hello world\n"
  "[00:05.50]안녕하세요\n"
  "[00:10.00]Goodbye\n"
)


def _insert_song_with_lyrics(tmp_path: Path, lrc: str | None = _LRC) -> None:
  insert_test_song(
    tmp_path / "data",
    song_id=_SONG_ID,
    extra={"lyrics_synced": lrc},
  )


# ---------------------------------------------------------------------------
# Available in serve mode
# ---------------------------------------------------------------------------


def test_lyrics_endpoint_available_in_serve_mode(serve_mode_client: TestClient, tmp_path: Path) -> None:
  _insert_song_with_lyrics(tmp_path)
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 404 for unknown song
# ---------------------------------------------------------------------------


def test_lyrics_404_unknown_song(serve_mode_client: TestClient) -> None:
  resp = serve_mode_client.get(f"/api/songs/{_MISSING_ID}/lyrics")
  assert resp.status_code == 404


# ---------------------------------------------------------------------------
# No lyrics stored
# ---------------------------------------------------------------------------


def test_lyrics_no_synced_lyrics(serve_mode_client: TestClient, tmp_path: Path) -> None:
  insert_test_song(tmp_path / "data", song_id=_SONG_ID)  # lyrics_synced=None
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  assert resp.status_code == 200
  body = resp.json()
  assert body["has_lyrics"] is False
  assert body["lines"] == []


# ---------------------------------------------------------------------------
# Parsed LRC lines
# ---------------------------------------------------------------------------


def test_lyrics_parsed_lines(serve_mode_client: TestClient, tmp_path: Path) -> None:
  _insert_song_with_lyrics(tmp_path)
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  assert resp.status_code == 200
  body = resp.json()
  assert body["has_lyrics"] is True
  assert body["song_id"] == _SONG_ID

  lines = body["lines"]
  assert len(lines) == 3

  assert lines[0]["time_ms"] == 1_000
  assert lines[0]["text"] == "Hello world"
  assert lines[0]["romanized"] is None

  assert lines[1]["time_ms"] == 5_500
  assert lines[1]["text"] == "안녕하세요"

  assert lines[2]["time_ms"] == 10_000
  assert lines[2]["text"] == "Goodbye"


def test_lyrics_metadata_tags_skipped(serve_mode_client: TestClient, tmp_path: Path) -> None:
  _insert_song_with_lyrics(tmp_path)
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  texts = [l["text"] for l in resp.json()["lines"]]
  assert not any("Test Song" in t or "Test Artist" in t for t in texts)


def test_lyrics_sorted_by_time(serve_mode_client: TestClient, tmp_path: Path) -> None:
  lrc = "[00:10.00]Third\n[00:01.00]First\n[00:05.00]Second\n"
  insert_test_song(tmp_path / "data", song_id=_SONG_ID, extra={"lyrics_synced": lrc})
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  times = [l["time_ms"] for l in resp.json()["lines"]]
  assert times == sorted(times)


# ---------------------------------------------------------------------------
# Romanization
# ---------------------------------------------------------------------------


def test_lyrics_romanize_korean(serve_mode_client: TestClient, tmp_path: Path) -> None:
  _insert_song_with_lyrics(tmp_path)

  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics?romanize=true")
  assert resp.status_code == 200
  lines = resp.json()["lines"]

  korean_line = next(l for l in lines if l["text"] == "안녕하세요")
  assert korean_line["romanized"] is not None

  latin_line = next(l for l in lines if l["text"] == "Hello world")
  assert latin_line["romanized"] is None


def test_lyrics_romanize_false_by_default(serve_mode_client: TestClient, tmp_path: Path) -> None:
  _insert_song_with_lyrics(tmp_path)
  resp = serve_mode_client.get(f"/api/songs/{_SONG_ID}/lyrics")
  lines = resp.json()["lines"]
  assert all(l["romanized"] is None for l in lines)
