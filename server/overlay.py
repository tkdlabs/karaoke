"""Lyrics overlay video creation.

Renders synced lyrics on a video file using the local karaoke_lib package
(bundled from the former karaoke_workflows dependency).
"""

from collections.abc import Callable
from pathlib import Path

from proglog import ProgressBarLogger

from karaoke_lib.lyrics import parse_lyrics_content
from karaoke_lib.video import create_lyrics_overlay_video


class _ProgressCallback(ProgressBarLogger):
    """Proglog logger that calls a callback with progress (0.0-1.0)."""

    def __init__(self, callback: Callable[[float], None]):
        super().__init__()
        self._callback = callback

    def bars_callback(self, bar, attr, value, old_value=None):
        if attr == "index" and bar == "frame_index":
            total = self.bars[bar]["total"]
            if total:
                self._callback(value / total)


def create_overlay(
    video_path: Path,
    lyrics_lrc: str,
    output_path: Path,
    on_progress: Callable[[float], None] | None = None,
    romanize: bool = True,
) -> None:
    """Render synced lyrics on top of a video (no audio track).

    Args:
        video_path: Source video file.
        lyrics_lrc: Synced lyrics in LRC format.
        output_path: Where to write the output mp4.
        on_progress: Optional callback receiving progress as 0.0-1.0.
        romanize: Whether to render romanized text below CJK lyrics.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lyrics = parse_lyrics_content(lyrics_lrc)
    if not lyrics:
        raise ValueError("No synced lyrics could be parsed")

    logger = _ProgressCallback(on_progress) if on_progress else "bar"
    create_lyrics_overlay_video(video_path, None, lyrics, output_path, logger=logger, romanize=romanize)
