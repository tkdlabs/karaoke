"""Demucs stem separation wrapper.

Extracts audio from video, runs demucs, and produces vocals + instrumental files.
Reuses logic from workflows/karaoke/audio.py.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Active Demucs model, overridable via DEMUCS_MODEL (all Demucs family weights
# are CC-BY-NC 4.0 — see THIRD_PARTY_NOTICES.md).
DEFAULT_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")


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


def run_demucs(input_path: Path, output_dir: Path, model: str = DEFAULT_MODEL) -> Path:
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
        stems_dir = run_demucs(wav_path, tmp_path, model=DEFAULT_MODEL)

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


def separate_multipass(video_path: Path, vocals_out: Path, instrumental_out: Path, passes: int = 2) -> None:
    """Multi-pass Demucs: run N passes to recover leaked instrumental from vocals.

    Each pass re-separates the previous vocals, extracting more leaked content.
    Recovered stems from all passes are summed together.
    """
    if passes < 2:
        raise ValueError("separate_multipass requires passes >= 2")

    vocals_out.parent.mkdir(parents=True, exist_ok=True)
    instrumental_out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # --- Pass 1: original mix ---
        wav_path = tmp_path / "audio.wav"
        extract_audio(video_path, wav_path)
        stems_dirs = [run_demucs(wav_path, tmp_path / "pass1", model=DEFAULT_MODEL)]

        # --- Additional passes: re-separate vocals from previous pass ---
        for p in range(2, passes + 1):
            prev_vocals = stems_dirs[-1] / "vocals.mp3"
            if not prev_vocals.exists():
                raise FileNotFoundError(f"Pass {p - 1} vocals not found at {prev_vocals}")
            stems_dirs.append(run_demucs(prev_vocals, tmp_path / f"pass{p}", model=DEFAULT_MODEL))

        # --- Combine per-instrument stems across all passes ---
        for stem_name in ("drums", "bass", "other"):
            combined = tmp_path / f"{stem_name}_combined.mp3"
            base = stems_dirs[0] / f"{stem_name}.mp3"
            if base.exists():
                shutil.copy2(base, combined)

            for stems_dir in stems_dirs[1:]:
                recovered = stems_dir / f"{stem_name}.mp3"
                if recovered.exists() and combined.exists():
                    temp_sum = tmp_path / f"{stem_name}_temp.mp3"
                    _sum_stems(combined, recovered, temp_sum)
                    shutil.move(str(temp_sum), str(combined))
                elif recovered.exists():
                    shutil.copy2(recovered, combined)

        # --- Final vocals = last pass vocals ---
        last_vocals = stems_dirs[-1] / "vocals.mp3"
        if not last_vocals.exists():
            raise FileNotFoundError(f"Pass {passes} vocals not found at {last_vocals}")
        shutil.copy2(last_vocals, vocals_out)

        # --- Final instrumental = combine all combined stems ---
        combine_stems = [
            tmp_path / f"{s}_combined.mp3" for s in ("drums", "bass", "other")
        ]
        stems_for_combine = [s for s in combine_stems if s.exists()]
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
