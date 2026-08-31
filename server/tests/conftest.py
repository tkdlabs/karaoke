"""
Shared fixtures and helpers for karaoke server tests.

Import strategy
---------------
main.py uses module-level ``if not SERVE_MODE:`` guards to conditionally
import external packages (demucs, ytdlp, lrclib, overlay, export) AND to
register FastAPI routes.  Because Python caches modules in ``sys.modules``,
we must isolate each mode in a separate process-level import cycle.

We solve this by using two function-scoped fixtures — ``full_mode_client``
and ``serve_mode_client`` — each of which clears the relevant modules from
``sys.modules``, injects stubs for the missing packages, sets the environment
variable, then imports ``main`` fresh.  The stubs remain in ``sys.modules``
for the lifetime of the test so that tests can configure mock return values on
them.  After the test completes the fixture tears down by purging all server
modules from ``sys.modules``.

DATA_DIR is pointed at a per-test tmp directory so the SQLite database is
isolated between tests.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# External module names that main.py imports only in full mode
# ---------------------------------------------------------------------------

_FULL_MODE_ONLY_MODULES = ("demucs", "export", "overlay", "lrclib", "ytdlp")

# All modules that belong to main.py's import tree and must be reloaded when
# switching modes.
_KARAOKE_SERVER_MODULES = ("main", "db", "models")


def _build_stubs() -> dict:
  """Return a dict of module_name → stub ModuleType for all full-mode deps."""
  stubs: dict = {}

  for name in _FULL_MODE_ONLY_MODULES:
    stubs[name] = types.ModuleType(name)

  return stubs


def _purge_server_modules() -> None:
  """Remove karaoke server + stub modules from sys.modules for a clean reload."""
  for name in list(sys.modules):
    if (
      name in _KARAOKE_SERVER_MODULES
      or name in _FULL_MODE_ONLY_MODULES
      or name.startswith("karaoke_lib")
    ):
      del sys.modules[name]


def _inject_stubs(stubs: dict) -> None:
  """Inject stub modules into sys.modules."""
  for name, stub in stubs.items():
    sys.modules[name] = stub


def _load_app(serve_mode: bool, data_dir: Path, stubs: dict) -> "types.ModuleType":
  """
  Import ``main`` in the requested mode with a temporary DATA_DIR.

  Stubs must already be injected into sys.modules before calling this.
  Returns the freshly-imported main module.
  """
  # Set environment before import — main.py reads these at module level.
  if serve_mode:
    os.environ["SERVE_MODE"] = "1"
  else:
    os.environ.pop("SERVE_MODE", None)

  os.environ["DATA_DIR"] = str(data_dir)

  # Add server directory to path so ``import db`` / ``import main`` resolve.
  server_dir = str(Path(__file__).parent.parent)
  if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

  return importlib.import_module("main")


# ---------------------------------------------------------------------------
# Fixtures for mode-specific TestClient instances
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_mode_client(tmp_path: Path) -> Generator[TestClient, None, None]:
  """
  TestClient for the app loaded in full mode (SERVE_MODE unset).

  The ytdlp, lrclib, demucs, overlay, export stubs are available in
  ``sys.modules`` for the duration of the test.  Tests that need to
  configure mock return values can write directly to the stub attributes::

      ytdlp_mod = sys.modules["ytdlp"]
      ytdlp_mod.search = MagicMock(return_value=[])
  """
  _purge_server_modules()
  stubs = _build_stubs()
  _inject_stubs(stubs)

  data_dir = tmp_path / "data"
  data_dir.mkdir()

  main_mod = _load_app(serve_mode=False, data_dir=data_dir, stubs=stubs)
  # Simulate a machine with yt-dlp installed so download/search tests exercise
  # the happy path; tests that need it absent override this per-test.
  main_mod.HAS_YTDLP = True  # type: ignore[attr-defined]

  with TestClient(main_mod.app, raise_server_exceptions=True) as client:
    yield client

  # Teardown: remove all server/stub modules so the next test gets a clean state.
  _purge_server_modules()
  os.environ.pop("SERVE_MODE", None)


@pytest.fixture()
def serve_mode_client(tmp_path: Path) -> Generator[TestClient, None, None]:
  """TestClient for the app loaded in serve mode (SERVE_MODE=1)."""
  _purge_server_modules()
  stubs = _build_stubs()
  _inject_stubs(stubs)  # harmless; serve mode won't import them

  data_dir = tmp_path / "data"
  data_dir.mkdir()

  main_mod = _load_app(serve_mode=True, data_dir=data_dir, stubs=stubs)
  # Serve mode is the lean deployment; simulate a box without yt-dlp.
  main_mod.HAS_YTDLP = False  # type: ignore[attr-defined]

  with TestClient(main_mod.app, raise_server_exceptions=True) as client:
    yield client

  _purge_server_modules()
  os.environ.pop("SERVE_MODE", None)


# ---------------------------------------------------------------------------
# Helper: insert a minimal song row directly into the test DB
# ---------------------------------------------------------------------------


def insert_test_song(
  data_dir: Path,
  song_id: str = "testsong0001",
  status: str = "ready",
  extra: dict | None = None,
) -> dict:
  """
  Insert a song row into the karaoke.db located at data_dir.

  The DB must already exist (i.e., the TestClient startup event has run).
  Returns the inserted song dict.
  """
  import sqlite3
  from datetime import datetime, timezone

  db_path = data_dir / "karaoke.db"
  now = datetime.now(timezone.utc).isoformat()

  row: dict = {
    "id": song_id,
    "title": "Test Song",
    "artist": "Test Artist",
    "duration": 180.0,
    "source_url": "https://youtube.com/watch?v=test",
    "video_filename": f"{song_id}.mp4",
    "thumbnail_url": None,
    "status": status,
    "error_message": None,
    "lyrics_synced": None,
    "lyrics_plain": None,
    "lyrics_source": None,
    "vocals_filename": None,
    "instrumental_filename": None,
    "stems_status": None,
    "stems_error": None,
    "export_filename": None,
    "export_status": None,
    "export_error": None,
    "export_vocal_level": None,
    "export_progress": None,
    "overlay_lyrics_filename": None,
    "overlay_romanized_filename": None,
    "overlay_status": None,
    "overlay_error": None,
    "overlay_progress": None,
    "variants_status": None,
    "variants_error": None,
    "variants_progress": None,
    "created_at": now,
    "updated_at": now,
  }
  if extra:
    row.update(extra)

  conn = sqlite3.connect(str(db_path))
  conn.row_factory = sqlite3.Row
  cols = ", ".join(row.keys())
  placeholders = ", ".join("?" for _ in row)
  conn.execute(f"INSERT INTO songs ({cols}) VALUES ({placeholders})", list(row.values()))
  conn.commit()
  conn.close()
  return row
