# Feature 32: Replace scattered `if not SERVE_MODE:` guards with FastAPI router

## Problem
`server/main.py` uses repeated `if not SERVE_MODE:` blocks scattered throughout the file
to conditionally register ~20 routes. This pattern is fragile:

- Easy to accidentally mis-indent a route into the wrong scope (see bug 01).
- The conditional logic is invisible in the route list — you have to read every block to
  know which routes are active in which mode.
- Adding a new route requires remembering to wrap it in the guard.

## Proposed Solution
Use a FastAPI `APIRouter` for the full-mode-only routes:

```python
from fastapi import APIRouter

write_router = APIRouter()

@write_router.post("/api/songs", response_model=Song, status_code=201)
def add_song(...): ...

@write_router.delete("/api/songs/{song_id}")
def delete_song(...): ...

# ... all other non-SERVE_MODE routes ...

if not SERVE_MODE:
    app.include_router(write_router)
```

## Benefits
- Single `if not SERVE_MODE:` guard at the bottom of the file, not scattered everywhere.
- Routes are always syntactically registered to the router (no dead-code risk).
- Clear separation between always-on routes (health, list, get, serve audio/video) and
  write routes (add, delete, stems, variants, overlay, export, lyrics, thumbnail).

## Scope
- Refactor `server/main.py` only.
- No API contract changes.
- Two routers: `read_router` (or keep at app level) and `write_router` (guarded).
