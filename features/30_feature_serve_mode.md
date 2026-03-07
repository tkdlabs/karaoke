# Feature: Serve Mode (SERVE_MODE env var)

Implement the serve mode design from `designs/serve_mode.md`.

## What to do

Add a `SERVE_MODE` env var to `server/main.py` that, when set to `"1"`, starts
a read-only serving backend with no heavy dependencies and no mutation endpoints.

### Changes to `server/main.py`

1. Read the flag near the top:
   ```python
   SERVE_MODE = os.environ.get("SERVE_MODE", "").lower() in ("1", "true", "yes")
   ```

2. Gate heavy imports — only import when NOT in serve mode:
   ```python
   if not SERVE_MODE:
       import demucs
       import export as export_mod
       import overlay as overlay_mod
       import lrclib
       import ytdlp
   ```

3. Gate the startup recovery loop (no workers run in serve mode):
   ```python
   @app.on_event("startup")
   def startup():
       db.init_db()
       # ... mkdir calls stay ...
       if not SERVE_MODE:
           # reset stuck processing statuses
           ...
   ```

4. Wrap all admin routes in `if not SERVE_MODE:` blocks:
   - `GET /api/search`
   - `POST /api/songs`
   - `DELETE /api/songs/{id}`
   - `GET /api/lyrics/search`
   - `PUT /api/songs/{id}/lyrics`
   - `PUT /api/songs/{id}/lyrics/adjust`
   - `DELETE /api/songs/{id}/lyrics`
   - `POST /api/songs/{id}/stems`
   - `DELETE /api/songs/{id}/stems`
   - `POST /api/songs/{id}/variants`
   - `DELETE /api/songs/{id}/variants`
   - `POST /api/songs/{id}/overlay`
   - `DELETE /api/songs/{id}/overlay`
   - `POST /api/songs/{id}/export`
   - `DELETE /api/songs/{id}/export`
   - `POST /api/songs/{id}/thumbnail`

   Keep all GET streaming/read endpoints unconditional.

5. Log serve mode on startup:
   ```python
   if SERVE_MODE:
       print("Running in SERVE_MODE — admin endpoints disabled")
   ```

## Acceptance criteria

- `SERVE_MODE=1 python main.py` starts without importing torch/demucs/yt-dlp
- All GET serving endpoints respond normally
- All admin POST/PUT/DELETE endpoints return 404 in serve mode
- Normal mode (no env var) is completely unchanged
