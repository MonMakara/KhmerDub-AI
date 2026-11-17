"""Subtitle and transcript parsing utilities for AI Media Toolkit."""

import re
from dataclasses import dataclass, field
from typing import List, Optional


class TranscriptParseError(Exception):
    """Raised when transcript content is malformed or invalid."""
    pass


@dataclass
class ParsedTranscriptSegment:
    segment_order: int
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@dataclass
class ParsedTranscriptResult:
    format: str  # "srt", "vtt", or "text"
    has_timestamps: bool
    segments: List[ParsedTranscriptSegment] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


TIMESTAMP_REGEX = re.compile(
    r'(-?)(?:(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3}))\s*-->\s*(-?)(?:(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3}))[^\n]*\n?'
)
HTML_TAG_REGEX = re.compile(r'<[^>]+>')


def parse_timestamp_components(sign: str, h: Optional[str], m: str, s: str, ms: str) -> float:
    """Convert timestamp components into floating point seconds, preserving sign."""
    hours = int(h) if h is not None else 0
    mins = int(m)
    secs = int(s)
    millis = int(ms.ljust(3, '0')[:3])
    val = round(hours * 3600.0 + mins * 60.0 + secs + millis / 1000.0, 3)
    return -val if sign == '-' else val


def clean_cue_text(text: str) -> str:
    """Clean subtitle cue text: strip HTML/VTT tags and normalize whitespace."""
    if not text:
        return ""
    cleaned = HTML_TAG_REGEX.sub('', text)
    # Remove WebVTT cue annotations if present on lines
    cleaned = re.sub(r'^(NOTE|REGION|STYLE)\b.*$', '', cleaned, flags=re.MULTILINE)
    # Normalize multiple whitespace / newlines
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    return " ".join(lines).strip()


def parse_transcript_content(content: str, filename: Optional[str] = None) -> ParsedTranscriptResult:
    """
    Parse transcript content from SRT, WebVTT, or plain text.
    Preserves segment order, timestamps, and UTF-8/Khmer Unicode text.
    Validates timestamps (start >= 0, end > start, sequential ordering).
    """
    if not content or not content.strip():
        raise TranscriptParseError("Transcript content is empty.")

    # Remove UTF-8 BOM if present
    clean_content = content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')

    # Detect file type or content signature
    fname_lower = (filename or "").lower()
    is_vtt_header = clean_content.startswith("WEBVTT")
    has_cue_arrows = "-->" in clean_content

    if not has_cue_arrows and not is_vtt_header and not fname_lower.endswith((".srt", ".vtt")):
        # Plain text mode without timestamps
        # Split into non-empty lines
        raw_lines = [l.strip() for l in clean_content.splitlines() if l.strip()]
        if not raw_lines:
            raise TranscriptParseError("No readable text found in input.")

        segments: List[ParsedTranscriptSegment] = []
        for idx, line in enumerate(raw_lines, start=1):
            segments.append(
                ParsedTranscriptSegment(
                    segment_order=idx,
                    text=line,
                    start_time=None,
                    end_time=None,
                )
            )

        return ParsedTranscriptResult(
            format="text",
            has_timestamps=False,
            segments=segments,
            warnings=["Plain text parsed without timestamps. Narration Mode is selected by default."],
        )

    # Subtitle mode: SRT or WebVTT
    fmt = "vtt" if (is_vtt_header or fname_lower.endswith(".vtt")) else "srt"
    matches = list(TIMESTAMP_REGEX.finditer(clean_content))

    if not matches:
        raise TranscriptParseError(
            f"Malformed {fmt.upper()} content: No valid timestamp intervals found (e.g. 00:00:01,000 --> 00:00:04,000)."
        )

    segments: List[ParsedTranscriptSegment] = []
    warnings: List[str] = []
    prev_end = 0.0

    for idx, match in enumerate(matches, start=1):
        g = match.groups()
        start = parse_timestamp_components(g[0], g[1], g[2], g[3], g[4])
        end = parse_timestamp_components(g[5], g[6], g[7], g[8], g[9])

        if start < 0:
            raise TranscriptParseError(
                f"Segment #{idx}: Negative timestamp ({start:.3f}s) is invalid. Negative timestamps are rejected."
            )

        if end <= start:
            raise TranscriptParseError(
                f"Segment #{idx}: End time ({end:.3f}s) must exceed start time ({start:.3f}s). Invalid interval."
            )

        if start < prev_end:
            warnings.append(
                f"Segment #{idx}: Start time ({start:.3f}s) overlaps with preceding segment end ({prev_end:.3f}s)."
            )

        prev_end = max(prev_end, end)

        # Extract cue text between current match end and next match start
        content_start = match.end()
        content_end = matches[idx].start() if idx < len(matches) else len(clean_content)
        raw_block = clean_content[content_start:content_end].strip()

        # Strip optional trailing cue index line (e.g., standalone number before the next cue)
        block_lines = [l.strip() for l in raw_block.splitlines() if l.strip()]
        if idx < len(matches) and block_lines and block_lines[-1].isdigit():
            block_lines = block_lines[:-1]

        cue_raw = "\n".join(block_lines)
        cue_text = clean_cue_text(cue_raw)

        if not cue_text:
            warnings.append(f"Segment #{idx}: Cue contains empty speech text.")

        segments.append(
            ParsedTranscriptSegment(
                segment_order=idx,
                text=cue_text,
                start_time=start,
                end_time=end,
            )
        )

    if not segments:
        raise TranscriptParseError(f"No valid speech cues found in {fmt.upper()} transcript.")

    return ParsedTranscriptResult(
        format=fmt,
        has_timestamps=True,
        segments=segments,
        warnings=warnings,
    )
