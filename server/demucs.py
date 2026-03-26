"""Demucs stem separation wrapper.

Extracts audio from video, runs demucs, and produces vocals + instrumental files.
Reuses logic from workflows/karaoke/audio.py.
"""

import shutil
import subprocess
import sys
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
    # Use the demucs binary co-located with our Python interpreter.
    # We avoid `sys.executable -m demucs` because the local server/demucs.py module
    # shadows the installed demucs package during module lookup, causing a silent no-op.
    demucs_bin = Path(sys.executable).parent / "demucs"
    cmd = [
        str(demucs_bin),
        "-n", model,
        "-o", str(output_dir),
        "--mp3",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"demucs failed (exit {result.returncode}):\n{result.stderr[-1000:]}"
        )
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


def _sum_stems(stem1: Path, stem2: Path, output: Path) -> None:
    """Sum two stem files using ffmpeg amix."""
    if not stem1.exists():
        if stem2.exists():
            shutil.copy2(stem2, output)
        return
    if not stem2.exists():
        shutil.copy2(stem1, output)
        return
    cmd = [
        "ffmpeg", "-y",
        "-i", str(stem1),
        "-i", str(stem2),
        "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def separate_iterative(video_path: Path, vocals_out: Path, instrumental_out: Path) -> None:
    """Two-pass Demucs: extract leaked instrumental from vocals, merge back."""
    vocals_out.parent.mkdir(parents=True, exist_ok=True)
    instrumental_out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # --- Pass 1: original mix ---
        wav_path = tmp_path / "audio.wav"
        extract_audio(video_path, wav_path)
        stems1_dir = run_demucs(wav_path, tmp_path / "pass1")

        # --- Pass 2: re-separate vocals from pass 1 ---
        vocals1 = stems1_dir / "vocals.mp3"
        if not vocals1.exists():
            raise FileNotFoundError(f"Pass 1 vocals not found at {vocals1}")
        stems2_dir = run_demucs(vocals1, tmp_path / "pass2")

        # --- Combine per-instrument stems (pass1 + pass2) ---
        for stem_name in ("drums", "bass", "other"):
            s1 = stems1_dir / f"{stem_name}.mp3"
            s2 = stems2_dir / f"{stem_name}.mp3"
            combined = tmp_path / f"{stem_name}_combined.mp3"
            _sum_stems(s1, s2, combined)

        # --- Final vocals = pass 2 vocals ---
        vocals2 = stems2_dir / "vocals.mp3"
        if not vocals2.exists():
            raise FileNotFoundError(f"Pass 2 vocals not found at {vocals2}")
        shutil.copy2(vocals2, vocals_out)

        # --- Final instrumental = combine all combined stems ---
        combine_instrumental_stems = [
            tmp_path / f"{s}_combined.mp3" for s in ("drums", "bass", "other")
        ]
        stems_for_combine = [s for s in combine_instrumental_stems if s.exists()]
        if not stems_for_combine:
            raise FileNotFoundError("No combined instrumental stems found")
        cmd = ["ffmpeg", "-y"]
        for s in stems_for_combine:
            cmd += ["-i", str(s)]
        cmd += [
            "-filter_complex",
            f"amix=inputs={len(stems_for_combine)}:duration=longest:normalize=0",
            str(instrumental_out),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
