from dataclasses import dataclass
from typing import List, Sequence, Optional
import math


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
