"""Transcript to Text conversion service.

Converts timestamped subtitle/transcript files (.srt, .vtt, .json, .sbv, .ass)
and raw cues into clean, readable plain text, structured narrative paragraphs,
or formatted markdown documents with intelligent pause grouping and speaker handling.
"""
import re
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from app.services.subtitles.parser import ParsedTranscriptResult, parse_transcript_content
from app.services.translation.formatter import KhmerTextFormatter


@dataclass
class ExtractedParagraph:
    index: int
    start_time: float
    end_time: float
    text: str
    speaker: Optional[str] = None
    cue_count: int = 1


@dataclass
class TranscriptToTextResult:
    full_text: str
    paragraphs: List[ExtractedParagraph]
    stats: Dict[str, Any]
    detected_language: str
    target_format: str
    formatted_content: str


def format_seconds_to_timecode(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS readable timestamp string."""
    secs = max(0.0, float(seconds))
    hrs = int(secs // 3600)
    mins = int((secs % 3600) // 60)
    rem_secs = int(secs % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{rem_secs:02d}"
    return f"{mins:02d}:{rem_secs:02d}"


def detect_language(text: str) -> str:
    """Detect whether text is predominantly English, Khmer, or bilingual."""
    km_matches = len(re.findall(r"[\u1780-\u17ff]", text))
    en_matches = len(re.findall(r"[A-Za-z]", text))
    if km_matches > 20 and en_matches > 20:
        return "bilingual"
    if km_matches > en_matches:
        return "km"
    return "en"


def calculate_word_count(text: str, language: str = "en") -> int:
    """Calculate word count respecting language characteristics (e.g. Khmer script without spaces)."""
    clean = (text or "").strip()
    if not clean:
        return 0
    if language == "km":
        clean_no_spaces = clean.replace(" ", "")
        return max(1, round(len(clean_no_spaces) / 3.8))
    # For English or mixed text
    return len(clean.split())


class TranscriptTextExtractor:
    """High-accuracy service for extracting clean text and structured paragraphs from transcripts."""

    def __init__(
        self,
        default_pause_threshold: float = 1.5,
    ):
        self.default_pause_threshold = default_pause_threshold

    def clean_cue_text(
        self,
        raw_text: str,
        strip_tags: bool = True,
        deduplicate: bool = True,
    ) -> Tuple[Optional[str], str]:
        """Strip markup tags, extract speaker labels, and polish text."""
        text = raw_text or ""

        if strip_tags:
            # Strip HTML tags like <font color="...">, <b>, <i>, <v ...>
            text = re.sub(r"<[^>]+>", "", text)
            # Strip ASS/SSA tags like {\an8}, {\pos(100,200)}
            text = re.sub(r"\{[^}]+\}", "", text)

        # Detect speaker label at the beginning
        # Matches patterns like: [SPEAKER_00]:, SPEAKER_01:, Speaker 1:, John Doe:, >> Speaker:
        speaker = None
        speaker_match = re.match(r"^(?:>>\s*)?\[?((?:SPEAKER_\d+|Speaker\s*\d+|[A-Z][A-Za-z0-9_\s]{1,24}))\]?\s*:\s*(.*)$", text, flags=re.DOTALL)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            text = speaker_match.group(2)
        elif text.startswith(">>"):
            text = text.lstrip("> ").strip()

        # Deduplicate consecutive identical words (e.g. "the the" -> "the", "and and" -> "and")
        if deduplicate:
            text = re.sub(r"\b([A-Za-z]+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text).strip()

        # Format Khmer if Khmer script is detected
        if re.search(r"[\u1780-\u17ff]", text):
            text = KhmerTextFormatter.format(text)

        return speaker, text

    def extract_from_content(
        self,
        content: str,
        filename: Optional[str] = "transcript.srt",
        paragraph_mode: str = "smart_paragraphs",
        speaker_handling: str = "strip",
        pause_threshold_seconds: Optional[float] = None,
        deduplicate_phrases: bool = True,
        strip_tags: bool = True,
        target_format: str = "txt",
        title: Optional[str] = "Extracted Transcript",
    ) -> TranscriptToTextResult:
        """Parse transcript content and extract formatted plain text or structured paragraphs."""
        parsed = parse_transcript_content(content, filename=filename)
        return self.extract_from_parsed_segments(
            segments=parsed.segments,
            paragraph_mode=paragraph_mode,
            speaker_handling=speaker_handling,
            pause_threshold_seconds=pause_threshold_seconds,
            deduplicate_phrases=deduplicate_phrases,
            strip_tags=strip_tags,
            target_format=target_format,
            title=title,
        )

    def extract_from_parsed_segments(
        self,
        segments: List[Any],
        paragraph_mode: str = "smart_paragraphs",
        speaker_handling: str = "strip",
        pause_threshold_seconds: Optional[float] = None,
        deduplicate_phrases: bool = True,
        strip_tags: bool = True,
        target_format: str = "txt",
        title: Optional[str] = "Extracted Transcript",
    ) -> TranscriptToTextResult:
        """Convert a list of segment models or dicts into clean structured text."""
        pause_thresh = (
            float(pause_threshold_seconds)
            if pause_threshold_seconds is not None and pause_threshold_seconds > 0
            else self.default_pause_threshold
        )

        cleaned_items = []
        for s in segments:
            raw_t = ""
            if isinstance(s, dict):
                raw_t = s.get("text", "") or s.get("edited_text", "") or s.get("raw_text", "") or ""
            else:
                raw_t = getattr(s, "edited_text", None) or getattr(s, "raw_text", None) or getattr(s, "text", "") or ""

            st = getattr(s, "start_time", 0.0)
            if st is None and isinstance(s, dict):
                st = s.get("start_time", 0.0)
            st = float(st or 0.0)

            et = getattr(s, "end_time", 0.0)
            if et is None and isinstance(s, dict):
                et = s.get("end_time", 0.0)
            et = float(et or (st + 2.0))

            speaker, clean_t = self.clean_cue_text(
                raw_t,
                strip_tags=strip_tags,
                deduplicate=deduplicate_phrases,
            )
            if clean_t:
                cleaned_items.append({
                    "start": st,
                    "end": et,
                    "speaker": speaker,
                    "text": clean_t,
                })

        paragraphs: List[ExtractedParagraph] = []

        if not cleaned_items:
            empty_stats = {
                "word_count": 0,
                "character_count": 0,
                "paragraph_count": 0,
                "cue_count": 0,
                "reading_time_minutes": 0.0,
                "speaking_time_minutes": 0.0,
                "detected_language": "en",
                "paragraph_mode": paragraph_mode,
            }
            return TranscriptToTextResult(
                full_text="",
                paragraphs=[],
                stats=empty_stats,
                detected_language="en",
                target_format=target_format,
                formatted_content="",
            )

        if paragraph_mode == "line_by_line":
            for idx, item in enumerate(cleaned_items, start=1):
                t_str = item["text"]
                if speaker_handling == "keep" and item["speaker"]:
                    t_str = f"{item['speaker']}: {t_str}"
                paragraphs.append(
                    ExtractedParagraph(
                        index=idx,
                        start_time=item["start"],
                        end_time=item["end"],
                        text=t_str,
                        speaker=item["speaker"],
                        cue_count=1,
                    )
                )

        elif paragraph_mode == "timestamped":
            for idx, item in enumerate(cleaned_items, start=1):
                tc = format_seconds_to_timecode(item["start"])
                t_str = item["text"]
                if speaker_handling == "keep" and item["speaker"]:
                    t_str = f"[{tc}] {item['speaker']}: {t_str}"
                else:
                    t_str = f"[{tc}] {t_str}"
                paragraphs.append(
                    ExtractedParagraph(
                        index=idx,
                        start_time=item["start"],
                        end_time=item["end"],
                        text=t_str,
                        speaker=item["speaker"],
                        cue_count=1,
                    )
                )

        elif paragraph_mode == "continuous":
            all_parts = []
            for item in cleaned_items:
                t_str = item["text"]
                if speaker_handling == "keep" and item["speaker"]:
                    t_str = f"{item['speaker']}: {t_str}"
                all_parts.append(t_str)

            # Join parts with natural sentence spacing
            joined_text = " ".join(all_parts)
            joined_text = re.sub(r"\s+", " ", joined_text).strip()
            if re.search(r"[\u1780-\u17ff]", joined_text):
                joined_text = KhmerTextFormatter.format(joined_text)

            paragraphs.append(
                ExtractedParagraph(
                    index=1,
                    start_time=cleaned_items[0]["start"],
                    end_time=cleaned_items[-1]["end"],
                    text=joined_text,
                    speaker=None,
                    cue_count=len(cleaned_items),
                )
            )

        else:
            # Default: smart_paragraphs
            curr_group = [cleaned_items[0]]
            p_groups: List[List[Dict[str, Any]]] = []

            for item in cleaned_items[1:]:
                prev = curr_group[-1]
                pause = max(0.0, item["start"] - prev["end"])
                speaker_changed = (speaker_handling == "keep" and item.get("speaker") != prev.get("speaker"))
                prev_text = prev["text"].strip()
                ended_sentence = bool(prev_text and prev_text[-1] in ".!?។:;\n")
                group_len = sum(len(x["text"]) for x in curr_group)

                # Determine if a paragraph break should occur
                should_break = False
                if speaker_changed:
                    should_break = True
                elif pause >= pause_thresh:
                    should_break = True
                elif ended_sentence and group_len >= 260:
                    should_break = True

                if should_break:
                    p_groups.append(curr_group)
                    curr_group = [item]
                else:
                    curr_group.append(item)

            if curr_group:
                p_groups.append(curr_group)

            for idx, g in enumerate(p_groups, start=1):
                g_start = g[0]["start"]
                g_end = g[-1]["end"]
                g_speaker = g[0]["speaker"]

                parts = []
                for x in g:
                    parts.append(x["text"])

                p_text = " ".join(parts)
                p_text = re.sub(r"\s+", " ", p_text).strip()
                if re.search(r"[\u1780-\u17ff]", p_text):
                    p_text = KhmerTextFormatter.format(p_text)

                if speaker_handling == "keep" and g_speaker:
                    p_text = f"{g_speaker}: {p_text}"

                paragraphs.append(
                    ExtractedParagraph(
                        index=idx,
                        start_time=g_start,
                        end_time=g_end,
                        text=p_text,
                        speaker=g_speaker,
                        cue_count=len(g),
                    )
                )

        # Build full text
        separator = "\n" if paragraph_mode in ("line_by_line", "timestamped") else "\n\n"
        full_text = separator.join(p.text for p in paragraphs)

        # Detect language and compute stats
        lang = detect_language(full_text)
        word_count = calculate_word_count(full_text, lang)
        char_count = len(full_text)
        reading_time = round(word_count / 200.0, 1) if word_count > 0 else 0.0
        speaking_time = round(word_count / 130.0, 1) if word_count > 0 else 0.0

        stats = {
            "word_count": word_count,
            "character_count": char_count,
            "paragraph_count": len(paragraphs),
            "cue_count": len(cleaned_items),
            "reading_time_minutes": reading_time,
            "speaking_time_minutes": speaking_time,
            "detected_language": lang,
            "paragraph_mode": paragraph_mode,
            "speaker_handling": speaker_handling,
        }

        # Build formatted output for target_format
        fmt = (target_format or "txt").strip().lower().lstrip(".")
        if fmt == "md":
            lang_label = "Khmer" if lang == "km" else ("Bilingual (English + Khmer)" if lang == "bilingual" else "English")
            header = (
                f"# {title or 'Extracted Transcript'}\n\n"
                f"> **Word Count:** {word_count} words | "
                f"**Reading Time:** ~{reading_time} min | "
                f"**Language:** {lang_label}\n\n"
                f"---\n\n"
            )
            formatted_content = header + full_text
        elif fmt == "json":
            json_payload = {
                "title": title or "Extracted Transcript",
                "stats": stats,
                "full_text": full_text,
                "paragraphs": [
                    {
                        "index": p.index,
                        "start_time": p.start_time,
                        "end_time": p.end_time,
                        "start_timecode": format_seconds_to_timecode(p.start_time),
                        "end_timecode": format_seconds_to_timecode(p.end_time),
                        "speaker": p.speaker,
                        "cue_count": p.cue_count,
                        "text": p.text,
                    }
                    for p in paragraphs
                ],
            }
            formatted_content = json.dumps(json_payload, ensure_ascii=False, indent=2)
        else:
            formatted_content = full_text

        return TranscriptToTextResult(
            full_text=full_text,
            paragraphs=paragraphs,
            stats=stats,
            detected_language=lang,
            target_format=fmt,
            formatted_content=formatted_content,
        )
