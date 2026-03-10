# Bug 05: Korean romanization silently disabled in deployment — overlay_romanized same as lyrics

## Status
Fixed

## Symptom
GET /api/songs/{id}/video/overlay_romanized serves the same video as overlay_lyrics.
Korean lyrics are not romanized in the overlay output.

## Root Cause
`korean_romanizer` is an optional dependency of `karaoke_workflows` (under the `[korean]`
extra in its `pyproject.toml`). It is not listed in `server/requirements.txt`, so it is
never installed in the deployment venv.

When `korean_romanizer` is unavailable, `lyrics.py` sets `HAS_KOREAN_ROMANIZER = False`
and `romanize_korean()` always returns `None`. As a result:

  `_lyrics_need_romanization(lyrics_lrc)` → always `False`

The overlay worker then renders once with `romanize=False` and copies that file for both
the `overlay_lyrics` and `overlay_romanized` outputs. No error is raised.

Previously the server ran from the shared ai-dev `.venv` (which has `korean_romanizer`
installed). The deploy refactor switched to a project-specific venv built only from
`server/requirements.txt`, which omitted the optional dep.

## Fix
Add `korean_romanizer` to `server/requirements.txt`.

## Affected files
- `server/requirements.txt` — fix
- `server/main.py` `_lyrics_need_romanization()` — silent failure with no log warning
