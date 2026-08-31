"""
Tests for Korean lyrics romanization guard in POST /api/songs/{id}/overlay.

Regression: when korean_romanizer is not installed, the server was silently
treating Korean lyrics as non-Korean (HAS_KOREAN_ROMANIZER=False caused
romanize_korean() to return None for every line, so _lyrics_need_romanization()
always returned False). Both overlay files were rendered without romanization
and the user had no feedback about the problem.

Fix: start_overlay() checks upfront whether Korean is present but the library
is missing, and returns HTTP 422 immediately with an actionable error message.
"""

import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import insert_test_song

KOREAN_LRC = "[00:01.00]안녕하세요\n[00:05.00]반갑습니다\n"
LATIN_LRC = "[00:01.00]Hello world\n[00:05.00]Goodbye world\n"


def _configure_lyrics(has_romanizer: bool) -> None:
  """Set karaoke_lib.lyrics.HAS_KOREAN_ROMANIZER for the current import cycle.

  Imported inside the fixture (not at module level) so it reflects the
  freshly-imported module created by conftest's purge/reload per test.
  """
  import karaoke_lib.lyrics

  karaoke_lib.lyrics.HAS_KOREAN_ROMANIZER = has_romanizer


@pytest.fixture()
def overlay_client_no_romanizer(full_mode_client: TestClient):
  """full_mode_client with HAS_KOREAN_ROMANIZER=False (library not installed)."""
  _configure_lyrics(has_romanizer=False)
  yield full_mode_client


@pytest.fixture()
def overlay_client_with_romanizer(full_mode_client: TestClient):
  """full_mode_client with HAS_KOREAN_ROMANIZER=True (library installed)."""
  _configure_lyrics(has_romanizer=True)
  sys.modules["overlay"].create_overlay = MagicMock()
  yield full_mode_client


# ---------------------------------------------------------------------------
# Regression tests: Korean lyrics without romanizer → 422 at request time
# ---------------------------------------------------------------------------


def test_korean_lyrics_without_romanizer_returns_422(
  overlay_client_no_romanizer: TestClient, tmp_path
):
  """POST /overlay with Korean lyrics must fail fast with 422 when romanizer is missing."""
  insert_test_song(
    tmp_path / "data",
    song_id="kor00000001",
    status="ready",
    extra={"lyrics_synced": KOREAN_LRC},
  )
  resp = overlay_client_no_romanizer.post("/api/songs/kor00000001/overlay")
  assert resp.status_code == 422
  assert "korean_romanizer" in resp.json()["detail"].lower()


def test_422_detail_is_actionable(overlay_client_no_romanizer: TestClient, tmp_path):
  """The 422 error message must include an install hint."""
  insert_test_song(
    tmp_path / "data",
    song_id="kor00000002",
    status="ready",
    extra={"lyrics_synced": KOREAN_LRC},
  )
  resp = overlay_client_no_romanizer.post("/api/songs/kor00000002/overlay")
  assert "pip install korean_romanizer" in resp.json()["detail"]


def test_latin_lyrics_without_romanizer_proceeds(
  overlay_client_no_romanizer: TestClient, tmp_path
):
  """Non-Korean lyrics must start rendering even when romanizer is absent."""
  sys.modules["overlay"].create_overlay = MagicMock()
  insert_test_song(
    tmp_path / "data",
    song_id="lat00000001",
    status="ready",
    extra={"lyrics_synced": LATIN_LRC},
  )
  resp = overlay_client_no_romanizer.post("/api/songs/lat00000001/overlay")
  assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Happy path: Korean lyrics with romanizer installed → overlay starts
# ---------------------------------------------------------------------------


def test_korean_lyrics_with_romanizer_proceeds(
  overlay_client_with_romanizer: TestClient, tmp_path
):
  """Korean lyrics must start rendering when korean_romanizer is installed."""
  insert_test_song(
    tmp_path / "data",
    song_id="kor00000003",
    status="ready",
    extra={"lyrics_synced": KOREAN_LRC},
  )
  resp = overlay_client_with_romanizer.post("/api/songs/kor00000003/overlay")
  assert resp.status_code == 200
  assert resp.json()["overlay_status"] == "processing"
