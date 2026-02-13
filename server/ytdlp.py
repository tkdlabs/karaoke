"""yt-dlp wrappers for searching and downloading videos."""

import json
import subprocess
from pathlib import Path

from models import SearchResult


def search(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search YouTube and return structured results."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--flat-playlist",
        "--no-download",
        f"ytsearch{max_results}:{query}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {result.stderr[:200]}")

    results = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        data = json.loads(line)
        results.append(SearchResult(
            video_id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("uploader", data.get("channel", "Unknown")),
            duration=float(data.get("duration") or 0),
            thumbnail_url=data.get("thumbnail", ""),
            url=data.get("url") or data.get("webpage_url") or f"https://www.youtube.com/watch?v={data.get('id', '')}",
        ))

    return results


def download(url: str, output_path: Path) -> None:
    """Download a video to the specified path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {result.stderr[:500]}")
