# Feature: Document stem-model license and add project licensing

## Summary
Document the non-commercial constraint of the Demucs `htdemucs` model weights, make the model
swappable so permissive alternatives can be used, and add a proper LICENSE + third-party
attributions to the project before public release.

## Motivation
The `demucs` package is MIT, but its `htdemucs` pretrained weights are **CC-BY-NC 4.0**
(non-commercial) — trained on the MusDB dataset, which is research-only. Anyone using the stems
feature commercially would violate the weights license. yt-dlp (Unlicense/PD), ffmpeg (GPL, invoked
externally), moviepy (MIT), lrcup (MIT), and lrclib (community API) all carry their own conditions
that should be documented. The repo currently has no LICENSE file at all.

## Design
- Swappable model: `server/demucs.py::run_demucs` already takes `model`, and passes `-n` to the CLI.
  Read the name from env `DEMUCS_MODEL` (default `htdemucs`) so operators can point at a
  permissively-licensed checkpoint; surface the active model in `/api/health`.
- UI: small disclaimer in the stems section of `SongLibrary.tsx`, e.g. "Stems use Demucs
  `htdemucs` weights (CC-BY-NC 4.0, non-commercial)". Shown when the active model is non-commercial.
- Repo: add `LICENSE` (MIT) + `THIRD_PARTY_NOTICES.md` listing demucs (MIT), htdemucs weights
  (CC-BY-NC 4.0), moviepy (MIT), lrcup (MIT), korean_romanizer, ffmpeg/ffprobe (GPL, external),
  yt-dlp (Unlicense, optional per feature 39), and the lrclib.net terms.
- README: "License & responsible use" section covering the above and that users are responsible for
  the media they process.

## Scope
- `server/demucs.py`: env-driven model name; `server/main.py`: /api/health field
- `components/SongLibrary.tsx`: stems disclaimer
- Repo: `LICENSE`, `THIRD_PARTY_NOTICES.md`, README section
- No functional changes to stems separation, variants, export, player, or overlay

## Follow-up (out of scope for this feature)
An engine abstraction (`STEM_ENGINE` env) that swaps in a permissively-licensed
separation backend — Spleeter (Deezer, MIT weights) is the realistic candidate;
open-unmix weights are also non-commercial. Spleeter pulls TensorFlow, so it
would run in a nested venv or Docker rather than the main venv.

## Acceptance Criteria
- [ ] `DEMUCS_MODEL` env var selects the Demucs model; default remains `htdemucs`
- [ ] `/api/health` reports the active model; disclaimer shown in stems UI
- [ ] `LICENSE` and `THIRD_PARTY_NOTICES.md` present and accurate
- [ ] README has a license/attribution section incl. CC-BY-NC warning and responsible-use note
- [ ] Existing tests pass; identical stems output with default settings