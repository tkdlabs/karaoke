# Feature: Iterative Demucs Deep Clean Mode

## Summary
Add a "Deep clean" option that runs Demucs twice on the extracted vocals to recover instrumental content that leaked into the vocal track, improving instrumental quality.

## Motivation
Demucs sometimes pulls instrumental content into the vocal track, degrading the reconstructed instrumental. EQ match and exciter compensate spectrally but cannot recover missing audio content. A second Demucs pass on the vocals can extract and return that leaked content.

## Design
See `designs/iterative_demucs.md`

## Scope
- New `separate_iterative()` function in `demucs.py`
- `deep_clean` flag threaded through models, API, DB, endpoints, workers
- Per-song and bulk "Deep clean" checkbox in UI
- No changes to variants, export, player, or overlay pipelines

## Acceptance Criteria
- [ ] Deep clean checkbox visible per-song and in bulk bar
- [ ] When enabled, stems separation runs 2-pass Demucs and merges recovered stems
- [ ] Output files are same filenames as normal mode
- [ ] Works with bulk regeneration (stems and variants)
- [ ] All existing tests pass + new tests for deep_clean flag
