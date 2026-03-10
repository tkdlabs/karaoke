# Bug 01: POST /api/songs and DELETE /api/songs/{id} return 405 Method Not Allowed

## Status
Fixed

## Symptom
In full-mode deploy, adding a song or deleting a song returns HTTP 405 Method Not Allowed.
GET /api/songs still works.

## Root Cause
`add_song` (POST /api/songs) and `delete_song` (DELETE /api/songs/{id}) were accidentally
indented 4 spaces inside the body of `get_song`, making them unreachable dead code after
`return song`. Python treats the indented code as valid (unreachable statements after a
return are syntactically legal), so no error was raised at startup, but the routes were
never registered with FastAPI.

The `if not SERVE_MODE:` guard block that was supposed to wrap them was missing; the two
functions were floating inside `get_song` instead.

## Fix
Extracted `add_song` and `delete_song` from inside `get_song`'s body and wrapped them in
a proper `if not SERVE_MODE:` block at module level (consistent with all other write
routes in the file).

## Affected file
`server/main.py` lines ~128–200
