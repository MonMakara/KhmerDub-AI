from dataclasses import dataclass
from typing import List, Sequence, Optional, Dict, Any, Set
import logging
import math
import re
import subprocess
from pathlib import Path

from app.services.subtitles.checker import get_fonts_dir

logger = logging.getLogger(__name__)


@dataclass
class SubtitleCue:
    """Represents a single timed subtitle cue."""
    sequence: int
    start_time: float
    end_time: float
    text: str


def format_timestamp_srt(seconds: float) -> str:
    """
    Format seconds into SubRip (SRT) timestamp format: HH:MM:SS,mmm
    Example: 65.73 -> "00:01:05,730"
    """
    if seconds is None or math.isnan(seconds) or seconds < 0:
        seconds = 0.0

    total_ms = int(round(seconds * 1000.0))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    s = total_sec % 60
    total_min = total_sec // 60
    m = total_min % 60
    h = total_min // 60

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """
    Format seconds into WebVTT timestamp format: HH:MM:SS.mmm
    Example: 65.73 -> "00:01:05.730"
    """
    if seconds is None or math.isnan(seconds) or seconds < 0:
        seconds = 0.0

    total_ms = int(round(seconds * 1000.0))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    s = total_sec % 60
    total_min = total_sec // 60
    m = total_min % 60
    h = total_min // 60

    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def format_timestamp_ass(seconds: float) -> str:
    """
    Format seconds into SubStation Alpha timestamp format: H:MM:SS.cs
    Example: 65.73 -> "0:01:05.73"
    """
    if seconds is None or math.isnan(seconds) or seconds < 0:
        seconds = 0.0

    total_cs = int(round(seconds * 100.0))
    cs = total_cs % 100
    total_sec = total_cs // 100
    s = total_sec % 60
    total_min = total_sec // 60
    m = total_min % 60
    h = total_min // 60

    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


ASS_STYLE_PRESETS = {
    "tiktok_yellow": {
        "font_name": "Khmer OS Battambang",
        "font_size": 52,
        "primary_color": "&H0000FFFF",  # Vivid yellow (BGR: B=00, G=FF, R=FF)
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",  # Black
        "back_color": "&H80000000",     # Semi-transparent black shadow
        "bold": 0,                      # 0 = Regular (Khmer OS fonts lack bold TTFs; avoids fallback)
        "italic": 0,
        "border_style": 1,              # 1 = outline + drop shadow
        "outline": 3.5,
        "shadow": 1.5,
        "alignment": 2,                 # Bottom center
        "margin_v_vertical": 240,       # 9:16 safe zone
        "margin_v_widescreen": 80,      # 16:9 safe zone
    },
    "classic_white": {
        "font_name": "Khmer OS Battambang",
        "font_size": 48,
        "primary_color": "&H00FFFFFF",  # Pure white
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 0,
        "italic": 0,
        "border_style": 1,
        "outline": 3.2,
        "shadow": 1.5,
        "alignment": 2,
        "margin_v_vertical": 240,
        "margin_v_widescreen": 80,
    },
    "boxed_black": {
        "font_name": "Khmer OS Battambang",
        "font_size": 46,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",     # Opaque box
        "bold": 0,
        "italic": 0,
        "border_style": 3,              # 3 = opaque box
        "outline": 2.0,
        "shadow": 0.0,
        "alignment": 2,
        "margin_v_vertical": 240,
        "margin_v_widescreen": 80,
    },
    "headline_bold": {
        "font_name": "Khmer OS Muol",
        "font_size": 56,
        "primary_color": "&H0020D7FF",  # Gold / Amber
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",
        "back_color": "&H90000000",
        "bold": 0,
        "italic": 0,
        "border_style": 1,
        "outline": 4.0,
        "shadow": 2.0,
        "alignment": 2,
        "margin_v_vertical": 240,
        "margin_v_widescreen": 80,
    },
}

DEFAULT_FALLBACK_FONT = "Noto Sans Khmer"

_INSTALLED_FAMILIES_CACHE: Optional[Set[str]] = None


def get_installed_font_families() -> Set[str]:
    """Retrieve installed font family names from fontconfig and bundled directory."""
    global _INSTALLED_FAMILIES_CACHE
    if _INSTALLED_FAMILIES_CACHE is not None:
        return _INSTALLED_FAMILIES_CACHE

    families: Set[str] = set()
    try:
        res = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                for fam in line.split(","):
                    c = fam.strip()
                    if c:
                        families.add(c)
    except Exception as e:
        logger.warning("Could not execute fc-list to query font families: %s", e)

    # Check bundled fonts directory directly
    fonts_dir = get_fonts_dir()
    if fonts_dir.exists():
        bundled_map = {
            "KhmerOSbattambang.ttf": "Khmer OS Battambang",
            "KhmerOScontent.ttf": "Khmer OS Content",
            "KhmerOSmuol.ttf": "Khmer OS Muol",
            "NotoSansKhmer-Regular.ttf": "Noto Sans Khmer",
            "NotoSansKhmer-Bold.ttf": "Noto Sans Khmer",
            "NotoSerifKhmer-Regular.ttf": "Noto Serif Khmer",
            "NotoSerifKhmer-Bold.ttf": "Noto Serif Khmer",
        }
        for file_name, family_name in bundled_map.items():
            if (fonts_dir / file_name).exists():
                families.add(family_name)

    _INSTALLED_FAMILIES_CACHE = families
    return _INSTALLED_FAMILIES_CACHE


def resolve_khmer_font(requested_font: Optional[str] = None, preset_default: str = "Khmer OS Battambang") -> str:
    """Validate font family against installed fonts. If missing or lacking Khmer coverage,
    log a warning and fall back to Noto Sans Khmer; never fall back to a font without Khmer coverage.
    """
    target = (requested_font or preset_default).strip()
    installed = get_installed_font_families()

    if target in installed:
        return target

    logger.warning(
        "Font '%s' is not installed or lacks verified Khmer coverage. Falling back to '%s'.",
        target,
        DEFAULT_FALLBACK_FONT,
    )
    if DEFAULT_FALLBACK_FONT in installed:
        return DEFAULT_FALLBACK_FONT
    return "Khmer OS Battambang"


def tokenize_khmer_words(text: str) -> List[str]:
    """Tokenize Khmer text into grammatical words using PyICU BreakIterator,
    khmer-nltk, or safe cluster boundary splitting without breaking clusters.
    """
    # 1. Try PyICU BreakIterator (highest precision C++ ICU engine)
    try:
        import icu
        bi = icu.BreakIterator.createWordInstance(icu.Locale("km"))
        bi.setText(text)
        tokens: List[str] = []
        start = bi.first()
        while True:
            try:
                end = next(bi)
            except StopIteration:
                break
            tokens.append(text[start:end])
            start = end
        if tokens:
            return tokens
    except Exception:
        pass

    # 2. Try khmer-nltk (CRF-based morphological segmenter)
    try:
        from khmernltk import word_tokenize
        words = word_tokenize(text, return_tokens=True)
        if words:
            return words
    except Exception:
        pass

    # 3. Fallback: split at spaces
    return text.split(" ")


def wrap_single_line(line: str, max_chars: int = 38) -> str:
    """Wrap a single line at word boundaries or spaces, keeping Unicode clusters intact."""
    if not line or len(line) <= max_chars:
        return line

    is_khmer = bool(re.search(r"[\u1780-\u17ff]", line))
    if not is_khmer:
        # Latin / English wrapping on whitespace
        words = line.split(" ")
        lines: List[str] = []
        curr = ""
        for w in words:
            cand = f"{curr} {w}".strip() if curr else w
            if len(cand) <= max_chars or not curr:
                curr = cand
            else:
                lines.append(curr)
                curr = w
        if curr:
            lines.append(curr)
        return r"\N".join(lines)

    tokens = tokenize_khmer_words(line)
    lines = []
    curr = ""
    for tok in tokens:
        cand = curr + tok
        if len(cand) <= max_chars or not curr:
            curr = cand
        else:
            lines.append(curr.strip())
            curr = tok.lstrip()
    if curr:
        lines.append(curr.strip())
    return r"\N".join(lines)


def wrap_khmer_cue_text(text: str, max_chars: int = 38) -> str:
    """Intelligently wrap text at spaces or word boundaries from ICU BreakIterator,
    inserting explicit \\N in the ASS text and never breaking inside a cluster.
    """
    if not text or len(text) <= max_chars:
        return text

    # Handle existing explicit newlines or line breaks
    normalized = text.replace("\r\n", "\n").replace(r"\N", "\n").replace(r"\n", "\n")
    raw_lines = normalized.split("\n")

    wrapped_lines = [wrap_single_line(l, max_chars=max_chars) for l in raw_lines]
    return r"\N".join(wrapped_lines)


def generate_ass(
    cues: Sequence[SubtitleCue],
    style_name: str = "tiktok_yellow",
    font_name: Optional[str] = None,
    font_size: Optional[int] = None,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    margin_v: Optional[int] = None,
    prevent_overlaps: bool = True,
    filter_empty: bool = True,
) -> str:
    """Generate Advanced SubStation Alpha (.ass) subtitle script with custom typography,
    high-contrast outlines, and viral social safe-zone margins.
    Scaled to real video dimensions via PlayResX and PlayResY.
    """
    sorted_cues = sanitize_and_sort_cues(cues, prevent_overlaps=prevent_overlaps, filter_empty=filter_empty)
    if not sorted_cues:
        return ""

    preset = dict(ASS_STYLE_PRESETS.get(style_name, ASS_STYLE_PRESETS["tiktok_yellow"]))

    # Resolve font family strictly against fc-list / bundled fonts
    preset_font = preset.get("font_name", "Khmer OS Battambang")
    effective_font = resolve_khmer_font(font_name, preset_default=preset_font)
    preset["font_name"] = effective_font

    # MarginV: 240 for 9:16 vertical, 80 for 16:9 widescreen
    if margin_v is not None and margin_v >= 0:
        preset["margin_v"] = margin_v
    elif play_res_y > play_res_x:
        preset["margin_v"] = preset.get("margin_v_vertical", 240)
    else:
        preset["margin_v"] = preset.get("margin_v_widescreen", 80)

    if font_size is not None and font_size > 0:
        preset["font_size"] = font_size

    style_line = (
        f"Style: ViralSubtitle,{preset['font_name']},{preset['font_size']},"
        f"{preset['primary_color']},{preset['secondary_color']},"
        f"{preset['outline_color']},{preset['back_color']},"
        f"{preset['bold']},{preset['italic']},0,0,100,100,0,0,"
        f"{preset['border_style']},{preset['outline']},{preset['shadow']},"
        f"{preset['alignment']},40,40,{preset['margin_v']},1"
    )

    header = [
        "[Script Info]",
        "Title: KhmerDub Viral Subtitles",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events = []
    for cue in sorted_cues:
        start_str = format_timestamp_ass(cue.start_time)
        end_str = format_timestamp_ass(cue.end_time)
        wrapped_text = wrap_khmer_cue_text(cue.text)
        text_escaped = wrapped_text.replace("\r\n", r"\N").replace("\n", r"\N")
        events.append(f"Dialogue: 0,{start_str},{end_str},ViralSubtitle,,0,0,0,,{text_escaped}")

    return "\n".join(header + events) + "\n"


def sanitize_and_sort_cues(
    cues: Sequence[SubtitleCue],
    prevent_overlaps: bool = True,
    filter_empty: bool = True,
) -> List[SubtitleCue]:
    """
    Sanitize, validate, and sort subtitle cues chronologically.
    - Clamps negative timestamps to 0.0.
    - Ensures end_time > start_time (minimum 0.05s duration).
    - Prevents unintended overlaps by clamping end_time to next cue's start_time.
    - Preserves UTF-8 and Khmer Unicode intact.
    """
    valid_cues: List[SubtitleCue] = []

    for cue in cues:
        raw_text = (cue.text or "").strip()
        if filter_empty and not raw_text:
            continue

        start = max(0.0, float(cue.start_time or 0.0))
        end = max(start + 0.05, float(cue.end_time or (start + 1.0)))

        # Normalize line endings to standard LF
        normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        valid_cues.append(
            SubtitleCue(
                sequence=cue.sequence,
                start_time=start,
                end_time=end,
                text=normalized_text,
            )
        )

    # Sort strictly by start_time, then by original sequence
    valid_cues.sort(key=lambda c: (c.start_time, c.sequence))

    # Re-sequence 1..N and handle overlaps if requested
    sanitized: List[SubtitleCue] = []
    for idx, cue in enumerate(valid_cues):
        start = cue.start_time
        end = cue.end_time

        if prevent_overlaps and idx < len(valid_cues) - 1:
            next_start = valid_cues[idx + 1].start_time
            if end > next_start:
                # Clamp end time to next start time with minimal buffer
                end = max(start + 0.05, next_start)

        sanitized.append(
            SubtitleCue(
                sequence=idx + 1,
                start_time=start,
                end_time=end,
                text=cue.text,
            )
        )

    return sanitized


def generate_srt(
    cues: Sequence[SubtitleCue],
    prevent_overlaps: bool = True,
    filter_empty: bool = True,
) -> str:
    """
    Generate SubRip (.srt) formatted subtitle string from cues.
    Strictly conforms to SubRip UTF-8 specification:
      1
      00:00:00,500 --> 00:00:12,500
      Subtitle text here

      2
      00:00:12,500 --> 00:00:29,500
      Next subtitle text
    """
    sorted_cues = sanitize_and_sort_cues(
        cues,
        prevent_overlaps=prevent_overlaps,
        filter_empty=filter_empty,
    )
    if not sorted_cues:
        return ""

    blocks: List[str] = []
    for cue in sorted_cues:
        start_str = format_timestamp_srt(cue.start_time)
        end_str = format_timestamp_srt(cue.end_time)
        block = f"{cue.sequence}\n{start_str} --> {end_str}\n{cue.text}"
        blocks.append(block)

    return "\n\n".join(blocks) + "\n"


def generate_vtt(
    cues: Sequence[SubtitleCue],
    prevent_overlaps: bool = True,
    filter_empty: bool = True,
) -> str:
    """
    Generate WebVTT (.vtt) formatted subtitle string from cues.
    Strictly conforms to W3C WebVTT specification:
      WEBVTT

      1
      00:00:00.500 --> 00:00:12.500
      Subtitle text here

      2
      00:00:12.500 --> 00:00:29.500
      Next subtitle text
    """
    sorted_cues = sanitize_and_sort_cues(
        cues,
        prevent_overlaps=prevent_overlaps,
        filter_empty=filter_empty,
    )
    if not sorted_cues:
        return "WEBVTT\n\n"

    cue_blocks: List[str] = []
    for cue in sorted_cues:
        start_str = format_timestamp_vtt(cue.start_time)
        end_str = format_timestamp_vtt(cue.end_time)
        block = f"{cue.sequence}\n{start_str} --> {end_str}\n{cue.text}"
        cue_blocks.append(block)

    return "WEBVTT\n\n" + "\n\n".join(cue_blocks) + "\n"


def generate_txt(
    cues: Sequence[SubtitleCue],
    filter_empty: bool = True,
) -> str:
    """Generate clean plain text from cues, joining segments into flowing paragraphs."""
    sorted_cues = sanitize_and_sort_cues(cues, prevent_overlaps=False, filter_empty=filter_empty)
    if not sorted_cues:
        return ""
    lines = [cue.text.strip() for cue in sorted_cues if cue.text.strip()]
    return "\n\n".join(lines) + "\n"


def generate_csv(
    cues: Sequence[SubtitleCue],
    filter_empty: bool = True,
) -> str:
    """Generate RFC 4180 CSV string with sequence, start, end, duration, and text."""
    import csv
    import io

    sorted_cues = sanitize_and_sort_cues(cues, prevent_overlaps=False, filter_empty=filter_empty)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "sequence",
        "start_time",
        "end_time",
        "duration_seconds",
        "start_timestamp",
        "end_timestamp",
        "text",
    ])
    for cue in sorted_cues:
        dur = round(max(0.0, cue.end_time - cue.start_time), 2)
        writer.writerow([
            cue.sequence,
            f"{cue.start_time:.2f}",
            f"{cue.end_time:.2f}",
            f"{dur:.2f}",
            format_timestamp_srt(cue.start_time),
            format_timestamp_srt(cue.end_time),
            cue.text,
        ])
    return output.getvalue()
