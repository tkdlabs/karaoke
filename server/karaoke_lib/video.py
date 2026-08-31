"""
Video overlay creation for karaoke-style lyrics display.

Two-line display algorithm: always shows the current line (yellow word-by-word
fill) and the upcoming next line (white preview). Lines alternate between top
and bottom positions so they stay in place as they transition from "next" to
"current":

    LINE_1 (current, yellow fill)    <- top
    LINE_2 (next, white)             <- bottom

    LINE_3 (next, white)             <- top      (replaced LINE_1)
    LINE_2 (current, yellow fill)    <- bottom   (stayed in place)

    LINE_3 (current, yellow fill)    <- top      (stayed in place)
    LINE_4 (next, white)             <- bottom   (replaced LINE_2)

Folded into the server from workflows/karaoke (karaoke_workflows) so the
project has no external dependency.
"""

from pathlib import Path

from .lyrics import LyricLine, romanize_korean, validate_lyrics_timing


CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
LATIN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Audio codec mappings for different container formats (video is copied as-is)
AUDIO_CODECS = {
    ".mp4": "aac",
    ".mkv": "aac",
    ".avi": "mp3",
    ".mov": "aac",
    ".webm": "libvorbis",
}


def _make_text_clip(text: str, font_size: int, color: str, stroke_width: int, font: str | None = None):
    """Create a styled TextClip with consistent formatting."""
    from moviepy import TextClip
    return TextClip(
        text=text,
        font_size=font_size,
        color=color,
        font=font or CJK_FONT,
        stroke_color="black",
        stroke_width=stroke_width,
        margin=(10, 20),
    )


def _create_line_overlay(
    line: LyricLine,
    y_pos: float,
    video_width: int,
    font_size: int,
    stroke_width: int,
    display_start: float,
    display_end: float,
    highlight_start: float | None = None,
    highlight_end: float | None = None,
    romanize: bool = True,
) -> list:
    """
    Create moviepy clips for a single lyric line at a given vertical position.

    Args:
        y_pos: bottom edge of the main text area.
        display_start/end: total time the line is visible (white text).
        highlight_start/end: time range for yellow word-by-word fill.
            None means no highlighting (line shown as upcoming preview only).

    Returns a list of moviepy clips (white base, optional romanization,
    optional yellow word highlights).
    """
    clips = []
    display_duration = display_end - display_start
    if display_duration <= 0 or not line.words:
        return clips

    # White base text (shown for entire display duration)
    white_clip = _make_text_clip(line.text, font_size, "white", stroke_width)
    text_height = white_clip.size[1]
    white_clip = white_clip.with_position(("center", y_pos - text_height))
    white_clip = white_clip.with_start(display_start).with_duration(display_duration)
    clips.append(white_clip)

    # Romanization below main text (shown for entire display duration)
    romanized = romanize_korean(line.text) if romanize else None
    if romanized:
        rom_font_size = int(font_size * 0.6)
        rom_stroke = max(1, int(rom_font_size / 16))
        rom_clip = _make_text_clip(romanized, rom_font_size, "cyan", rom_stroke, font=LATIN_FONT)
        rom_clip = rom_clip.with_position(("center", y_pos + int(font_size * 0.2)))
        rom_clip = rom_clip.with_start(display_start).with_duration(display_duration)
        clips.append(rom_clip)

    # Yellow word-by-word highlight (only during "current" phase)
    if highlight_start is not None and highlight_end is not None and highlight_end > highlight_start:
        full_width = white_clip.size[0]
        base_x = (video_width - full_width) / 2

        for word in line.words:
            # Build the progressively-revealed highlighted text
            words_so_far = []
            for w in line.words:
                if w.start_time < word.end_time:
                    words_so_far.append(w.text)
                else:
                    break

            highlighted_text = " ".join(words_so_far)
            if not highlighted_text:
                continue

            yellow_clip = _make_text_clip(highlighted_text, font_size, "yellow", stroke_width)
            yellow_clip = yellow_clip.with_position((base_x, y_pos - text_height))

            remaining = highlight_end - word.start_time
            if remaining > 0:
                yellow_clip = yellow_clip.with_start(word.start_time).with_duration(remaining)
                clips.append(yellow_clip)

    return clips


def create_lyrics_overlay_video(
    video_path: Path,
    audio_path: Path | None,
    lyrics: list[LyricLine],
    output_path: Path,
    resolution: int | None = None,
    duration: float | None = None,
    logger: str | object = "bar",
    romanize: bool = True,
) -> None:
    """Create video with synchronized karaoke-style lyrics overlay.

    When audio_path is None, the output video has no audio track.
    """
    from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip

    print("Creating video with lyrics overlay...")

    lyrics = validate_lyrics_timing(lyrics)
    lyrics = [line for line in lyrics if line.words]

    video = VideoFileClip(str(video_path))
    audio = AudioFileClip(str(audio_path)) if audio_path else None

    if duration is not None:
        video = video.subclipped(0, min(duration, video.duration))
        if audio:
            audio = audio.subclipped(0, min(duration, audio.duration))
        lyrics = [line for line in lyrics if line.start_time < duration]

    if resolution:
        orig_width, orig_height = video.size
        if orig_height > resolution:
            scale_factor = resolution / orig_height
            new_width = int(orig_width * scale_factor)
            new_width = new_width - (new_width % 2)
            new_height = resolution - (resolution % 2)
            video = video.resized((new_width, new_height))
            print(f"Scaling video from {orig_width}x{orig_height} to {new_width}x{new_height}")

    video_width, video_height = video.size
    font_size = int(video_height * 0.05)
    stroke_width = max(1, int(font_size / 16))
    bottom_margin = int(video_height * 0.08)

    # Two-line vertical layout: top and bottom positions
    # Extra spacing when romanization is present to avoid overlap
    has_romanization = romanize and any(romanize_korean(line.text) is not None for line in lyrics)
    line_spacing = int(font_size * (3.3 if has_romanization else 1.6))

    bottom_y = video_height - bottom_margin
    top_y = bottom_y - line_spacing

    # Build overlay clips using the two-line alternating algorithm:
    # Even-indexed lines display at top, odd-indexed at bottom.
    # Each line appears first as "next" (white preview while previous line
    # is current), then transitions to "current" (yellow fill) in place.
    text_clips = []

    for i, line in enumerate(lyrics):
        line_y = top_y if i % 2 == 0 else bottom_y

        # "Current" phase: this line is being sung (yellow highlight active)
        current_start = line.start_time
        current_end = lyrics[i + 1].start_time if i + 1 < len(lyrics) else line.end_time + 0.3

        # Total display: starts earlier as "next" preview while previous line is current
        display_start = lyrics[i - 1].start_time if i > 0 else line.start_time
        display_end = current_end

        text_clips.extend(_create_line_overlay(
            line, line_y, video_width, font_size, stroke_width,
            display_start, display_end,
            highlight_start=current_start,
            highlight_end=current_end,
            romanize=romanize,
        ))

    final = CompositeVideoClip([video] + text_clips)
    if audio:
        final = final.with_audio(audio)

    output_ext = output_path.suffix.lower()
    audio_codec = AUDIO_CODECS.get(output_ext, "aac")
    video_codec = "libvpx" if output_ext == ".webm" else "libx264"

    print("Rendering video with lyrics (this requires re-encoding)...")
    write_kwargs = dict(
        codec=video_codec,
        logger=logger,
    )
    if audio:
        write_kwargs["audio_codec"] = audio_codec
    final.write_videofile(str(output_path), **write_kwargs)

    video.close()
    if audio:
        audio.close()