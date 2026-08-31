Frontend/backend for karaoke management.

We should basically provide a database and additionally functionality of workflows/karaoke/remove_vocals.py and support using yt-dlp.

The frontend should live in frontends/karaoke and it maintain a database of karaoke videos and allow:

- *IMPLEMENTED* F3 Fetching/Searching videos using yt-dlp:
  - Display search results, and allow fetching the original music video.

- *IMPLEMENTED* F4 Fetching/Searching lyrics files based on libLrc.
  - Map them to the metadata containing the video.

- *IMPLEMENTED* F5 Store derived audio files from running demucs:
  - Vocals, everything minus vocals.

- *IMPLEMENTED* F6 Render the lyrics on the downloaded video (no sound):
  - Follow the logic of workflows/karaoke/remove_vocals.py

- *IMPLEMENTED* F7 Download videos for export:
  - With % of vocals mixed in (again follow workflows/karaoke/remove_vocals.py)


Additionally the backend should provide streaming API to use by eg. ExoPlayer or MediaPlayer.
  - *IMPLEMENTED* F1: Streaming endpoint with configurable vocal level (3 presets) and video stream selection (original or lyrics overlay).
  - *IMPLEMENTED* F2: On-the-fly pitch change (+-3 semitones) for the mixed audio, applied per chunk while streaming.

Android TV client (target Android TV 11):

- Uses the thumbnails and metadata from backend to display a grid display of songs to choose from.
- Uses the same endpoints via ExoPlayer to play the pre-defined streams (video - lyrics by default), default pitch = 0, default voice config = configurable, but guide as default would be OK.
- TV remote can change: voice support, pitch, turn on/off lyrics while playing.

## License & responsible use

This project is MIT-licensed (see `LICENSE`). Third-party dependencies and
pretrained weights carry their own terms — see `THIRD_PARTY_NOTICES.md`.

**Non-commercial stems:** the default Demucs `htdemucs` pretrained weights are
CC-BY-NC 4.0 (trained on research-only MUSDB18 data). Using stems separation
**commercially violates the weights license**. You can switch models with the
`DEMUCS_MODEL` env var (e.g. `htdemucs_ft`), but every Demucs-family checkpoint
is non-commercial. For commercial use, a permissively-licensed separation model
(e.g. Spleeter) is required. The active model is shown in the app UI and
reported by `GET /api/health` as `stems_model`.

**yt-dlp is optional** (see feature 39): search/download only work when the
binary is installed. Without it, use "Import video" to add local files.

**Media ownership:** you are responsible for the videos and lyrics you download
and process, and for clearing rights to them before distribution.