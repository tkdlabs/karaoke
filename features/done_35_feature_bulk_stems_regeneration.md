# Bulk Stems Regeneration

## Summary

Add `POST /api/bulk/stems` endpoint that regenerates stems (Demucs separation + auto-triggered variants) for multiple songs sequentially. Supports auto-discovery of songs needing stems, or explicit song ID list.

## Design

See [designs/bulk_regeneration.md](../designs/bulk_regeneration.md)

## Scope

### Backend
- Add `bulk_operations` table to `db.py` with helpers (`get_active_bulk`, `upsert_bulk`, `update_bulk`)
- Add `BulkStemsRequest` and `BulkOperationResponse` models to `models.py`
- Add `POST /api/bulk/stems` endpoint on `write_router`
- Add `_bulk_worker` background thread (sequential processing)
- Add `_run_single_stems` helper (calls `_stems_worker` synchronously)
- Add auto-resume on startup
- Add `GET /api/bulk/status` endpoint (on `app`, not `write_router`)
- Add `POST /api/bulk/cancel` endpoint on `write_router`

### Frontend
- Add `startBulkStems`, `getBulkStatus`, `cancelBulk` to `lib/api.ts`
- Add "Bulk Operations" bar to top of `SongLibrary.tsx` with progress, cancel, EQ/Exciter toggles
