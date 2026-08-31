# Feature: Make yt-dlp an optional runtime dependency

## Summary
Turn yt-dlp from a hard pip requirement into an optional, runtime-detected external tool. When it
is absent, search and YouTube download are hidden/degraded gracefully and the app still works via
manual import (feature 38).

## Motivation
yt-dlp is the main legal-risk surface for a public release. It is already invoked only as an
external `yt-dlp` subprocess (`server/ytdlp.py`), so making it optional is purely a matter of
detection and graceful degradation — no code paths need yt-dlp installed to run the player,
variants, lyrics, overlay, or export.

## Design
- Startup probe: if `shutil.which("yt-dlp")` is falsy, set a module-level `HAS_YTDLP = False`
  (keep the existing `YTDLP_CHANNEL` installer for admins who want it).
- New `GET /api/capabilities` returning `{"ytdlp": true|false}` (also add to `GET /api/health`).
- `/api/search` and the download worker return a clear `409`/HTTPException with
  "yt-dlp is not installed — use manual import" when `HAS_YTDLP` is false.
- Remove `yt-dlp` from `server/requirements.txt`; add `requirements-ytdlp.txt` (documented) or
  leave installation to the existing `YTDLP_CHANNEL` mechanism.
- Frontend: on mount, fetch `/api/capabilities`; hide the YouTube search bar and search-result
  cards when unavailable; surface the manual import button instead (feature 38).
- README: "yt-dlp optional → enables YouTube search/download; requires manual import otherwise."

## Scope
- `server/main.py`: capability probe + endpoint + guard branches in search/add
- `server/ytdlp.py`: none (already subprocess-based)
- `lib/api.ts` + `components/SongLibrary.tsx` + `components/SearchResults.tsx`: conditional UI
- `requirements*.txt` split
- No changes to variants, export, player, or overlay

## Acceptance Criteria
- [ ] App boots and all local features work with no `yt-dlp` on PATH
- [ ] `/api/capabilities` and `/api/health` report `ytdlp: false` correctly
- [ ] Search returns a clear error and is not shown in the UI when yt-dlp is missing
- [ ] Imported songs (feature 38) run the full pipeline without yt-dlp
- [ ] With yt-dlp present, search + download behave exactly as before