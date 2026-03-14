# Feature 33: Lyrics API endpoint for native TV rendering

## Description

Add `GET /api/songs/{song_id}/lyrics` to expose the stored LRC lyrics as structured
JSON, with optional server-side romanization. This endpoint is consumed by the
karaoke-tv Android app so it can render lyrics natively without switching video
streams (see karaoke-tv feat_03).

Romanization must remain server-side because `korean_romanizer` is a Python library
and the existing romanization logic in `overlay.py` can be reused directly.

## Endpoint spec

```
GET /api/songs/{song_id}/lyrics?romanize=false
```

### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `romanize` | bool | `false` | If `true`, add romanized text for each line where applicable |

### Response — 200 OK

```json
{
  "song_id": "abc123",
  "has_lyrics": true,
  "lines": [
    { "time_ms": 1000, "text": "안녕하세요", "romanized": "annyeonghaseyo" },
    { "time_ms": 5400, "text": "Hello world",  "romanized": null }
  ]
}
```

- `time_ms`: cue start time in milliseconds (parsed from LRC `[MM:SS.CC]`)
- `text`: lyric line as stored
- `romanized`: romanized text if `romanize=true` and the line contains Hangul,
  otherwise `null`
- `has_lyrics`: `false` (and `lines: []`) when no `lyrics_synced` is stored

### Error cases

| Status | Condition |
|--------|-----------|
| 404 | Song not found |
| 422 | `romanize=true` but `korean_romanizer` is not installed |

### Notes

- LRC parsing: strip `[MM:SS.CC]` prefix, convert to ms, skip metadata lines
  (`[ti:]`, `[ar:]`, `[al:]`, `[by:]`, `[offset:]`)
- Endpoint is read-only — register on the always-on router (available in SERVE_MODE)
- Reuse `_detect_korean` and romanization logic already in `overlay.py`

## Acceptance criteria

- [ ] `GET /api/songs/{id}/lyrics` returns parsed LRC lines as JSON
- [ ] `?romanize=true` returns `romanized` field populated for Hangul lines
- [ ] `?romanize=true` returns 422 when `korean_romanizer` not installed
- [ ] Returns `has_lyrics: false, lines: []` when no synced lyrics stored
- [ ] Returns 404 for unknown song
- [ ] Endpoint available in SERVE_MODE (read-only router)
- [ ] Unit tests cover: LRC parsing, romanization, missing lyrics, missing library
