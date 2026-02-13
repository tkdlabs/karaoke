"""Demucs stem separation wrapper.

Extracts audio from video, runs demucs, and produces vocals + instrumental files.
Reuses logic from workflows/karaoke/audio.py.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract audio track from video as WAV."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        str(audio_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def run_demucs(input_path: Path, output_dir: Path, model: str = "htdemucs") -> Path:
    """Run demucs and return the stems directory."""
    cmd = [
        "demucs",
        "-n", model,
        "-o", str(output_dir),
        "--mp3",
        str(input_path),
    ]
    subprocess.run(cmd, check=True)
    return output_dir / model / input_path.stem


def combine_instrumental(stems_dir: Path, output_path: Path) -> None:
    """Combine bass + drums + other stems into a single instrumental file using ffmpeg."""
    stems = [stems_dir / f for f in ("bass.mp3", "drums.mp3", "other.mp3") if (stems_dir / f).exists()]
    if not stems:
        raise FileNotFoundError(f"No instrumental stems found in {stems_dir}")

    # Use ffmpeg amix filter to combine stems
    cmd = ["ffmpeg", "-y"]
    for s in stems:
        cmd += ["-i", str(s)]
    cmd += [
        "-filter_complex", f"amix=inputs={len(stems)}:duration=longest:normalize=0",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def separate(video_path: Path, vocals_out: Path, instrumental_out: Path) -> None:
    """
    Full pipeline: extract audio from video, run demucs, produce vocals + instrumental.

    Args:
        video_path: Path to the source video file.
        vocals_out: Where to write the vocals mp3.
        instrumental_out: Where to write the instrumental mp3.
    """
    vocals_out.parent.mkdir(parents=True, exist_ok=True)
    instrumental_out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Extract audio
        wav_path = tmp_path / "audio.wav"
        extract_audio(video_path, wav_path)

        # Run demucs
        stems_dir = run_demucs(wav_path, tmp_path)

        # Copy vocals
        vocals_stem = stems_dir / "vocals.mp3"
        if not vocals_stem.exists():
            raise FileNotFoundError(f"Vocals stem not found at {vocals_stem}")
        shutil.copy2(vocals_stem, vocals_out)

        # Combine instrumental stems
        combine_instrumental(stems_dir, instrumental_out)
