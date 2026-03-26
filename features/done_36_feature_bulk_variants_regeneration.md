# Bulk Variants Regeneration

## Summary

Add `POST /api/bulk/variants` endpoint that regenerates audio variants (pitch × vocal level) for multiple songs that already have stems separated. Supports auto-discovery of songs needing variants, or explicit song ID list. Shares infrastructure with bulk stems (same worker, status, cancel).

## Design

See [designs/bulk_regeneration.md](../designs/bulk_regeneration.md)

## Scope

### Backend
- Add `BulkVariantsRequest` model to `models.py`
- Add `POST /api/bulk/variants` endpoint on `write_router`
- Add `_run_single_variants` helper (calls `_variants_worker` synchronously)
- Reuses `_bulk_worker`, `bulk_operations` table, status/cancel endpoints from feature 35

### Frontend
- Add `startBulkVariants` to `lib/api.ts`
- Add "Regen All Variants" button to bulk operations bar (alongside stems button)
