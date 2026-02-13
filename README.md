Frontend/backend for karaoke management.

We should basically provide a database and additionally functionality of workflows/karaoke/remove_vocals.py and support using yt-dlp.

The frontend should live in frontends/karaoke and it maintain a database of karaoke videos and allow:

- F3 Fetching/Searching videos using yt-dlp:
  - Display search results, and allow fetching the original music video.

- F4 Fetching/Searching lyrics files based on libLrc.
  - Map them to the metadata containing the video.

- F5 Store derived audio files from running demucs:
  - Vocals, everything minus vocals.

- F6 Render the lyrics on the downloaded video (no sound):
  - Follow the logic of workflows/karaoke/remove_vocals.py

- F7 Download videos for export:
  - With % of vocals mixed in (again follow workflows/karaoke/remove_vocals.py)


Additionally the backend should provide streaming API to use by eg. ExoPlayer or MediaPlayer.
  - F1: Allow to update the backend to mix in vocals at different rates.
  - F2: On-the-fly pitch change for vocals, and other audio stream, being able to update this while streaming.