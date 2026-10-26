"""Transcript Segmentation Service.

Provides natural sentence-based and dubbing-optimized segmentation of speech-to-text
transcripts using exact Faster-Whisper word-level timestamps.
"""

import logging
import re
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any

from app.services.transcription.base import TranscriptionSegment, WordTiming

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
    if re.search(r"\d\.\d", clean):
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


def _approximate_split_text(
    seg: TranscriptionSegment,
) -> List[TranscriptionSegment]:
    """
    Fallback: split segment text when word-level timestamps are unavailable.
    Calculates proportional start and end times based on character length.
    Marks is_approximate = True.
    """
    text = seg.text.strip()
    # Split on sentence boundaries (e.g. '.', '!', '?') followed by space
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 1:
        return [
            TranscriptionSegment(
                segment_order=seg.segment_order,
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
                words=None,
                is_approximate=True,
                is_manually_edited=seg.is_manually_edited,
            )
        ]

    total_chars = sum(len(s) for s in sentences)
    total_duration = max(0.2, seg.end_time - seg.start_time)
    cursor = seg.start_time
    result: List[TranscriptionSegment] = []

    for idx, s in enumerate(sentences):
        is_last = idx == len(sentences) - 1
        if is_last:
            s_end = seg.end_time
        else:
            proportion = len(s) / max(1, total_chars)
            dur = max(0.3, proportion * total_duration)
            s_end = min(seg.end_time - 0.1 * (len(sentences) - idx - 1), cursor + dur)
            s_end = max(s_end, cursor + 0.1)

        result.append(
            TranscriptionSegment(
                segment_order=idx + 1,
                start_time=round(cursor, 3),
                end_time=round(s_end, 3),
                text=s,
                words=None,
                is_approximate=True,
                is_manually_edited=seg.is_manually_edited,
            )
        )
        cursor = s_end

    return result


def _split_long_words(
    words: List[WordTiming],
    target_min: float = 2.0,
    target_max: float = 6.0,
) -> List[List[WordTiming]]:
    """
    Subdivide a long list of words into chunks targeting target_min to target_max seconds.
    Chooses optimal split points at clause punctuation and natural pauses.
    Never splits mid-word.
    """
    if not words:
        return []

    total_duration = words[-1].end - words[0].start
    if total_duration <= target_max:
        return [words]

    chunks: List[List[WordTiming]] = []
    curr_start_idx = 0
    ideal_duration = (target_min + target_max) / 2.0  # e.g., 4.0s

    while curr_start_idx < len(words):
        remaining_words = len(words) - curr_start_idx
        if remaining_words == 0:
            break

        chunk_start_time = words[curr_start_idx].start
        remaining_duration = words[-1].end - chunk_start_time

        if remaining_duration <= target_max:
            chunks.append(words[curr_start_idx:])
            break

        # Search candidate split index k where curr_start_idx <= k < len(words) - 1
        best_k = -1
        best_score = -1e9

        for k in range(curr_start_idx, len(words) - 1):
            chunk_dur = words[k].end - chunk_start_time
            if chunk_dur < 1.0:
                continue
            if chunk_dur > target_max + 1.5:
                # Stop looking too far past target_max
                break

            # Natural pause between word k and word k+1
            pause = max(0.0, words[k + 1].start - words[k].end)

            # Scoring factors
            score = 0.0
            # Distance penalty from ideal duration
            dist = abs(chunk_dur - ideal_duration)
            score -= dist * 2.0

            # Bonus for natural pause
            if pause >= 0.35:
                score += pause * 15.0
            elif pause >= 0.15:
                score += pause * 5.0

            # Bonus for clause punctuation (comma, semicolon, etc.)
            if is_clause_boundary(words[k].word):
                score += 8.0

            # Conjunction / preposition penalty or bonus
            next_word_clean = words[k + 1].word.strip().lower()
            if next_word_clean in {"and", "but", "because", "so", "which", "that", "while", "when", "although"}:
                score += 3.0

            # Ensure remaining duration is viable
            rem_dur = words[-1].end - words[k + 1].start
            if rem_dur < 1.0:
                score -= 15.0

            if score > best_score:
                best_score = score
                best_k = k

        # Fallback if no candidate within window: pick nearest word around ideal_duration
        if best_k == -1:
            for k in range(curr_start_idx, len(words) - 1):
                chunk_dur = words[k].end - chunk_start_time
                if chunk_dur >= target_min:
                    best_k = k
                    break
            if best_k == -1:
                best_k = len(words) - 1

        chunks.append(words[curr_start_idx : best_k + 1])
        curr_start_idx = best_k + 1

    return chunks


def segment_transcript(
    raw_segments: List[TranscriptionSegment],
    mode: str = "sentence",
    target_min: float = 2.0,
    target_max: float = 6.0,
    max_sentence_duration: float = 12.0,
) -> List[TranscriptionSegment]:
    """
    Main segmentation entry point.

    Modes:
      - 'original': returns raw Faster-Whisper segments unmodified.
      - 'sentence': splits on natural sentence boundaries using exact word timestamps.
      - 'dubbing': dubbing-optimized segmentation targeting 2.0–6.0s durations.
    """
    mode_str = str(mode).lower().strip()
    if mode_str == SegmentationMode.ORIGINAL or mode_str == "original":
        # Preserve original Faster-Whisper segments
        result: List[TranscriptionSegment] = []
        for idx, seg in enumerate(raw_segments, start=1):
            result.append(
                TranscriptionSegment(
                    segment_order=idx,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    text=seg.text,
                    words=seg.words,
                    is_approximate=seg.is_approximate,
                    is_manually_edited=seg.is_manually_edited,
                )
            )
        return result

    # Check if word timestamps are present across segments
    has_any_words = any(seg.words and len(seg.words) > 0 for seg in raw_segments)

    if not has_any_words:
        # Fallback for transcripts without word-level timestamps
        all_approx: List[TranscriptionSegment] = []
        order = 1
        for seg in raw_segments:
            sub_segs = _approximate_split_text(seg)
            for sub in sub_segs:
                sub.segment_order = order
                order += 1
                all_approx.append(sub)
        return all_approx

    # 1. Flatten all words sequentially while tracking raw segment transitions
    all_words: List[WordTiming] = []
    # If some segments lack words, synthesize word items from text
    for seg in raw_segments:
        if seg.words and len(seg.words) > 0:
            for w in seg.words:
                all_words.append(w)
        else:
            # Generate estimated words for segments missing word timestamps
            words_in_text = seg.text.strip().split()
            if words_in_text:
                dur = max(0.1, (seg.end_time - seg.start_time) / len(words_in_text))
                for w_i, w_txt in enumerate(words_in_text):
                    w_start = seg.start_time + w_i * dur
                    w_end = min(seg.end_time, w_start + dur)
                    all_words.append(
                        WordTiming(
                            word=" " + w_txt,
                            start=round(w_start, 3),
                            end=round(w_end, 3),
                            probability=0.8,
                        )
                    )

    if not all_words:
        return []

    # 2. Group words into natural sentence chunks
    sentence_word_chunks: List[List[WordTiming]] = []
    curr_chunk: List[WordTiming] = []

    for i, w in enumerate(all_words):
        curr_chunk.append(w)
        next_w_text = all_words[i + 1].word if i + 1 < len(all_words) else None
        pause_to_next = max(0.0, all_words[i + 1].start - w.end) if i + 1 < len(all_words) else 0.0

        is_ender = is_sentence_boundary(w.word, next_w_text)
        is_large_pause = pause_to_next >= 1.5  # Significant silence indicates sentence end

        if is_ender or is_large_pause or i == len(all_words) - 1:
            if curr_chunk:
                sentence_word_chunks.append(curr_chunk)
                curr_chunk = []

    if curr_chunk:
        sentence_word_chunks.append(curr_chunk)

    final_word_chunks: List[List[WordTiming]] = []

    if mode_str == SegmentationMode.SENTENCE or mode_str == "sentence":
        # Mode: Sentence-Based
        # Split sentences that are extraordinarily long (> max_sentence_duration)
        for s_chunk in sentence_word_chunks:
            dur = s_chunk[-1].end - s_chunk[0].start
            if dur > max_sentence_duration and len(s_chunk) > 4:
                sub_chunks = _split_long_words(s_chunk, target_min=3.0, target_max=max_sentence_duration)
                final_word_chunks.extend(sub_chunks)
            else:
                final_word_chunks.append(s_chunk)

    else:
        # Mode: Dubbing-Optimized
        # Step A: Split long sentences into 2.0-6.0s chunks
        intermediate_chunks: List[List[WordTiming]] = []
        for s_chunk in sentence_word_chunks:
            dur = s_chunk[-1].end - s_chunk[0].start
            if dur > target_max and len(s_chunk) > 3:
                sub_chunks = _split_long_words(s_chunk, target_min=target_min, target_max=target_max)
                intermediate_chunks.extend(sub_chunks)
            else:
                intermediate_chunks.append(s_chunk)

        # Step B: Merge excessively short chunks (< target_min) with adjacent chunks
        # when combined duration <= target_max
        idx = 0
        while idx < len(intermediate_chunks):
            chunk = intermediate_chunks[idx]
            chunk_dur = chunk[-1].end - chunk[0].start

            if chunk_dur < target_min and idx + 1 < len(intermediate_chunks):
                next_chunk = intermediate_chunks[idx + 1]
                combined_dur = next_chunk[-1].end - chunk[0].start
                # Merge if combined duration is within target_max
                if combined_dur <= target_max:
                    merged = chunk + next_chunk
                    final_word_chunks.append(merged)
                    idx += 2
                    continue

            final_word_chunks.append(chunk)
            idx += 1

    # 3. Build output TranscriptionSegments with verified timings
    result_segments: List[TranscriptionSegment] = []
    for order, chunk in enumerate(final_word_chunks, start=1):
        if not chunk:
            continue
        start_t = round(float(chunk[0].start), 3)
        end_t = round(float(chunk[-1].end), 3)

        # Guarantee invariant: start_time < end_time
        if end_t <= start_t:
            end_t = round(start_t + 0.1, 3)

        text = _build_text_from_words(chunk)
        if not text:
            continue

        result_segments.append(
            TranscriptionSegment(
                segment_order=order,
                start_time=start_t,
                end_time=end_t,
                text=text,
                words=chunk,
                is_approximate=False,
                is_manually_edited=False,
            )
        )

    return result_segments


def split_segment_at_word(
    segment: TranscriptionSegment,
    split_index: int,
) -> Tuple[TranscriptionSegment, TranscriptionSegment]:
    """
    Manually split a segment into two segments at a specified word index.
    Preserves exact word timestamps.
    """
    if not segment.words or len(segment.words) < 2:
        # Approximate split by characters
        words = segment.text.split()
        if len(words) < 2:
            raise ValueError("Segment cannot be split: fewer than 2 words")
        split_idx = max(1, min(split_index, len(words) - 1))
        text1 = " ".join(words[:split_idx])
        text2 = " ".join(words[split_idx:])
        mid_time = round(segment.start_time + (segment.end_time - segment.start_time) * (split_idx / len(words)), 3)
        seg1 = TranscriptionSegment(
            segment_order=segment.segment_order,
            start_time=segment.start_time,
            end_time=mid_time,
            text=text1,
            words=None,
            is_approximate=True,
            is_manually_edited=True,
        )
        seg2 = TranscriptionSegment(
            segment_order=segment.segment_order + 1,
            start_time=mid_time,
            end_time=segment.end_time,
            text=text2,
            words=None,
            is_approximate=True,
            is_manually_edited=True,
        )
        return seg1, seg2

    idx = max(1, min(split_index, len(segment.words) - 1))
    chunk1 = segment.words[:idx]
    chunk2 = segment.words[idx:]

    seg1 = TranscriptionSegment(
        segment_order=segment.segment_order,
        start_time=round(float(chunk1[0].start), 3),
        end_time=round(float(chunk1[-1].end), 3),
        text=_build_text_from_words(chunk1),
        words=chunk1,
        is_approximate=segment.is_approximate,
        is_manually_edited=True,
    )
    seg2 = TranscriptionSegment(
        segment_order=segment.segment_order + 1,
        start_time=round(float(chunk2[0].start), 3),
        end_time=round(float(chunk2[-1].end), 3),
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
        is_approximate=seg1.is_approximate or seg2.is_approximate,
        is_manually_edited=True,
    )
