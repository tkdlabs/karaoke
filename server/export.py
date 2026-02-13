"""Export video with vocals mixed in at a configurable level.

Uses ffmpeg to mix vocals + instrumental audio and mux onto the original video.
"""

import subprocess
from pathlib import Path


def create_export(
    video_path: Path,
    vocals_path: Path,
    instrumental_path: Path,
    output_path: Path,
    vocal_level: float = 0.3,
) -> None:
    """
    Create an export video with vocals mixed at the given level.

    Args:
        video_path: Source video file.
        vocals_path: Vocals audio (mp3).
        instrumental_path: Instrumental audio (mp3).
        output_path: Where to write the output mp4.
        vocal_level: 0.0 = pure instrumental, 1.0 = full vocals.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build ffmpeg command:
    # - Input 0: video (copy stream)
    # - Input 1: instrumental audio
    # - Input 2: vocals audio (scaled by vocal_level)
    # - Mix instrumental + scaled vocals, mux with video
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(instrumental_path),
        "-i", str(vocals_path),
        "-filter_complex",
        f"[2:a]volume={vocal_level}[v];[1:a][v]amix=inputs=2:duration=longest:normalize=0[a]",
        "-map", "0:v:0",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
