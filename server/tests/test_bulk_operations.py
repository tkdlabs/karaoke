"""
Tests for bulk regeneration endpoints and helpers.

Covers:
  - ``_bulk_should_skip`` unit logic
  - ``GET /api/bulk/status`` in both modes
  - ``POST /api/bulk/stems`` in full and serve modes
  - ``POST /api/bulk/variants`` in full and serve modes
  - ``POST /api/bulk/cancel`` in full and serve modes
"""

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import insert_test_song


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SONG_A = "bulksong_a"
_SONG_B = "bulksong_b"


def _data_dir_from_client(client: TestClient) -> Path:
  """Return the DATA_DIR Path used by the app loaded inside this client."""
  db_mod = sys.modules.get("db")
  assert db_mod is not None, "db module not loaded — fixture setup failed"
  return Path(db_mod.DB_PATH).parent  # type: ignore[attr-defined]


def _insert_active_bulk(data_dir: Path) -> str:
  """Insert a fake active bulk operation row and return its id."""
  db_path = data_dir / "karaoke.db"
  op_id = str(uuid.uuid4())
  now = datetime.now(timezone.utc).isoformat()
  conn = sqlite3.connect(str(db_path))
  conn.execute(
    """
    INSERT INTO bulk_operations
      (id, operation_type, eq_match, exciter, clear_existing, status, total,
       completed, failed, queue, errors, current_song_id, created_at, updated_at)
    VALUES (?, ?, 0, 0, 0, 'active', 2, 0, 0, '[]', '{}', NULL, ?, ?)
    """,
    (op_id, "stems", now, now),
  )
  conn.commit()
  conn.close()
  return op_id


# ---------------------------------------------------------------------------
# _bulk_should_skip unit tests
# ---------------------------------------------------------------------------


class TestBulkSkipLogic:
  """Unit tests for the ``_bulk_should_skip`` helper."""

  def test_returns_true_when_song_is_none(self, full_mode_client: TestClient) -> None:
    skip = sys.modules["main"]._bulk_should_skip(None, "stems")
    assert skip is True

  def test_returns_true_when_status_not_ready(self, full_mode_client: TestClient) -> None:
    song = {"status": "pending", "stems_status": None, "variants_status": None}
    assert sys.modules["main"]._bulk_should_skip(song, "stems") is True

  def test_returns_true_stems_already_processing(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": "processing"}
    assert sys.modules["main"]._bulk_should_skip(song, "stems") is True

  def test_returns_false_stems_status_none(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": None}
    assert sys.modules["main"]._bulk_should_skip(song, "stems") is False

  def test_returns_false_stems_status_error(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": "error"}
    assert sys.modules["main"]._bulk_should_skip(song, "stems") is False

  def test_returns_true_variants_stems_not_ready(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": None, "variants_status": None}
    assert sys.modules["main"]._bulk_should_skip(song, "variants") is True

  def test_returns_true_variants_already_processing(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": "ready", "variants_status": "processing"}
    assert sys.modules["main"]._bulk_should_skip(song, "variants") is True

  def test_returns_false_variants_eligible(self, full_mode_client: TestClient) -> None:
    song = {"status": "ready", "stems_status": "ready", "variants_status": None}
    assert sys.modules["main"]._bulk_should_skip(song, "variants") is False


# ---------------------------------------------------------------------------
# GET /api/bulk/status
# ---------------------------------------------------------------------------


class TestBulkStatus:
  """Tests for GET /api/bulk/status in both modes."""

  def test_status_inactive_full_mode(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.get("/api/bulk/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is False

  def test_status_inactive_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.get("/api/bulk/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is False


# ---------------------------------------------------------------------------
# POST /api/bulk/stems
# ---------------------------------------------------------------------------


class TestBulkStems:
  """Tests for POST /api/bulk/stems."""

  def test_stems_not_available_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.post("/api/bulk/stems", json={})
    assert resp.status_code == 404

  def test_stems_empty_explicit_ids_returns_400(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.post("/api/bulk/stems", json={"song_ids": []})
    assert resp.status_code == 400
    assert "No eligible" in resp.json()["detail"]

  def test_stems_auto_discover_no_eligible_returns_400(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post("/api/bulk/stems", json={})
    assert resp.status_code == 400

  def test_stems_auto_discover_finds_eligible(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_A, status="ready", extra={"stems_status": None})
    insert_test_song(data_dir, _SONG_B, status="ready", extra={"stems_status": None})

    with patch.object(sys.modules["main"].threading, "Thread") as mock_thread:
      mock_thread.return_value = MagicMock()
      resp = full_mode_client.post("/api/bulk/stems", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["operation_type"] == "stems"
    assert body["total"] == 2
    assert set(body["song_ids"]) == {_SONG_A, _SONG_B}
    mock_thread.assert_called_once()

  def test_stems_409_when_already_active(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    _insert_active_bulk(data_dir)

    insert_test_song(data_dir, _SONG_A, status="ready", extra={"stems_status": None})
    resp = full_mode_client.post("/api/bulk/stems", json={})
    assert resp.status_code == 409
    assert "already running" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/bulk/variants
# ---------------------------------------------------------------------------


class TestBulkVariants:
  """Tests for POST /api/bulk/variants."""

  def test_variants_not_available_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.post("/api/bulk/variants", json={})
    assert resp.status_code == 404

  def test_variants_auto_discover_no_eligible_returns_400(
    self, full_mode_client: TestClient
  ) -> None:
    resp = full_mode_client.post("/api/bulk/variants", json={})
    assert resp.status_code == 400

  def test_variants_auto_discover_finds_eligible(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir, _SONG_A, status="ready",
      extra={"stems_status": "ready", "variants_status": None},
    )
    insert_test_song(
      data_dir, _SONG_B, status="ready",
      extra={"stems_status": "ready", "variants_status": None},
    )

    with patch.object(sys.modules["main"].threading, "Thread") as mock_thread:
      mock_thread.return_value = MagicMock()
      resp = full_mode_client.post("/api/bulk/variants", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["operation_type"] == "variants"
    assert body["total"] == 2
    assert set(body["song_ids"]) == {_SONG_A, _SONG_B}


# ---------------------------------------------------------------------------
# POST /api/bulk/cancel
# ---------------------------------------------------------------------------


class TestBulkCancel:
  """Tests for POST /api/bulk/cancel."""

  def test_cancel_404_when_no_active_operation(self, full_mode_client: TestClient) -> None:
    resp = full_mode_client.post("/api/bulk/cancel")
    assert resp.status_code == 404
    assert "No bulk operation" in resp.json()["detail"]

  def test_cancel_not_available_in_serve_mode(self, serve_mode_client: TestClient) -> None:
    resp = serve_mode_client.post("/api/bulk/cancel")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# clear_existing flag
# ---------------------------------------------------------------------------


class TestBulkClearExisting:
  """Tests for clear_existing flag on bulk endpoints."""

  def test_stems_skips_existing_by_default(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_A, status="ready", extra={"stems_status": "ready"})

    resp = full_mode_client.post("/api/bulk/stems", json={})
    assert resp.status_code == 400
    assert "No eligible" in resp.json()["detail"]

  def test_stems_includes_existing_when_clear(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(data_dir, _SONG_A, status="ready", extra={"stems_status": "ready"})

    with patch.object(sys.modules["main"].threading, "Thread") as mock_thread:
      mock_thread.return_value = MagicMock()
      resp = full_mode_client.post(
        "/api/bulk/stems", json={"clear_existing": True}
      )

    assert resp.status_code == 200
    body = resp.json()
    assert _SONG_A in body["song_ids"]
    assert body["total"] == 1

  def test_variants_skips_existing_by_default(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir, _SONG_A, status="ready",
      extra={"stems_status": "ready", "variants_status": "ready"},
    )

    resp = full_mode_client.post("/api/bulk/variants", json={})
    assert resp.status_code == 400
    assert "No eligible" in resp.json()["detail"]

  def test_variants_includes_existing_when_clear(self, full_mode_client: TestClient) -> None:
    data_dir = _data_dir_from_client(full_mode_client)
    insert_test_song(
      data_dir, _SONG_A, status="ready",
      extra={"stems_status": "ready", "variants_status": "ready"},
    )

    with patch.object(sys.modules["main"].threading, "Thread") as mock_thread:
      mock_thread.return_value = MagicMock()
      resp = full_mode_client.post(
        "/api/bulk/variants", json={"clear_existing": True}
      )

    assert resp.status_code == 200
    body = resp.json()
    assert _SONG_A in body["song_ids"]
    assert body["total"] == 1
