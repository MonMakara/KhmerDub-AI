"""Transcript Segmentation Service.

Provides natural sentence-based and dubbing-optimized segmentation of speech-to-text
transcripts using exact Faster-Whisper word-level timestamps.
"""

import logging
import math
import uuid
from collections import Counter
from dataclasses import replace
import re
from enum import Enum
from typing import List, Optional, Tuple

from app.services.transcription.base import (
    TranscriptionSegment, WordTiming, identify_source_words,
)

logger = logging.getLogger(__name__)

# Known abbreviations that do NOT constitute sentence boundaries
COMMON_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "i.e.", "e.g.", "no.", "vol.", "approx.", "dept.", "est.", "inc.",
    "ltd.", "co.", "corp.", "st.", "gen.", "col.", "sgt.", "capt.",
    "u.s.", "u.k.", "e.u.", "u.s.a.", "a.m.", "p.m."
}

# Clause boundary punctuation
CLAUSE_PUNCTUATION_REGEX = re.compile(r"[,;:\-—–]$")
SENTENCE_TERMINATOR_REGEX = re.compile(r"(\.|\!|\?|\.{3})$")

# Grammatical tokens that should NEVER end a speech segment (prepositions, articles, conjunctions)
GRAMMATICAL_INCOMPLETE_WORDS = {
    "the", "a", "an", "of", "to", "in", "on", "at", "by", "for", "with",
    "from", "into", "through", "toward", "towards", "against", "between", "among",
    "under", "over", "and", "but", "or", "so", "as", "than",
    "where", "which", "who", "that", "if", "when", "while", "though", "although"
}


class SegmentationMode(str, Enum):
    ORIGINAL = "original"
    SENTENCE = "sentence"
    DUBBING = "dubbing"


def is_sentence_boundary(word: str, next_word: Optional[str] = None) -> bool:
    """
    Determine if a word token represents a genuine sentence boundary.
    Handles attached punctuation, trailing quotes/brackets, abbreviations,
    acronyms, and numbers.
    """
    if not word:
        return False

    clean = word.strip().rstrip("\"'”)»]")
    if not clean:
        return False

    lower = clean.lower()

    # 1. Abbreviations check
    if lower in COMMON_ABBREVIATIONS:
        return False

    # 2. Single initial (e.g., 'J. K. Rowling')
    if re.match(r"^[A-Za-z]\.$", clean):
        return False

    # 3. Acronyms (e.g., 'U.S.A.', 'I.B.M.')
    if re.match(r"^([A-Za-z]\.)+$", clean):
        return False

    # 4. Decimals or currency (e.g., '3.14', '$1.50')
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)+", clean):
        return False

    # 5. Check if clean word ends with sentence terminator (. ! ? or ...)
    if SENTENCE_TERMINATOR_REGEX.search(clean):
        return True

    return False


def is_clause_boundary(word: str) -> bool:
    """Check if word ends with clause punctuation (comma, semicolon, colon, dash)."""
    if not word:
        return False
    clean = word.strip().rstrip("\"'”)»]")
    return bool(CLAUSE_PUNCTUATION_REGEX.search(clean))


def _build_text_from_words(words: List[WordTiming]) -> str:
    """Reconstruct clean sentence text from a list of WordTiming objects."""
    if not words:
        return ""
    has_spaces = any(" " in w.word for w in words)
    if has_spaces:
        raw = "".join(w.word for w in words).strip()
    else:
        raw = " ".join(w.word.strip() for w in words)
    return re.sub(r"\s+", " ", raw).strip()


# These expressions must remain intact even when a soft duration target is exceeded.
PROTECTED_EXPRESSIONS = (
    ("rubik's", "cube"), ("rubik’s", "cube"), ("rubiks", "cube"),
    ("rubik", "cube"), ("three", "move", "insert"),
    ("two", "look", "oll"), ("two", "look", "pll"),
    ("f2l", "pair"), ("wide", "turn"), ("quarter", "turn"),
    ("half", "turn"), ("artificial", "intelligence"),
    ("machine", "learning"), ("deep", "learning"), ("neural", "network"),
)
INCOMPLETE_ENDINGS = GRAMMATICAL_INCOMPLETE_WORDS | {
    "my", "your", "his", "her", "our", "their", "its", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "will", "would",
    "could", "should", "can", "must", "not", "very", "has", "have", "had",
}
UNITS = {"seconds", "second", "minutes", "minute", "hours", "hour", "ms", "s",
         "meters", "metres", "cm", "mm", "kg", "grams", "degrees", "percent", "%"}
NOTATION = re.compile(r"^[URFDLBMESxyzurfdlb](?:w)?(?:2|['’′])?$")


def _token(word: str) -> str:
    return word.strip().strip('"“”()[]{}.,;:!?').lower()


def _can_split(words: List[WordTiming], index: int) -> bool:
    """Hard exclusions for an expression or overlapping ASR evidence."""
    left, right = words[index], words[index + 1]
    if left.end > right.start:
        return False
    if (NOTATION.fullmatch(left.word.strip().strip(",;()"))
            and NOTATION.fullmatch(right.word.strip().strip(",;()"))):
        return False
    tokens = [_token(w.word) for w in words]
    if tokens[index] in INCOMPLETE_ENDINGS and not is_sentence_boundary(left.word):
        return False
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", tokens[index]) and tokens[index + 1] in UNITS:
        return False
    for expression in PROTECTED_EXPRESSIONS:
        for start in range(max(0, index - len(expression) + 2), index + 1):
            if (tuple(tokens[start:start + len(expression)]) == expression
                    and start <= index < start + len(expression) - 1):
                return False
    return True


def _approximate_split_text(seg: TranscriptionSegment) -> List[TranscriptionSegment]:
    """Unaligned legacy text keeps its recorded interval; no estimated word times."""
    return [replace(seg, is_approximate=True)]


def _split_long_words(
    words: List[WordTiming], target_min: float = 1.0, target_max: float = 4.2,
) -> List[List[WordTiming]]:
    """Choose complete phrase boundaries near three seconds, preserving every token."""
    chunks = []
    cursor = 0
    while cursor < len(words):
        if words[-1].end - words[cursor].start <= target_max:
            chunks.append(words[cursor:])
            break
        candidates = []
        for index in range(cursor, len(words) - 1):
            if not _can_split(words, index):
                continue
            duration = words[index].end - words[cursor].start
            if duration <= 0:
                continue
            if duration > target_max:
                if not candidates:
                    # A protected expression may legitimately exceed target max.
                    candidates.append((-1000.0 - duration, index))
                break
            pause = max(0.0, words[index + 1].start - words[index].end)
            remaining = words[-1].end - words[index + 1].start
            score = -abs(duration - 2.8) * 2.5
            score += 3.0 if is_clause_boundary(words[index].word) else 0.0
            score += min(pause, 0.8) * 6.0
            if _token(words[index + 1].word) in {"and", "but", "because", "when", "while"}:
                score += 1.2
            if duration < target_min:
                score -= 10.0
            if remaining < 1.0:
                score -= 12.0
            candidates.append((score, index))
        split = max(candidates)[1] + 1 if candidates else len(words)
        chunks.append(words[cursor:split])
        cursor = split
    return chunks


def validate_word_coverage(
    raw_segments: List[TranscriptionSegment], segments: List[TranscriptionSegment],
) -> dict[str, int | bool]:
    """Validate occurrence IDs and order, independently of repeated word strings."""
    raw = identify_source_words(raw_segments)
    expected = [w.word_id for s in raw for w in s.words or []]
    assigned = [w.word_id for s in segments for w in s.words or []]
    expected_counts, assigned_counts = Counter(expected), Counter(assigned)
    missing = list((expected_counts - assigned_counts).elements())
    extra = list((assigned_counts - expected_counts).elements())
    duplicates = [identifier for identifier, count in assigned_counts.items() if count > 1]
    if missing or extra or duplicates or expected != assigned:
        raise ValueError("Segmentation changed source word coverage or order")
    return {"source_words": len(expected), "assigned_words": len(assigned),
            "unassigned_words": len(missing), "duplicate_words": len(duplicates),
            "word_order_preserved": expected == assigned}


def segment_transcript(
    raw_segments: List[TranscriptionSegment], mode: str = "sentence",
    target_min: float = 1.0, target_max: float = 4.2,
    max_sentence_duration: float = 4.2,
) -> List[TranscriptionSegment]:
    """Short original-timed phrases; transcript boundaries stay independent of TTS."""
    mode_name = str(getattr(mode, "value", mode)).lower().strip()
    if mode_name not in {"original", "sentence", "dubbing"}:
        raise ValueError(f"Unsupported segmentation mode: {mode}")
    if target_min <= 0 or target_max < target_min or max_sentence_duration <= 0:
        raise ValueError("Invalid segmentation duration targets")
    raw = identify_source_words(raw_segments)
    if mode_name == "original":
        return [replace(s, segment_order=i) for i, s in enumerate(raw, 1)]

    # Process aligned runs without estimating times for intervening unaligned text.
    result = []
    run = []

    def flush_run() -> None:
        if not run:
            return
        words = [w for segment in run for w in segment.words or []]
        sentences = []
        current = []
        pause_threshold = 0.32 if mode_name == "dubbing" else 0.45
        for index, word in enumerate(words):
            current.append(word)
            last = index == len(words) - 1
            pause = words[index + 1].start - word.end if not last else 0.0
            tail_end = next((candidate.end for candidate in words[index + 1:]
                             if is_sentence_boundary(candidate.word)), words[-1].end)
            tail_duration = tail_end - words[index + 1].start if not last else 0.0
            curr_dur = word.end - current[0].start
            natural_pause = (not last and pause >= pause_threshold
                             and tail_duration >= target_min
                             and curr_dur >= target_min
                             and _can_split(words, index))
            sentence_end = is_sentence_boundary(word.word) and (
                last or _can_split(words, index)
            )
            # Natural clause boundary split (commas, semicolons, dashes) for short, natural breath segments
            clause_split = (
                not last
                and is_clause_boundary(word.word)
                and (pause >= 0.20 or curr_dur >= 2.2)
                and curr_dur >= target_min
                and tail_duration >= target_min
                and _can_split(words, index)
            )
            if last or sentence_end or natural_pause or clause_split:
                sentences.append(current)
                current = []
        limit = min(target_max, max_sentence_duration) if mode_name == "sentence" else target_max
        for sentence in sentences:
            for chunk in _split_long_words(sentence, target_min, limit):
                uncertain = any(
                    w.is_uncertain or w.end <= w.start or not math.isfinite(w.start + w.end)
                    for w in chunk
                )
                source = next(s for s in run if any(w.word_id == chunk[0].word_id for w in s.words or []))
                identity = str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(w.word_id for w in chunk)))
                result.append(TranscriptionSegment(
                    segment_order=0, start_time=chunk[0].start, end_time=chunk[-1].end,
                    text=_build_text_from_words(chunk), words=chunk,
                    is_approximate=uncertain or source.is_approximate,
                    id=identity, source_audio_reference=source.source_audio_reference,
                ))
        run.clear()

    for segment in raw:
        if segment.words and not segment.is_manually_edited:
            run.append(segment)
        else:
            flush_run()
            result.extend(_approximate_split_text(segment))
    flush_run()
    for order, segment in enumerate(result, 1):
        segment.segment_order = order
    validate_word_coverage(raw, result)
    return result


def split_segment_at_word(
    segment: TranscriptionSegment,
    split_index: int,
) -> Tuple[TranscriptionSegment, TranscriptionSegment]:
    """
    Manually split a segment into two segments at a specified word index.
    Preserves exact word timestamps.
    """
    if not segment.words or len(segment.words) < 2:
        raise ValueError("Word alignment is unavailable; source audio alignment is required before splitting")

    if segment.is_manually_edited and _build_text_from_words(segment.words) != segment.text.strip():
        raise ValueError(
            "Edited text differs from aligned source words; realignment is required before splitting"
        )

    idx = max(1, min(split_index, len(segment.words) - 1))
    chunk1 = segment.words[:idx]
    chunk2 = segment.words[idx:]

    seg1 = TranscriptionSegment(
        segment_order=segment.segment_order,
        start_time=float(chunk1[0].start),
        end_time=float(chunk1[-1].end),
        text=_build_text_from_words(chunk1),
        words=chunk1,
        is_approximate=segment.is_approximate,
        is_manually_edited=True,
    )
    seg2 = TranscriptionSegment(
        segment_order=segment.segment_order + 1,
        start_time=float(chunk2[0].start),
        end_time=float(chunk2[-1].end),
        text=_build_text_from_words(chunk2),
        words=chunk2,
        is_approximate=segment.is_approximate,
        is_manually_edited=True,
    )
    return seg1, seg2


def merge_adjacent_segments(
    seg1: TranscriptionSegment,
    seg2: TranscriptionSegment,
) -> TranscriptionSegment:
    """
    Manually merge two adjacent segments into a single segment.
    """
    merged_words: Optional[List[WordTiming]] = None
    if seg1.words and seg2.words:
        merged_words = seg1.words + seg2.words
    elif seg1.words:
        merged_words = seg1.words
    elif seg2.words:
        merged_words = seg2.words

    merged_text = f"{seg1.text.strip()} {seg2.text.strip()}"
    return TranscriptionSegment(
        segment_order=seg1.segment_order,
        start_time=min(seg1.start_time, seg2.start_time),
        end_time=max(seg1.end_time, seg2.end_time),
        text=merged_text,
        words=merged_words,
        is_approximate=seg1.is_approximate or seg2.is_approximate or not (seg1.words and seg2.words),
        is_manually_edited=True,
    )
