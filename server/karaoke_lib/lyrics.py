"""
Lyrics data models, parsing, and utilities.

Supports LRC (standard and enhanced), SRT, VTT, and simple word-timed formats.
Folded into the server from workflows/karaoke (karaoke_workflows) so the
project has no external dependency.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# Korean romanization support (optional)
try:
    from korean_romanizer.romanizer import Romanizer
    HAS_KOREAN_ROMANIZER = True
except ImportError:
    HAS_KOREAN_ROMANIZER = False


def romanize_korean(text: str) -> str | None:
    """
    Romanize Korean (Hangul) text to Latin characters.
    Returns None if no Korean characters present or library not available.
    """
    if not HAS_KOREAN_ROMANIZER:
        return None

    # Check if text contains Korean characters (Hangul range: AC00-D7AF)
    has_korean = any('\uAC00' <= char <= '\uD7AF' for char in text)
    if not has_korean:
        return None

    try:
        r = Romanizer(text)
        return r.romanize()
    except Exception:
        return None


@dataclass
class LyricWord:
    """A single word with timing information."""
    text: str
    start_time: float  # seconds
    end_time: float    # seconds


@dataclass
class LyricLine:
    """A line of lyrics with word-level timing."""
    words: list[LyricWord]

    @property
    def start_time(self) -> float:
        return self.words[0].start_time if self.words else 0.0

    @property
    def end_time(self) -> float:
        return self.words[-1].end_time if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def parse_lyrics_file(lyrics_path: Path) -> list[LyricLine]:
    """
    Parse lyrics file with word-level timestamps.

    Supported formats:
    1. Enhanced LRC with word timestamps:
       [00:12.34]<00:12.34>Hello <00:12.80>world <00:13.20>today

    2. Simple word-timed format (one word per line):
       0.00-0.50 Hello
       0.50-1.20 world

    3. Line-timed LRC (words will be evenly distributed):
       [00:12.34]Hello world today

    4. SRT subtitle format:
       1
       00:00:12,340 --> 00:00:15,670
       Hello world today

    5. VTT (WebVTT) subtitle format:
       WEBVTT

       00:00:12.340 --> 00:00:15.670
       Hello world today
    """
    content = lyrics_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    lyrics: list[LyricLine] = []

    # Detect format based on file extension first, then content
    ext = lyrics_path.suffix.lower()

    if ext == ".srt":
        lyrics = _parse_srt(content)
    elif ext == ".vtt":
        lyrics = _parse_vtt(content)
    elif ext == ".lrc" or lines and re.match(r"^\[\d+:\d+", lines[0]):
        # LRC format (by extension or content)
        if any("<" in line for line in lines):
            lyrics = _parse_enhanced_lrc(lines)
        else:
            lyrics = _parse_standard_lrc(lines)
    elif lines and re.match(r"^\d+\.\d+-\d+\.\d+\s+", lines[0]):
        # Simple word-timed format
        lyrics = _parse_simple_word_timed(lines)
    elif "WEBVTT" in content[:50]:
        # VTT without extension
        lyrics = _parse_vtt(content)
    elif re.search(r"\d+\s*\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", content):
        # SRT without extension
        lyrics = _parse_srt(content)
    else:
        # Default to standard LRC
        lyrics = _parse_standard_lrc(lines)

    return lyrics


def parse_lyrics_content(content: str) -> list[LyricLine]:
    """Parse LRC lyrics content from a string (same formats as parse_lyrics_file)."""
    lines = content.strip().split("\n")

    if any("<" in line for line in lines):
        return _parse_enhanced_lrc(lines)
    return _parse_standard_lrc(lines)


def apply_lyrics_offset(lyrics: list[LyricLine], offset: float) -> list[LyricLine]:
    """
    Shift all lyrics timestamps by offset seconds.

    Positive offset delays lyrics (e.g., 1.5 shows lyrics 1.5s later).
    Negative offset shows lyrics earlier.
    Lines that would start before 0 are clamped to 0.
    """
    if offset == 0.0:
        return lyrics

    shifted = []
    for line in lyrics:
        words = [
            LyricWord(
                text=w.text,
                start_time=max(0.0, w.start_time + offset),
                end_time=max(0.0, w.end_time + offset),
            )
            for w in line.words
        ]
        # Drop lines where all words ended up at 0
        if words and words[-1].end_time > 0.0:
            shifted.append(LyricLine(words=words))

    return shifted


def validate_lyrics_timing(lyrics: list[LyricLine]) -> list[LyricLine]:
    """
    Validate and fix overlapping lyrics timelines.

    Returns corrected lyrics where each line ends before the next begins.
    """
    if not lyrics:
        return lyrics

    corrected = []
    for i, line in enumerate(lyrics):
        if not line.words:
            continue

        # Check if this line overlaps with next
        if i + 1 < len(lyrics):
            next_start = lyrics[i + 1].start_time
            if line.end_time > next_start:
                print(f"  Warning: Line {i+1} overlaps with next line "
                      f"({line.end_time:.2f}s > {next_start:.2f}s): \"{line.text[:30]}...\"")
                # Adjust the last word's end time
                adjusted_words = list(line.words)
                if adjusted_words:
                    last_word = adjusted_words[-1]
                    adjusted_words[-1] = LyricWord(
                        text=last_word.text,
                        start_time=last_word.start_time,
                        end_time=min(last_word.end_time, next_start - 0.05),
                    )
                corrected.append(LyricLine(words=adjusted_words))
            else:
                corrected.append(line)
        else:
            corrected.append(line)

    return corrected


def format_duration(seconds: int | float) -> str:
    """Format seconds as m:ss."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


# --- Internal parsing functions ---


def _parse_time(time_str: str) -> float:
    """Parse time string like '00:12.34' or '12.34' to seconds."""
    time_str = time_str.strip("[]<>")
    if ":" in time_str:
        parts = time_str.split(":")
        if len(parts) == 2:
            minutes, seconds = parts
            return float(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    return float(time_str)


def _parse_srt_time(time_str: str) -> float:
    """Parse SRT time format: '00:00:12,340' to seconds."""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    return float(time_str)


def _parse_simple_word_timed(lines: list[str]) -> list[LyricLine]:
    """Parse simple format: '0.00-0.50 Hello'"""
    words: list[LyricWord] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+\.?\d*)-(\d+\.?\d*)\s+(.+)$", line)
        if match:
            start, end, text = match.groups()
            words.append(LyricWord(text=text, start_time=float(start), end_time=float(end)))

    # Group words into lines based on gaps
    return _group_words_into_lines(words)


def _parse_enhanced_lrc(lines: list[str]) -> list[LyricLine]:
    """Parse enhanced LRC: '[00:12.34]<00:12.34>Hello <00:12.80>world'"""
    lyrics: list[LyricLine] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("[ti:") or line.startswith("[ar:"):
            continue

        # Extract line start time
        line_time_match = re.match(r"^\[(\d+:\d+\.?\d*)\](.*)$", line)
        if not line_time_match:
            continue

        line_start = _parse_time(line_time_match.group(1))
        rest = line_time_match.group(2)

        # Parse word timestamps
        words: list[LyricWord] = []
        word_pattern = re.compile(r"<(\d+:\d+\.?\d*)>([^<]+)")
        matches = list(word_pattern.finditer(rest))

        if matches:
            for i, match in enumerate(matches):
                start = _parse_time(match.group(1))
                text = match.group(2).strip()
                # End time is start of next word or estimate
                if i + 1 < len(matches):
                    end = _parse_time(matches[i + 1].group(1))
                else:
                    end = start + 0.5  # Default word duration
                if text:
                    words.append(LyricWord(text=text, start_time=start, end_time=end))
        else:
            # No word timestamps, treat as standard line
            text = rest.strip()
            if text:
                words.append(LyricWord(text=text, start_time=line_start, end_time=line_start + 3.0))

        if words:
            lyrics.append(LyricLine(words=words))

    return lyrics


def _parse_standard_lrc(lines: list[str]) -> list[LyricLine]:
    """Parse standard LRC, distributing words evenly across line duration."""
    lyrics: list[LyricLine] = []
    parsed_lines: list[tuple[float, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match [mm:ss.xx] or [mm:ss] format
        match = re.match(r"^\[(\d+:\d+\.?\d*)\](.*)$", line)
        if match:
            time = _parse_time(match.group(1))
            text = match.group(2).strip()
            if text:
                parsed_lines.append((time, text))

    # Calculate durations and create word timings
    for i, (start_time, text) in enumerate(parsed_lines):
        # End time is start of next line or +4 seconds
        if i + 1 < len(parsed_lines):
            end_time = parsed_lines[i + 1][0]
        else:
            end_time = start_time + 4.0

        # Distribute words evenly
        word_texts = text.split()
        if not word_texts:
            continue

        duration = end_time - start_time
        word_duration = duration / len(word_texts)

        words: list[LyricWord] = []
        for j, word_text in enumerate(word_texts):
            word_start = start_time + j * word_duration
            word_end = word_start + word_duration
            words.append(LyricWord(text=word_text, start_time=word_start, end_time=word_end))

        lyrics.append(LyricLine(words=words))

    return lyrics


def _parse_srt(content: str) -> list[LyricLine]:
    """
    Parse SRT subtitle format.

    Format:
        1
        00:00:12,340 --> 00:00:15,670
        Hello world today
    """
    lyrics: list[LyricLine] = []
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # Find the timestamp line (skip sequence number)
        timestamp_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if "-->" in line:
                timestamp_line = line
                text_lines = lines[i + 1:]
                break

        if not timestamp_line:
            continue

        # Parse timestamps
        match = re.match(r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})", timestamp_line)
        if not match:
            continue

        start_time = _parse_srt_time(match.group(1))
        end_time = _parse_srt_time(match.group(2))

        # Combine text lines and strip HTML tags
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text)  # Remove HTML tags like <i>, </i>
        text = text.strip()

        if not text:
            continue

        # Distribute words evenly across the duration
        word_texts = text.split()
        if not word_texts:
            continue

        duration = end_time - start_time
        word_duration = duration / len(word_texts)

        words: list[LyricWord] = []
        for j, word_text in enumerate(word_texts):
            word_start = start_time + j * word_duration
            word_end = word_start + word_duration
            words.append(LyricWord(text=word_text, start_time=word_start, end_time=word_end))

        lyrics.append(LyricLine(words=words))

    return lyrics


def _parse_vtt(content: str) -> list[LyricLine]:
    """
    Parse WebVTT subtitle format.

    Format:
        WEBVTT

        00:00:12.340 --> 00:00:15.670
        Hello world today
    """
    # Remove WEBVTT header and any metadata
    content = re.sub(r"^WEBVTT.*?\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^NOTE.*?\n\n", "", content, flags=re.MULTILINE | re.DOTALL)

    lyrics: list[LyricLine] = []
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        # Find the timestamp line (may have optional cue identifier before it)
        timestamp_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if "-->" in line:
                timestamp_line = line
                text_lines = lines[i + 1:]
                break

        if not timestamp_line:
            continue

        # Parse timestamps (VTT uses . instead of ,)
        # Also handle optional cue settings after timestamps
        match = re.match(r"(\d{2}:\d{2}[:\.][\d\.]+)\s*-->\s*(\d{2}:\d{2}[:\.][\d\.]+)", timestamp_line)
        if not match:
            continue

        start_time = _parse_srt_time(match.group(1))
        end_time = _parse_srt_time(match.group(2))

        # Combine text lines and strip HTML/VTT tags
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text)  # Remove tags like <v>, <c>, etc.
        text = text.strip()

        if not text:
            continue

        # Distribute words evenly across the duration
        word_texts = text.split()
        if not word_texts:
            continue

        duration = end_time - start_time
        word_duration = duration / len(word_texts)

        words: list[LyricWord] = []
        for j, word_text in enumerate(word_texts):
            word_start = start_time + j * word_duration
            word_end = word_start + word_duration
            words.append(LyricWord(text=word_text, start_time=word_start, end_time=word_end))

        lyrics.append(LyricLine(words=words))

    return lyrics


def _group_words_into_lines(words: list[LyricWord], gap_threshold: float = 1.0) -> list[LyricLine]:
    """Group words into lines based on time gaps."""
    if not words:
        return []

    lines: list[LyricLine] = []
    current_line: list[LyricWord] = [words[0]]

    for i in range(1, len(words)):
        gap = words[i].start_time - words[i - 1].end_time
        if gap > gap_threshold:
            lines.append(LyricLine(words=current_line))
            current_line = []
        current_line.append(words[i])

    if current_line:
        lines.append(LyricLine(words=current_line))

    return lines