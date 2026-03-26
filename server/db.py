"""SQLite database for karaoke song library."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_default_data_dir = Path(__file__).parent.parent / "data"
DB_PATH = Path(os.environ.get("DATA_DIR", str(_default_data_dir))) / "karaoke.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT,
            duration REAL,
            source_url TEXT NOT NULL,
            video_filename TEXT,
            thumbnail_url TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            lyrics_synced TEXT,
            lyrics_plain TEXT,
            lyrics_source TEXT,
            vocals_filename TEXT,
            instrumental_filename TEXT,
            stems_status TEXT,
            stems_error TEXT,
            export_filename TEXT,
            export_status TEXT,
            export_error TEXT,
            export_vocal_level REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # Migrations for existing databases
    _migrate(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bulk_operations (
            id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            eq_match INTEGER NOT NULL DEFAULT 0,
            exciter INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            total INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            queue TEXT NOT NULL DEFAULT '[]',
            errors TEXT NOT NULL DEFAULT '{}',
            current_song_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that may be missing from older schema versions."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(songs)").fetchall()}
    new_columns = {
        "lyrics_synced": "TEXT",
        "lyrics_plain": "TEXT",
        "lyrics_source": "TEXT",
        "vocals_filename": "TEXT",
        "instrumental_filename": "TEXT",
        "stems_status": "TEXT",
        "stems_error": "TEXT",
        "export_filename": "TEXT",
        "export_status": "TEXT",
        "export_error": "TEXT",
        "export_vocal_level": "REAL",
        "overlay_filename": "TEXT",
        "overlay_lyrics_filename": "TEXT",
        "overlay_romanized_filename": "TEXT",
        "overlay_status": "TEXT",
        "overlay_error": "TEXT",
        "export_progress": "REAL",
        "overlay_progress": "REAL",
        "variants_status": "TEXT",
        "variants_error": "TEXT",
        "variants_progress": "REAL",
    }
    for col, col_type in new_columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE songs ADD COLUMN {col} {col_type}")


def insert_song(song: dict) -> dict:
    now = _now()
    song.setdefault("created_at", now)
    song.setdefault("updated_at", now)
    song.setdefault("status", "pending")

    conn = get_connection()
    cols = ", ".join(song.keys())
    placeholders = ", ".join("?" for _ in song)
    conn.execute(f"INSERT INTO songs ({cols}) VALUES ({placeholders})", list(song.values()))
    conn.commit()

    row = conn.execute("SELECT * FROM songs WHERE id = ?", (song["id"],)).fetchone()
    conn.close()
    return dict(row)


def get_song(song_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_songs() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM songs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_song(song_id: str, **fields) -> dict | None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [song_id]

    conn = get_connection()
    conn.execute(f"UPDATE songs SET {set_clause} WHERE id = ?", values)
    conn.commit()

    row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_song(song_id: str) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_active_bulk() -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM bulk_operations WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_bulk(operation: dict) -> dict:
    now = _now()
    operation.setdefault("created_at", now)
    operation.setdefault("updated_at", now)
    conn = get_connection()
    cols = ", ".join(operation.keys())
    placeholders = ", ".join("?" for _ in operation)
    conn.execute(
        f"INSERT OR REPLACE INTO bulk_operations ({cols}) VALUES ({placeholders})",
        list(operation.values()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM bulk_operations WHERE id = ?", (operation["id"],)
    ).fetchone()
    conn.close()
    return dict(row)


def update_bulk(operation_id: str, **fields) -> dict | None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [operation_id]
    conn = get_connection()
    conn.execute(f"UPDATE bulk_operations SET {set_clause} WHERE id = ?", values)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM bulk_operations WHERE id = ?", (operation_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
