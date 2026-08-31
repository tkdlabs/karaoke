# Feature: Manual video import (no YouTube / yt-dlp)

## Summary
Add a non-yt-dlp path to get a song into the library: upload a local video file (or fetch from a
direct MP4 URL). This makes the app fully usable to process, play, and export a user's own files
without ever touching YouTube — the legal/compliance core needed for public release.

## Motivation
Releasing on GitHub while bundling YouTube download is a legal liability (yt-dlp lives under
recurring RIAA/DMCA pressure; downloading violates YouTube ToS regardless). The player, variants,
lyrics, overlay, and export pipelines already operate on a local `videos/{id}.mp4`, so a manual
import makes the whole app functional with zero YouTube involvement.

## Design
- New endpoint `POST /api/songs/import` (multipart): fields `file` (required) and optional
  `title` / `artist`.
- New `_import_worker`: copy (stream) the upload into `videos/{song_id}.mp4`, ffprobe duration,
  then reuse the existing thumbnail-regeneration helper. Default title/artist from filename or
  file metadata tags (mp4/ID3); source_url set to the original filename.
- Song created with `status = "downloading"`, transitions to `"ready"` exactly like the current
  worker, so every downstream pipeline (stems/variants/overlay/export) works unchanged.
- Optional extension: paste a direct `https://…mp4` URL → fetch with stdlib `urllib` (no yt-dlp).
  Keep out of scope for v1 if unclear.
- UI: "Import video" button in the song library header → native file picker → `FormData` upload.
  Show normal "adding" progress row.
- No changes to the yt-dlp-based `POST /api/songs` path.

## Scope
- `server/main.py`: import endpoint + `_import_worker` + thumbnail reuse
- `server/demucs.py` / models: none (song shape unchanged)
- `lib/api.ts` + `components/SongLibrary.tsx`: import button + upload fetch
- No changes to variants, export, player, overlay, or search

## Acceptance Criteria
- [ ] `POST /api/songs/import` accepts a multipart video and creates a `ready` song
- [ ] Imported song plays and runs stems / variants / overlay / export identical to a downloaded one
- [ ] Duration and thumbnail populated from the uploaded file
- [ ] "Import video" visible in the library even when yt-dlp is absent (feature 39)
- [ ] Existing yt-dlp download path unchanged