# Dynamic EQ Filter for Non-Voice Stem Enrichment

## Status: Phase 1-3 Implemented

---

## Problem

The current `_compute_eq_filter()` averages FFT power across **all** 10-second chunks of the entire file, comparing the original mix against the instrumental stem. This creates a systematic measurement error: in vocal-heavy sections the original contains vocal energy (300 Hz–4 kHz fundamentals, 4–16 kHz harmonics/sibilance/breath) that the instrumental correctly does not have. The EQ correction interprets this missing vocal energy as a separation loss and attempts to compensate — boosting frequencies that were never part of the instrumental content.

Combined with `_build_exciter_filter()` (aexciter above 4 kHz generating harmonics), the result is over-emphasized high frequencies producing an unrealistic, "tweety" character in the enriched instrumental.

### Current Band Strengths (for reference)

| Band   | Strength | Risk of vocal bleed into correction |
|--------|----------|-------------------------------------|
| 63 Hz  | 0.50     | Low — vocals absent                 |
| 125 Hz | 0.45     | Low                                 |
| 250 Hz | 0.35     | Low–medium                          |
| 500 Hz | 0.12     | High — vocal fundamental            |
| 1 kHz  | 0.10     | High — vocal core                   |
| 2 kHz  | 0.10     | High — vocal presence               |
| 4 kHz  | 0.30     | Medium — sibilance region           |
| 8 kHz  | 0.40     | Medium — breath/air                 |
| 16 kHz | 0.45     | Medium — high-freq artifacts + exciter overlap |

The 8 kHz (0.40) and 16 kHz (0.45) bands are particularly affected: vocal breath noise and harmonic content at these frequencies inflates the measured original-vs-instrumental gap, leading to aggressive correction that the exciter then amplifies further.

---

## Proposed Approach: Voice-Silence-Gated EQ

### Core Idea

Instead of averaging FFT power over all chunks, **only use chunks where the vocal stem has low energy** (instrumental breaks, intros, outros, and micro-silences between phrases even within choruses). In these segments the original and instrumental should be nearly identical — any measured difference represents genuine separation artifacts rather than the expected absence of vocals.

### Algorithm

```
1. Decode original, instrumental, AND vocals to PCM mono at 22050 Hz
2. Chunk all three into 10-second windows (same as current)
3. For each chunk, compute RMS energy of the vocal stem
4. Rank chunks by vocal energy, select bottom N% (e.g., bottom 30%)
   - Alternatively: threshold-based — use chunks where vocal RMS < X dB below peak
5. Accumulate FFT power only from selected chunks
6. Compute per-band gain correction as before (with _EQ_BAND_STRENGTH, clamp)
7. If fewer than K qualifying chunks found, fall back to current full-file averaging
```

### Chunk Granularity

10-second chunks may be too coarse for detecting micro-silences between vocal phrases. Consider:

- **2–3 second chunks**: Better temporal resolution for catching inter-phrase gaps in dense vocal sections (choruses). Increases FFT resolution trade-off but 2s at 22050 Hz still gives 44100-point FFT — more than sufficient for octave-band analysis.
- **Adaptive**: Use 2s chunks for silence detection, then merge adjacent qualifying chunks for FFT analysis to maintain frequency resolution.

### Threshold Strategy

- **Percentile-based** (bottom 30% by vocal RMS): Adapts to each song automatically. A capella songs with no true silence may select "least vocal" segments — still an improvement over all-segment averaging.
- **Absolute threshold** (vocal RMS < -40 dBFS): More predictable but risks selecting zero chunks in continuously vocal-heavy tracks.
- **Hybrid**: Use absolute threshold first; if <3 chunks qualify, fall back to percentile.

---

## Risks

### 1. Insufficient silence segments
Songs with wall-to-wall vocals (certain pop, rap) may have very few qualifying chunks. The fallback to full-file averaging means no regression, but also no improvement for these tracks.

**Mitigation**: Reduce chunk size to 2–3s to catch micro-silences. The hybrid threshold ensures graceful degradation.

### 2. Processing time increase
Reading the vocal stem PCM adds ~1 decode (currently we only decode original + instrumental). RMS computation per chunk is negligible. Overall impact: ~30–50% more I/O time in `_compute_eq_filter()`, still under 10s for a typical 4-minute song.

### 3. Silence segments may not be representative
Intros/outros may have different instrumentation than the main body of the song (e.g., a sparse piano intro vs. full-band chorus). EQ correction derived from sparse sections may under-correct for the denser sections.

**Mitigation**: Weight qualifying chunks by how "full" (non-silent across the frequency spectrum) the instrumental is — preferring instrumental breaks with full arrangement over sparse intros.

### 4. Demucs vocal leakage
Demucs isn't perfect — the "vocal stem" may still contain some instrument bleed, especially percussive transients and bright synths. A "silent vocal" chunk might actually have leaked instrumental content, skewing the reference.

**Mitigation**: This actually helps — if the vocal stem leaks instrument content, those chunks will have higher vocal RMS and will be excluded, naturally selecting cleaner reference segments.

### 5. Overfitting to specific content
Silence segments in one genre may have a very different spectral profile than in another. A carefully tuned threshold for one genre may underperform on another.

**Mitigation**: The percentile-based approach is genre-agnostic since it's relative to each song's own vocal energy distribution.

---

## Alternatives

### A. Reduce static band strengths at 8 kHz / 16 kHz

**Simplest change**. Lower `_EQ_BAND_STRENGTH` at 8 kHz from 0.40 → 0.20 and 16 kHz from 0.45 → 0.25. Reduces the "tweety" artifact with zero added complexity or processing time.

| Pro | Con |
|-----|-----|
| Zero code complexity | Blanket reduction — songs that genuinely lost high-freq content won't get corrected |
| No additional decoding | Requires manual tuning per iteration |

**Effort**: Trivial — constant change, A/B test.

### B. Reduce or disable the exciter filter

The aexciter generates harmonics above 4 kHz. Combined with the EQ boosting 8 kHz/16 kHz, this is likely the primary source of the "tweet" character. Options:

- **Disable exciter entirely** (`exciter=False` default or remove)
- **Raise exciter freq** from 4000 → 6000+ Hz so it only adds extreme air
- **Lower drive/blend/amount** (currently 4/2/2 → try 2/1/1)

| Pro | Con |
|-----|-----|
| Directly addresses the harmonic generation causing "tweet" | Loses some brightness restoration that benefits certain songs |
| Simple parameter change | Still a static approach |

**Effort**: Trivial — parameter change, A/B test.

### C. Spectral envelope matching (more sophisticated)

Instead of octave-band EQ, compute a smooth spectral envelope (e.g., LPC or cepstral smoothing) of the original and instrumental, derive a continuous correction curve, and apply via FFT filtering. This avoids the coarse octave-band approximation and can be more precise.

| Pro | Con |
|-----|-----|
| More accurate frequency correction | Significantly more complex implementation |
| No discrete band artifacts | Cannot be expressed as simple ffmpeg EQ filters — needs custom FFT processing |
| Can combine with silence-gating | Higher CPU cost |

**Effort**: High — requires custom audio processing pipeline outside ffmpeg filter chains.

### D. Per-band silence detection (hybrid of proposed + current)

Instead of a global voice-silence gate, detect silence **per frequency band**. For each EQ band, only accumulate power from chunks where the vocal stem has low energy **in that specific band**. This handles the case where vocals are present in mid-range but high frequencies are voice-free.

| Pro | Con |
|-----|-----|
| Most precise approach | More complex than global silence gating |
| Handles partial vocal presence well | Diminishing returns — vocal harmonics typically span wide range |

**Effort**: Medium — extends the proposed approach.

### E. Progressive EQ (section-adaptive correction)

Instead of computing a single global EQ curve for the entire song, **detect the spectral distribution in different sections** (intro, verse, chorus, bridge, outro) and apply **per-section EQ corrections**. Instrumentation often changes dramatically between sections — a sparse verse (acoustic guitar + bass) has a very different spectral profile than a full-band chorus (drums, synths, layered guitars).

#### Approach

```
1. Segment the song into N regions (e.g., 30-second windows or structural sections)
2. For each region, compute the original-vs-instrumental spectral gap
3. Derive per-region EQ correction curves
4. Apply time-varying EQ using ffmpeg's sendcmd/asendcmd mechanism
   or pre-process in numpy and stitch the output
```

#### ffmpeg Implementation Options

- **`sendcmd` / `asendcmd`**: ffmpeg supports timed filter parameter changes. We can schedule EQ gain changes at section boundaries:
  ```
  asendcmd=c='0.0 equalizer@e1 g 3.5; 30.0 equalizer@e1 g 1.2; 60.0 equalizer@e1 g 4.0'
  ```
  Each command changes the gain of a named EQ filter at a specific timestamp. Supports smooth transitions if combined with crossfade or ramped values.

- **Segment + stitch**: Process each section independently with its own static EQ, then concatenate. Risk of audible seams at boundaries unless crossfaded.

- **Numpy FFT processing**: Apply a time-varying spectral correction curve directly in the frequency domain, write the result to a temp file, then pass to ffmpeg for encoding. Most flexible but exits the ffmpeg filter chain.

#### Risks Specific to Progressive EQ

| Risk | Severity | Mitigation |
|------|----------|------------|
| Audible gain jumps at section boundaries | High | Ramp/interpolate gains over 1–2s at transitions |
| Section detection accuracy | Medium | Use fixed-length windows (e.g., 30s) instead of structural analysis |
| Increased complexity in filter chain | Medium | Start with 3–4 regions, not full structural segmentation |
| sendcmd support varies across ffmpeg builds | Low | Test on target deployment; fallback to numpy processing |

| Pro | Con |
|-----|-----|
| Adapts to instrumentation changes within the song | Significantly more complex than static EQ |
| Can combine with silence-gating per section | Audible artifacts at section boundaries |
| Most natural-sounding correction | sendcmd parameter scheduling adds ffmpeg complexity |
| Handles songs where verse ≠ chorus instrumentation | Debugging filter chains becomes harder |

**Effort**: Medium–High. The `sendcmd` approach keeps us in ffmpeg but requires careful timestamp computation and gain ramping. The numpy approach is more flexible but adds a processing step.

**Relationship to other approaches**: Progressive EQ can be combined with silence-gating (Phase 2) — use silence-gated analysis per section to compute that section's correction curve. This would be the most accurate approach but also the most complex.

---

## Recommendation

### Phase 1 — Quick wins ✅ APPROVED
1. **Reduce exciter intensity**: `drive=2, blend=1, amount=1` or disable entirely. This is likely the single biggest contributor to the "tweet" artifact.
2. **Lower 8 kHz / 16 kHz band strengths** to 0.20 / 0.25. Conservative reduction.
3. A/B test on 3–5 songs spanning genres (ballad, pop, rock, R&B).

### Phase 2 — Dynamic EQ ✅ IMPLEMENTED
4. Voice-silence-gated EQ with 3s chunks and hybrid threshold (-40 dBFS absolute / bottom 30% percentile fallback).
5. `_compute_eq_filter()` now accepts optional `vocals_path` parameter.
6. A/B test against Phase 1 baseline.

### Phase 3 — Progressive EQ (section-adaptive) ✅ IMPLEMENTED
7. `_compute_progressive_eq_filter()` segments song into 30s sections with per-section EQ.
8. Uses `asendcmd` with named `equalizer@e<hz>` instances, gain changes scheduled 1s before section boundaries.
9. Combines with silence-gating per section.
10. Auto-selected for songs >60s; falls back to Phase 2 static EQ for shorter songs or on failure.

### Phase 4 — Refinement
10. Per-band silence detection (Alternative D).
11. Adaptive exciter parameters based on measured high-frequency loss.

---

## Implementation Sketch (Phase 2)

Changes to `_compute_eq_filter()` in `server/main.py`:

```python
def _compute_eq_filter(original_path: Path, instrumental_path: Path,
                       vocals_path: Path | None = None) -> str:
    # ... existing numpy import and PCM decode for orig, inst ...

    # NEW: decode vocals for silence detection
    if vocals_path:
        vox = _read_pcm_mono(vocals_path, sr)
        vox = vox[:length]

    chunk = sr * 3  # reduced from 10s to 3s for better temporal resolution
    n_chunks = max(1, length // chunk)

    # Compute per-chunk vocal RMS
    if vocals_path:
        vox_rms = []
        for k in range(n_chunks):
            v = vox[k * chunk : (k + 1) * chunk]
            if len(v) < chunk:
                v = np.pad(v, (0, chunk - len(v)))
            vox_rms.append(np.sqrt(np.mean(v ** 2)))
        vox_rms = np.array(vox_rms)

        # Hybrid threshold: absolute first, percentile fallback
        abs_threshold = 10 ** (-40 / 20)  # -40 dBFS
        quiet_mask = vox_rms < abs_threshold
        if quiet_mask.sum() < 3:
            # Fallback: bottom 30% by vocal energy
            threshold = np.percentile(vox_rms, 30)
            quiet_mask = vox_rms <= threshold
    else:
        quiet_mask = np.ones(n_chunks, dtype=bool)  # all chunks (current behavior)

    # Accumulate FFT power only from qualifying chunks
    half = chunk // 2 + 1
    orig_pwr = np.zeros(half)
    inst_pwr = np.zeros(half)
    used = 0

    for k in range(n_chunks):
        if not quiet_mask[k]:
            continue
        # ... existing FFT accumulation ...
        used += 1

    if used == 0:
        return ""  # no qualifying chunks

    # ... rest unchanged ...
```

Calling code in `_variants_worker()` would pass `vocals_path` to `_compute_eq_filter()`.

---

## Open Questions

1. What's the right chunk size? 2s vs 3s vs 5s — needs empirical testing.
2. Should we weight qualifying chunks by instrumental RMS (prefer "full" arrangement over sparse intros)?
3. Is the exciter worth keeping at all, or should it be removed entirely?
