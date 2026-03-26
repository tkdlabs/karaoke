# Iterative Demucs ("Deep Clean" Mode)

## Problem

Demucs (`htdemucs`) stem separation sometimes leaks instrumental content into the vocal track. While the vocals sound acceptably clean, the instrumental suffers because the leaked content is *missing* from `bass.mp3`, `drums.mp3`, and `other.mp3`. The existing EQ match and exciter post-processing try to compensate spectrally, but they cannot recover content that was physically removed — they boost frequencies, not reconstruct missing audio.

The pain point is **instrumental quality** specifically. Vocal bleed into instrumentals is not a concern.

## Proposed Approach

Run Demucs twice. The second pass processes the (impure) vocals from pass 1, extracting any instrumental content that leaked in. The recovered instrumental fragments are summed back into the pass-1 instrumentals.

### Pipeline

```
Pass 1: original_mix.wav → Demucs htdemucs
  → vocals1.mp3, drums1.mp3, bass1.mp3, other1.mp3

Pass 2: vocals1.mp3 → Demucs htdemucs
  → vocals2.mp3, drums2.mp3, bass2.mp3, other2.mp3

Final stems:
  vocals_final      = vocals2
  instrumental_final = mix(drums1 + drums2, bass1 + bass2, other1 + other2)
```

### Mixing Recovered Stems

The critical step is combining pass-1 and pass-2 instrumental stems without phase issues.

**Approach: ffmpeg amix with normalize=0** (matches existing `combine_instrumental` in `demucs.py`)

```python
# For each instrument type, sum pass-1 and pass-2 stems:
#   drums_combined = drums1 + drums2
#   bass_combined  = bass1 + bass2
#   other_combined = other1 + other2
# Then combine all three into final instrumental (same as current pipeline).

# Per-instrument summing (3 calls):
ffmpeg -y -i drums1.mp3 -i drums2.mp3 \
  -filter_complex "amix=inputs=2:duration=longest:normalize=0" \
  drums_combined.mp3

# Final instrumental (same as existing combine_instrumental):
ffmpeg -y -i drums_combined.mp3 -i bass_combined.mp3 -i other_combined.mp3 \
  -filter_complex "amix=inputs=3:duration=longest:normalize=0" \
  instrumental_final.mp3
```

**Why amix with normalize=0?**
- `normalize=0` preserves original amplitude — no automatic gain scaling
- This is what `combine_instrumental` already uses, so behavior is consistent
- Phase cancellation risk is low: pass-2 stems come from a different source (vocals1, not the original mix), so they are additive content, not duplicated waveforms

**Alternative considered — numpy direct sum:** Would give precise sample-level control but adds complexity (decode to PCM, align sample counts, sum, re-encode). Not worth it since ffmpeg amix already works correctly and is proven in the codebase.

## Changes Required

### 1. `server/demucs.py` — New `separate_iterative()` function

Add a new function alongside the existing `separate()`:

```python
def separate_iterative(
  video_path: Path,
  vocals_out: Path,
  instrumental_out: Path,
) -> None:
  """Two-pass Demucs: extract leaked instrumental from vocals, merge back."""
  vocals_out.parent.mkdir(parents=True, exist_ok=True)
  instrumental_out.parent.mkdir(parents=True, exist_ok=True)

  with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)

    # --- Pass 1: original mix ---
    wav_path = tmp_path / "audio.wav"
    extract_audio(video_path, wav_path)
    stems1_dir = run_demucs(wav_path, tmp_path / "pass1")

    # --- Pass 2: re-separate vocals from pass 1 ---
    vocals1 = stems1_dir / "vocals.mp3"
    if not vocals1.exists():
      raise FileNotFoundError(f"Pass 1 vocals not found at {vocals1}")
    stems2_dir = run_demucs(vocals1, tmp_path / "pass2")

    # --- Combine per-instrument stems (pass1 + pass2) ---
    for stem_name in ("drums", "bass", "other"):
      s1 = stems1_dir / f"{stem_name}.mp3"
      s2 = stems2_dir / f"{stem_name}.mp3"
      combined = tmp_path / f"{stem_name}_combined.mp3"
      _sum_stems(s1, s2, combined)

    # --- Final vocals = pass 2 vocals ---
    vocals2 = stems2_dir / "vocals.mp3"
    if not vocals2.exists():
      raise FileNotFoundError(f"Pass 2 vocals not found at {vocals2}")
    shutil.copy2(vocals2, vocals_out)

    # --- Final instrumental = combine all combined stems ---
    combine_instrumental_from_files(
      [tmp_path / f"{s}_combined.mp3" for s in ("drums", "bass", "other")],
      instrumental_out,
    )


def _sum_stems(stem1: Path, stem2: Path, output: Path) -> None:
  """Sum two stem files using ffmpeg amix."""
  if not stem1.exists():
    if stem2.exists():
      shutil.copy2(stem2, output)
    return
  if not stem2.exists():
    shutil.copy2(stem1, output)
    return

  cmd = [
    "ffmpeg", "-y",
    "-i", str(stem1),
    "-i", str(stem2),
    "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
    str(output),
  ]
  subprocess.run(cmd, check=True, capture_output=True)
```

The existing `combine_instrumental` already does the 3-input amix. Refactor it slightly to accept a list of paths (or add a `combine_instrumental_from_files` variant) so both `separate()` and `separate_iterative()` can use it.

### 2. `server/models.py` — Add `deep_clean` flag

Add to `VariantsRequest` (used by the stems endpoint):

```python
class VariantsRequest(BaseModel):
  eq_match: bool = False
  exciter: bool = False
  deep_clean: bool = False  # run Demucs twice to recover leaked instrumental content
```

Add to bulk models:

```python
class BulkStemsRequest(BaseModel):
  song_ids: list[str] | None = None
  eq_match: bool = False
  exciter: bool = False
  deep_clean: bool = False
  clear_existing: bool = False
```

### 3. `server/main.py` — Route the flag through workers

**`start_stems` endpoint** (line ~560): Already receives `VariantsRequest`, pass `req.deep_clean` into the thread args.

**`_stems_worker`**: Add `deep_clean: bool = False` parameter. Call `demucs.separate_iterative()` when true, `demucs.separate()` otherwise:

```python
def _stems_worker(
  song_id: str,
  video_path: Path,
  vocals_out: Path,
  instrumental_out: Path,
  eq_match: bool = False,
  exciter: bool = False,
  deep_clean: bool = False,
) -> None:
  """Background worker for Demucs stem separation."""
  log.info(f"Stems started: {song_id} (deep_clean={deep_clean})")
  try:
    if deep_clean:
      demucs.separate_iterative(video_path, vocals_out, instrumental_out)
    else:
      demucs.separate(video_path, vocals_out, instrumental_out)
    # ... rest unchanged
```

**`_run_single_stems`**: Pass `deep_clean` through.

**`_bulk_worker`**: The bulk operations table already stores `eq_match` and `exciter`. Add `deep_clean` column to `bulk_operations` table so it persists across the queue.

### 4. `server/db.py` — Add `deep_clean` column to `bulk_operations`

In `_migrate()`, add migration for the new column:

```python
if "deep_clean" not in bulk_cols:
  conn.execute(
    "ALTER TABLE bulk_operations ADD COLUMN deep_clean INTEGER NOT NULL DEFAULT 0"
  )
```

No changes to the `songs` table — the feature doesn't add per-song state. The output files (`vocals.mp3`, `instrumental.mp3`) are the same regardless of whether deep clean was used.

### 5. `lib/api.ts` — Add flag to `AudioEnhanceOptions`

```typescript
export interface AudioEnhanceOptions {
  eq_match: boolean;
  exciter: boolean;
  deep_clean: boolean;
}
```

And to `BulkRequest`:

```typescript
export interface BulkRequest {
  eq_match: boolean;
  exciter: boolean;
  deep_clean: boolean;
  clear_existing: boolean;
}
```

### 6. `components/SongLibrary.tsx` — Add checkbox

**Per-song controls** (alongside EQ match and Exciter checkboxes):

```tsx
<label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
  <input
    type="checkbox"
    checked={deepCleanFlags[song.id] ?? false}
    onChange={(e) =>
      setDeepCleanFlags((f) => ({ ...f, [song.id]: e.target.checked }))
    }
    className="accent-teal-500"
  />
  Deep clean
</label>
```

**Bulk controls** (alongside bulk EQ match and Exciter):

```tsx
<label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
  <input
    type="checkbox"
    checked={bulkDeepClean}
    onChange={(e) => setBulkDeepClean(e.target.checked)}
    className="accent-emerald-500"
    disabled={bulkStatus?.active ?? false}
  />
  Deep clean
</label>
```

State additions:

```tsx
const [deepCleanFlags, setDeepCleanFlags] = useState<Record<string, boolean>>({});
const [bulkDeepClean, setBulkDeepClean] = useState(false);
```

Props: update `onStartStems` and `onStartBulkStems` option types to include `deep_clean`.

### 7. `app/page.tsx` — Wire up the new flag

Pass `deep_clean` from the SongLibrary callbacks through to the API calls. Follows the same pattern as `eq_match` and `exciter`.

## Impact on EQ Filter Pipeline

`_compute_eq_filter` and `_compute_progressive_eq_filter` both accept `vocals_path` for voice-silence gating. In `_variants_worker`, these are called with the vocals file written by stems separation.

**No code changes needed in the EQ functions themselves.** When deep clean is enabled:
- `vocals_out` = vocals2 (cleaner, less instrumental leak)
- `instrumental_out` = enhanced instrumental (pass-1 + recovered pass-2 content)
- EQ functions receive the cleaner vocals2, which means silence-gating will be *more accurate* — fewer chunks contaminated by leaked instrumental content in the vocal stem
- The instrumental being compared to the original mix is now richer (has recovered content), so the measured EQ delta will be smaller where content was recovered — meaning less aggressive (and more correct) EQ correction

**Net effect: EQ matching quality improves automatically with deep clean.**

## Impact on Variant Generation

`_variants_worker` receives `vocals_path` and `instrumental_path`. These are the final output files from stems separation. Since deep clean writes to the same filenames (`{id}_vocals.mp3`, `{id}_instrumental.mp3`), variant generation is completely unchanged — it operates on whatever files are there.

## Impact on Other Features

- **Export** (`_export_worker`): Uses `vocals_filename` and `instrumental_filename` from DB. Same filenames, no change needed.
- **Audio serving** (`GET /api/songs/{id}/audio/{stem}`): Serves files from `AUDIO_DIR`. Same filenames, no change needed.
- **SongPlayer**: Loads variants or falls back to stem files. No change needed.
- **Overlay**: Uses video only, no audio involvement. No change needed.

## Risks and Mitigations

### 1. Double processing time for stem separation
Demucs runs twice. On a GPU this is typically 30-60s per pass for a 4-minute song, so total ~1-2 minutes.

**Mitigation**: User confirmed this is acceptable — stem separation is the fast part of the pipeline. The checkbox makes it opt-in.

### 2. Diminishing returns / quality regression on pass 2
If Demucs extracts very little instrumental content from vocals1, the pass-2 instrumental stems will be near-silent, adding only noise. In extreme cases, processing artifacts from the second pass could degrade quality.

**Mitigation**: This is experimental by nature. The `normalize=0` flag ensures near-silent stems don't affect the mix. Users can compare results with and without deep clean and choose per-song.

### 3. Phase alignment between pass-1 and pass-2 stems
Pass-2 stems originate from a different source (vocals1) than pass-1 stems (original mix). While they represent the same musical content, the Demucs model may introduce slight timing or phase shifts.

**Mitigation**: Since pass-2 instrumental content is *leaked* content that shouldn't have been in the vocals at all, even imperfect phase alignment is better than the content being entirely absent. Any minor phase artifacts are unlikely to be perceptible in context. If this proves to be an issue, a future enhancement could use sample-level cross-correlation to align stems before mixing.

### 4. Pass-2 vocals may lose legitimate vocal content
If Demucs aggressively separates vocals2, it might strip some genuine vocal content, making vocals thinner or more artificial.

**Mitigation**: The primary goal is instrumental quality, not vocal quality. For the karaoke use case, vocal quality at reduced mix levels (0%, 25%) is less critical — the user is singing. If vocals2 quality becomes a concern, a future option could keep vocals1 while still using the recovered instrumental.

### 5. Disk space and temp directory usage
The second Demucs pass creates a full set of stems in a temp directory. For a 4-minute song this is ~100MB of temp WAV/MP3 files.

**Mitigation**: Everything is in a `tempfile.TemporaryDirectory()` context manager, cleaned up automatically. Final output is the same two files as normal mode.

## What "Success" Looks Like

### Objective measures
- **A/B comparison**: For a song where instrumental quality is known to suffer, compare the standard instrumental vs deep-clean instrumental. Listen for:
  - Vocal bleed reduction in the standard path (not the goal but would be a bonus)
  - Missing instrument presence recovery: guitar lines, synth pads, or percussion hits that were muted or thinned in standard mode should be audible in deep clean mode
  - No new artifacts: clicks, phase cancellation notches, or "watery" sound
- **Spectral analysis**: Compare spectrograms of standard vs deep-clean instrumentals. Recovered content should appear as energy in frequency bands that were previously empty/attenuated.

### Subjective measures
- Does the instrumental sound "fuller" and more like the original mix (minus vocals)?
- With EQ match enabled, does deep clean reduce the amount of EQ correction needed (indicating less content loss)?
- In variant playback at 0% vocal level, does the backing track feel more complete?

### Failure indicators
- Deep clean instrumental sounds worse (artifacts, phasing, distortion)
- Pass-2 stems are consistently near-silent (Demucs found nothing to extract from vocals1) — would indicate the feature adds processing time for no benefit
- Vocals2 sound noticeably thinner or more processed than vocals1

## Implementation Order

1. `server/demucs.py` — Add `separate_iterative()` and `_sum_stems()`
2. `server/models.py` — Add `deep_clean` to `VariantsRequest`, `BulkStemsRequest`, `BulkVariantsRequest`
3. `server/db.py` — Add `deep_clean` column migration for `bulk_operations`
4. `server/main.py` — Thread `deep_clean` through `_stems_worker`, `_run_single_stems`, bulk worker, and the stems endpoint
5. `lib/api.ts` — Add `deep_clean` to `AudioEnhanceOptions` and `BulkRequest`
6. `components/SongLibrary.tsx` — Add checkbox state and UI for per-song and bulk controls
7. `app/page.tsx` — Wire callbacks

Estimated scope: ~150 lines of Python, ~30 lines of TypeScript.
