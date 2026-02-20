"""Export video with vocals mixed in at a configurable level.

Uses ffmpeg to mix vocals + instrumental audio and mux onto the original video.
"""

import re
import subprocess
from collections.abc import Callable
from pathlib import Path


def _parse_ffmpeg_time(time_str: str) -> float:
    """Parse ffmpeg time string like '00:03:45.123456' to seconds."""
    m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", time_str)
    if not m:
        return 0.0
    h, mins, s, us = m.groups()
    return int(h) * 3600 + int(mins) * 60 + int(s) + int(us) / 1_000_000


def create_export(
    video_path: Path,
    vocals_path: Path,
    instrumental_path: Path,
    output_path: Path,
    vocal_level: float = 0.3,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """
    Create an export video with vocals mixed at the given level.

    Args:
        video_path: Source video file.
        vocals_path: Vocals audio (mp3).
        instrumental_path: Instrumental audio (mp3).
        output_path: Where to write the output mp4.
        vocal_level: 0.0 = pure instrumental, 1.0 = full vocals.
        duration: Total duration in seconds (for progress calculation).
        on_progress: Optional callback receiving progress as 0.0-1.0.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
    ]

    if on_progress and duration and duration > 0:
        cmd += ["-progress", "pipe:1"]
        cmd.append(str(output_path))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time="):
                current = _parse_ffmpeg_time(line.split("=", 1)[1])
                on_progress(min(current / duration, 1.0))
        proc.wait()
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"ffmpeg export failed: {stderr[:500]}")
    else:
        cmd.append(str(output_path))
        subprocess.run(cmd, check=True, capture_output=True)
