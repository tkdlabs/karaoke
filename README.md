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