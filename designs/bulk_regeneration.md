# Bulk Regeneration

## Problem

After EQ/exciter improvements, users need to regenerate stems and variants for many songs at once. Currently every operation is per-song (one API call, one background thread). Manually clicking through 30+ songs is tedious, and the system has a single AI GPU for voice separation that must be serialized.

---

## API Design

All bulk endpoints go on `write_router` (excluded in SERVE_MODE).

### Endpoints

#### `POST /api/bulk/stems`

Regenerate stems (Demucs separation) for multiple songs. Stems auto-trigger variant generation after completion (existing `_stems_worker` behavior).

**Request body** — `BulkStemsRequest`:

```python
class BulkStemsRequest(BaseModel):
  song_ids: list[str] | None = None  # None = auto-discover
  eq_match: bool = False
  exciter: bool = False
```

- `song_ids=None` → auto-discover: all songs where `status="ready"` AND (`stems_status` is null OR `stems_status="error"`)
- `song_ids=[...]` → explicit list; server validates each exists and has `status="ready"`

**Response** — `BulkOperationResponse`:

```python
class BulkOperationResponse(BaseModel):
  operation_id: str       # UUID for tracking
  operation_type: str     # "stems" | "variants"
  total: int              # songs queued
  song_ids: list[str]     # ordered queue
```

**Errors**:
- `409` if a bulk operation is already running
- `400` if no eligible songs found (auto-discover) or all specified songs are ineligible

#### `POST /api/bulk/variants`

Regenerate variants only for multiple songs that already have stems.

**Request body** — `BulkVariantsRequest`:

```python
class BulkVariantsRequest(BaseModel):
  song_ids: list[str] | None = None  # None = auto-discover
  eq_match: bool = False
  exciter: bool = False
```

- `song_ids=None` → auto-discover: all songs where `stems_status="ready"` AND (`variants_status` is null OR `variants_status="error"`)
- `song_ids=[...]` → explicit list; server validates each has `stems_status="ready"`

**Response** — same `BulkOperationResponse`.

#### `GET /api/bulk/status`

Poll current bulk operation progress.

**Response** — `BulkStatusResponse`:

```python
class BulkStatusResponse(BaseModel):
  active: bool
  operation_id: str | None = None
  operation_type: str | None = None   # "stems" | "variants"
  status: str | None = None           # "active" | "completed" | "cancelled"
  total: int = 0
  completed: int = 0
  failed: int = 0
  current_song_id: str | None = None
  current_song_title: str | None = None
  queue: list[str] = []               # remaining song IDs
  errors: dict[str, str] = {}         # song_id → error message
```

This endpoint goes on `app` (not `write_router`) so the frontend can poll status even if we later want read-only status visibility. Reads from `bulk_operations` table.

#### `POST /api/bulk/cancel`

Cancel the current bulk operation. The currently-processing song finishes (we don't interrupt ffmpeg/demucs mid-run), but no further songs are started.

**Response**:

```python
{"status": "cancelled", "completed": 5, "remaining": 12}
```

Returns `404` if no bulk operation is active.

---

## Backend Implementation

### Persistence: `bulk_operations` table

Bulk operation state is persisted to SQLite so operations survive server restarts. Add to `db.py`:

```python
# In init_db():
conn.execute("""
  CREATE TABLE IF NOT EXISTS bulk_operations (
    id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,   -- "stems" | "variants"
    eq_match INTEGER NOT NULL DEFAULT 0,
    exciter INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',  -- "active" | "completed" | "cancelled"
    total INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    queue TEXT NOT NULL DEFAULT '[]',       -- JSON array of remaining song IDs
    errors TEXT NOT NULL DEFAULT '{}',      -- JSON dict of song_id → error
    current_song_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )
""")
```

DB helper functions follow the existing `db.py` patterns (plain SQL, `get_connection()`, `_now()`):

```python
def get_active_bulk() -> dict | None
def upsert_bulk(operation: dict) -> dict
def update_bulk(operation_id: str, **fields) -> dict | None
```

The `queue` and `errors` fields are stored as JSON strings, serialized/deserialized in the helpers.

### In-memory runtime state

A lightweight module-level dict holds only the runtime coordination (cancel flag + lock). This is NOT the source of truth — the DB is:

```python
_bulk_runtime: dict = {
  "cancel_requested": False,
  "lock": threading.Lock(),
}
```

The `lock` protects the cancel flag and serializes DB updates from the bulk worker thread vs API request threads.

### Worker: `_bulk_worker`

A single `threading.Thread(daemon=True)` processes songs sequentially. Progress is persisted to DB after each song so the operation can resume on restart:

```python
def _bulk_worker(operation_id: str) -> None:
  """Process songs from the bulk queue sequentially. Reads queue from DB."""
  op = db.get_bulk(operation_id)
  operation_type = op["operation_type"]
  eq_match = bool(op["eq_match"])
  exciter = bool(op["exciter"])
  queue = json.loads(op["queue"])
  errors = json.loads(op["errors"])

  for song_id in list(queue):
    with _bulk_runtime["lock"]:
      if _bulk_runtime["cancel_requested"]:
        db.update_bulk(operation_id, status="cancelled")
        log.info(f"Bulk {operation_type} cancelled, {len(queue)} remaining")
        break

    # Update current song in DB
    db.update_bulk(operation_id, current_song_id=song_id)

    song = db.get_song(song_id)

    if _should_skip(song, operation_type):
      queue.remove(song_id)
      db.update_bulk(operation_id,
        completed=op["completed"] + 1,  # re-read below
        queue=json.dumps(queue))
      op = db.get_bulk(operation_id)  # refresh
      continue

    try:
      if operation_type == "stems":
        _run_single_stems(song_id, song, eq_match, exciter)
      else:
        _run_single_variants(song_id, song, eq_match, exciter)

      queue.remove(song_id)
      op = db.get_bulk(operation_id)
      db.update_bulk(operation_id,
        completed=op["completed"] + 1,
        queue=json.dumps(queue))
      op = db.get_bulk(operation_id)
    except Exception as e:
      queue.remove(song_id)
      errors[song_id] = str(e)[:200]
      op = db.get_bulk(operation_id)
      db.update_bulk(operation_id,
        failed=op["failed"] + 1,
        queue=json.dumps(queue),
        errors=json.dumps(errors))
      op = db.get_bulk(operation_id)
      log.error(f"Bulk {operation_type} failed for {song_id}: {e}")

  # Mark completed if not cancelled
  final = db.get_bulk(operation_id)
  if final and final["status"] == "active":
    db.update_bulk(operation_id, status="completed", current_song_id=None)
  else:
    db.update_bulk(operation_id, current_song_id=None)

  log.info(f"Bulk {operation_type} finished: {final['completed']}/{final['total']}")
```

### `_run_single_stems` / `_run_single_variants`

These extract the setup logic from the existing `start_stems` / `start_variants` endpoint handlers and call the existing `_stems_worker` / `_variants_worker` **synchronously** (not in a new thread — the bulk worker thread IS the thread). This reuses all existing Demucs, ffmpeg, EQ, and progress logic unchanged.

```python
def _run_single_stems(song_id, song, eq_match, exciter):
  vocals_filename = f"{song_id}_vocals.mp3"
  instrumental_filename = f"{song_id}_instrumental.mp3"
  db.update_song(song_id,
    vocals_filename=vocals_filename,
    instrumental_filename=instrumental_filename,
    stems_status="processing", stems_error=None)

  video_path = VIDEOS_DIR / song["video_filename"]
  # Call synchronously — reuses existing worker
  _stems_worker(
    song_id, video_path,
    AUDIO_DIR / vocals_filename,
    AUDIO_DIR / instrumental_filename,
    eq_match, exciter,
  )
```

`_stems_worker` already auto-triggers `_variants_worker` on success, so bulk stems gets stems+variants per song for free.

### Skip logic

```python
def _should_skip(song, operation_type):
  if not song:
    return True
  if song["status"] != "ready":
    return True
  if operation_type == "stems":
    return song.get("stems_status") == "processing"
  else:  # variants
    if song.get("stems_status") != "ready":
      return True
    return song.get("variants_status") == "processing"
```

### Preventing conflicts

- Only one bulk operation at a time — check `db.get_active_bulk()` before starting, return `409` if one exists with `status="active"`.
- Individual per-song endpoints continue to work. If a user triggers stems on a single song while bulk is running on a different song, both proceed independently (different threads, different songs). The bulk worker skips any song whose status is already `processing`.

### Startup: auto-resume

Add to the existing `startup()` function:

```python
# Reset cancel flag
with _bulk_runtime["lock"]:
  _bulk_runtime["cancel_requested"] = False

# Check for an active bulk operation to resume
active_bulk = db.get_active_bulk()
if active_bulk:
  remaining = json.loads(active_bulk["queue"])
  if remaining:
    # Reset the song that was mid-processing (already handled by existing stuck-status reset above)
    log.info(f"Resuming bulk {active_bulk['operation_type']}: {len(remaining)} songs remaining")
    thread = threading.Thread(
      target=_bulk_worker,
      args=(active_bulk["id"],),
      daemon=True,
    )
    thread.start()
  else:
    # Queue was empty — mark as completed
    db.update_bulk(active_bulk["id"], status="completed", current_song_id=None)
```

The existing stuck-status reset logic (already in `startup()`) handles the song that was mid-processing when the server died — it gets set to `stems_status="error"` or `variants_status="error"`. On resume, the bulk worker re-reads the queue from DB and re-attempts that song (since its status is now "error", not "processing", so `_should_skip` won't skip it).

---

## Frontend Integration

### API client (`lib/api.ts`)

```typescript
export interface BulkRequest {
  song_ids?: string[];
  eq_match: boolean;
  exciter: boolean;
}

export interface BulkOperationResponse {
  operation_id: string;
  operation_type: string;
  total: number;
  song_ids: string[];
}

export interface BulkStatus {
  active: boolean;
  operation_id: string | null;
  operation_type: string | null;
  total: number;
  completed: number;
  failed: number;
  current_song_id: string | null;
  current_song_title: string | null;
  queue: string[];
  errors: Record<string, string>;
}

export async function startBulkStems(req: BulkRequest): Promise<BulkOperationResponse> {
  return fetchApi("/api/bulk/stems", { method: "POST", body: JSON.stringify(req) });
}

export async function startBulkVariants(req: BulkRequest): Promise<BulkOperationResponse> {
  return fetchApi("/api/bulk/variants", { method: "POST", body: JSON.stringify(req) });
}

export async function getBulkStatus(): Promise<BulkStatus> {
  return fetchApi("/api/bulk/status");
}

export async function cancelBulk(): Promise<void> {
  await fetchApi("/api/bulk/cancel", { method: "POST" });
}
```

### UI location

Add a **"Bulk Operations"** section to the top of `SongLibrary.tsx`, above the song grid. This keeps it visible without cluttering individual song cards.

```
┌─────────────────────────────────────────────────────────────┐
│ Bulk Operations                                             │
│                                                             │
│  [Regen All Stems ▸]  [Regen All Variants ▸]               │
│  ☑ EQ Match   ☑ Exciter                                    │
│                                                             │
│  ── when active: ──────────────────────────────────────────│
│  Processing 5/23 — "Song Title" (stems)                     │
│  ████████░░░░░░░░░░░░ 22%        [Cancel]                   │
│  1 failed                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Behavior**:
- Buttons disabled when a bulk operation is already active
- EQ/Exciter checkboxes match the existing per-song options
- Auto-discovery by default (no song IDs sent). Explicit song selection out of scope for v1
- Poll `/api/bulk/status` every 3 seconds while active (same interval as existing song polling)
- Show completion toast when done, with error count if any failed

### Progress display

- Aggregate progress bar: `completed / total`
- Current song title shown so user knows what's happening
- Failed count shown in red; expandable to show per-song error messages
- Individual song cards continue to show their own `stems_status` / `variants_status` via existing 3-second polling — no changes needed

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Song deleted mid-bulk | `_should_skip` returns True (song not found), counted as completed, continue to next |
| Server restart mid-bulk | Bulk state persisted in DB. On startup, server detects `status="active"` row, resumes from remaining queue. The interrupted song is reset to "error" by existing stuck-status logic and re-attempted. |
| Individual operation started on a song in the bulk queue | Bulk worker checks status before processing; if already `processing`, skips that song |
| All songs already have stems/variants | Auto-discover finds 0 eligible songs → `400` response |
| Empty library | Same — 0 eligible → `400` |
| Cancel during Demucs (long-running) | Current song finishes completely before worker checks cancel flag. This is intentional — partial stems are worse than complete ones. |
| Bulk stems where some songs already have stems | Those songs get re-processed (stems overwritten). The endpoint is "regenerate", not "generate missing". Auto-discover only finds songs without stems. |
| Network timeout on long bulk | Client polls status independently; the backend worker is fire-and-forget. Reconnecting shows current progress. |

---

## Not In Scope (v1)

- **Selective song picking UI** (checkboxes on individual songs) — auto-discover covers the main use case
- **Parallel processing** — single GPU constraint means sequential is correct
- **Persistent operation history** — only the most recent operation is tracked; could add history query later
- **Bulk overlay / bulk export** — can be added later following the same pattern
- **WebSocket push** — polling at 3s is consistent with existing architecture
