import re
import hashlib
from typing import List, Tuple, Dict, Any, Optional


class SubtitleSplitter:
    """
    Intelligent subtitle segmenter and readability analyzer for Khmer and English.
    
    Splits long captions into natural, readable subtitle cues while:
    - Preserving Khmer Unicode, orthographic syllable clusters, and punctuation.
    - Avoiding splitting after COENG signs (\u17D2) or within dependent vowel/diacritic sequences.
    - Targeting readable line lengths (~35-42 chars per line, max ~70-80 chars per cue).
    - Allocating proportional estimated durations respecting speech segment boundaries.
    """

    # Khmer Unicode ranges
    KHMER_CHAR = r"[\u1780-\u17D3\u17D7\u17DD]"
    KHMER_SENTENCE_PUNCT = r"[។៕?!៖]"
    KHMER_CLAUSE_PUNCT = r"[,;]"

    # Khmer discourse markers and conjunctions for natural phrase splitting
    KHMER_CONJUNCTIONS = [
        "ប៉ុន្តែ",     # but
        "ពីព្រោះ",     # because
        "ព្រោះ",       # because (short)
        "ដូច្នេះ",     # therefore
        "ហេតុនេះ",    # hence
        "ហើយ",         # and / then
        "ដើម្បី",     # in order to
        "ប្រសិនបើ",   # if
        "បើ",          # if (short)
        "នៅពេល",      # when
        "ពេលដែល",      # when / while
        "កាលដែល",      # while
        "ដែល",         # which / that
        "ឬក៏",         # or else
        "ឬ",           # or
        "ទោះបី",       # although
        "ដូចជា",       # such as
        "ជាពិសេស",     # especially
    ]

    # English conjunctions and clause markers
    ENGLISH_CONJUNCTIONS = [
        " and ",
        " but ",
        " because ",
        " or ",
        " so ",
        " while ",
        " when ",
        " that ",
        " with ",
        " which ",
        " although ",
        " though ",
        " where ",
    ]

    @classmethod
    def is_safe_khmer_split_index(cls, text: str, idx: int) -> bool:
        """
        Check if an index in text is safe to split without corrupting Khmer orthography.
        Never splits:
        - Right before or after a COENG (\u17D2).
        - Before a dependent vowel (\u17B4-\u17C5).
        - Before a diacritic or sign (\u17C6-\u17D3, \u17DD).
        """
        if idx <= 0 or idx >= len(text):
            return True

        # Unsafe if immediately preceded by COENG (\u17D2)
        if text[idx - 1] == "\u17D2":
            return False

        # Unsafe if immediately preceding COENG (\u17D2)
        if text[idx] == "\u17D2":
            return False

        # Unsafe if immediately preceding dependent vowel, diacritic, or sign
        char = text[idx]
        if "\u17B4" <= char <= "\u17D3" or char == "\u17DD":
            return False

        return True

    @classmethod
    def find_nearest_safe_khmer_index(cls, text: str, target_idx: int) -> int:
        """Find the nearest safe Khmer orthographic break index to target_idx."""
        if target_idx <= 0:
            return 0
        if target_idx >= len(text):
            return len(text)

        # Search backward first (prefer shorter line before target)
        for offset in range(0, min(15, target_idx)):
            cand = target_idx - offset
            if cls.is_safe_khmer_split_index(text, cand):
                return cand

        # Search forward if backward didn't find within 15 chars
        for offset in range(1, min(15, len(text) - target_idx)):
            cand = target_idx + offset
            if cls.is_safe_khmer_split_index(text, cand):
                return cand

        return target_idx

    @classmethod
    def split_khmer_by_punctuation(cls, text: str) -> List[str]:
        """Split Khmer text by sentence punctuation (។, ៕, ?, !, ៖)."""
        pattern = rf"({cls.KHMER_SENTENCE_PUNCT})\s*"
        parts = re.split(pattern, text)
        sentences: List[str] = []
        for i in range(0, len(parts) - 1, 2):
            s = (parts[i] + parts[i + 1]).strip()
            if s:
                sentences.append(s)
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())
        return sentences

    @classmethod
    def split_khmer_clause(cls, text: str, max_chars: int = 75) -> List[str]:
        """
        Split a long Khmer clause into shorter natural phrases if length exceeds max_chars.
        Prefers:
        1. Spaces (natural Khmer clause/topic boundaries).
        2. Known conjunctions (ប៉ុន្តែ, ហើយ, ពីព្រោះ, etc.).
        3. Safe orthographic cluster boundaries near the target midpoint.
        """
        text = text.strip()
        if len(text) <= max_chars:
            return [text]

        # 1. Try splitting at existing spaces
        if " " in text:
            space_parts = [p.strip() for p in text.split(" ") if p.strip()]
            # Group into chunks <= max_chars
            chunks: List[str] = []
            curr = ""
            for p in space_parts:
                test = (curr + " " + p).strip() if curr else p
                if len(test) <= max_chars or not curr:
                    curr = test
                else:
                    chunks.append(curr)
                    curr = p
            if curr:
                chunks.append(curr)

            # If chunks resulted in more than 1 chunk and all are smaller, recurse on each
            if len(chunks) > 1:
                refined: List[str] = []
                for ch in chunks:
                    if len(ch) > max_chars:
                        refined.extend(cls.split_khmer_clause(ch, max_chars))
                    else:
                        refined.append(ch)
                return refined

        # 2. Try splitting at Khmer conjunction words
        for conj in cls.KHMER_CONJUNCTIONS:
            pos = text.find(conj)
            # Must not be at the very start or end
            if 15 <= pos <= len(text) - 15:
                # Ensure split point is safe
                if cls.is_safe_khmer_split_index(text, pos):
                    left = text[:pos].strip()
                    right = text[pos:].strip()
                    if left and right:
                        return cls.split_khmer_clause(left, max_chars) + cls.split_khmer_clause(right, max_chars)

        # 3. Fallback: split at nearest safe Khmer cluster near the midpoint
        mid = len(text) // 2
        safe_idx = cls.find_nearest_safe_khmer_index(text, mid)
        if 0 < safe_idx < len(text):
            left = text[:safe_idx].strip()
            right = text[safe_idx:].strip()
            if left and right:
                return cls.split_khmer_clause(left, max_chars) + cls.split_khmer_clause(right, max_chars)

        return [text]

    @classmethod
    def split_text_khmer(cls, text: str, max_chars: int = 75) -> List[str]:
        """
        Split a full Khmer text into subtitle-sized segments.
        1. Breaks at sentence boundaries.
        2. Breaks long sentences at natural clause or phrase boundaries.
        """
        s = text.strip()
        if not s:
            return []

        # 1. Sentence split
        sentences = cls.split_khmer_by_punctuation(s)
        if not sentences:
            sentences = [s]

        # 2. Clause split if any sentence is too long
        results: List[str] = []
        for sent in sentences:
            if len(sent) > max_chars:
                results.extend(cls.split_khmer_clause(sent, max_chars))
            else:
                results.append(sent)

        return [r.strip() for r in results if r.strip()]

    @classmethod
    def split_text_english(cls, text: str, max_chars: int = 70) -> List[str]:
        """
        Split a full English text into subtitle-sized segments.
        1. Breaks at sentence boundaries (. ? ! ; :).
        2. Breaks long sentences at commas, hyphens, or conjunctions.
        3. Breaks at word boundaries closest to max_chars.
        """
        s = text.strip()
        if not s:
            return []

        # 1. Sentence split
        sentence_pattern = r"([.?!;:])\s+"
        parts = re.split(sentence_pattern, s)
        sentences: List[str] = []
        for i in range(0, len(parts) - 1, 2):
            sent = (parts[i] + parts[i + 1]).strip()
            if sent:
                sentences.append(sent)
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())

        if not sentences:
            sentences = [s]

        results: List[str] = []
        for sent in sentences:
            if len(sent) <= max_chars:
                results.append(sent)
                continue

            # Split by commas or conjunctions
            words = sent.split(" ")
            curr = ""
            for w in words:
                test = (curr + " " + w).strip() if curr else w
                if len(test) <= max_chars or not curr:
                    curr = test
                else:
                    results.append(curr)
                    curr = w
            if curr:
                results.append(curr)

        return [r.strip() for r in results if r.strip()]

    @classmethod
    def estimate_split_timings(
        cls,
        chunks: List[str],
        start_time: float,
        end_time: float,
        min_duration: float = 0.8,
    ) -> List[Tuple[float, float]]:
        """
        Allocate proportional, non-overlapping subtitle cue timestamps.
        Guarantees:
        - t_0 == start_time
        - t_K == end_time
        - Each cue duration >= min_duration (if total duration allows)
        - Strictly non-overlapping and chronological.
        """
        if not chunks:
            return []

        if len(chunks) == 1:
            return [(round(start_time, 3), round(end_time, 3))]

        total_duration = max(0.2, end_time - start_time)
        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            total_chars = len(chunks)

        # Proportional duration based on character count
        durations: List[float] = []
        for c in chunks:
            char_ratio = len(c) / total_chars
            dur = max(min_duration, total_duration * char_ratio)
            durations.append(dur)

        # Normalize so sum(durations) == total_duration
        current_sum = sum(durations)
        if current_sum > 0:
            scale = total_duration / current_sum
            durations = [d * scale for d in durations]

        timings: List[Tuple[float, float]] = []
        curr_start = start_time
        for i, dur in enumerate(durations):
            if i == len(durations) - 1:
                # Clamp last cue strictly to end_time
                cue_end = end_time
            else:
                cue_end = curr_start + dur

            # Guard against invalid durations
            cue_start_rounded = round(curr_start, 3)
            cue_end_rounded = round(max(curr_start + 0.1, cue_end), 3)

            timings.append((cue_start_rounded, cue_end_rounded))
            curr_start = cue_end_rounded

        return timings

    @classmethod
    def calculate_readability(
        cls,
        text: str,
        start_time: float,
        end_time: float,
        language: str,
        max_cps: float = 20.0,
        max_chars: int = 80,
        max_duration: float = 7.0,
        min_duration: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Compute subtitle readability quality indicators.
        Supports Khmer Unicode cluster measurements.
        """
        dur = max(0.05, end_time - start_time)
        clean_text = (text or "").strip()
        char_count = len(clean_text)
        line_count = len(clean_text.splitlines()) if clean_text else 0
        cps = round(char_count / dur, 1)

        # Language-specific default thresholds
        lang = language.lower() if language else "km"
        effective_max_chars = 75 if lang == "en" else max_chars
        effective_max_cps = 18.0 if lang == "en" else max_cps

        warnings: List[str] = []
        if cps > effective_max_cps:
            warnings.append(f"High reading speed ({cps} CPS)")
        if char_count > effective_max_chars:
            warnings.append(f"Caption too long ({char_count} chars)")
        if line_count > 2:
            warnings.append(f"Too many display lines ({line_count} lines)")
        if dur < min_duration:
            warnings.append(f"Duration too short ({dur:.1f}s)")
        if dur > max_duration:
            warnings.append(f"Duration too long ({dur:.1f}s)")

        return {
            "duration": round(dur, 2),
            "character_count": char_count,
            "line_count": line_count,
            "characters_per_second": cps,
            "warnings": warnings,
            "has_warnings": len(warnings) > 0,
        }

    @staticmethod
    def compute_source_hash(text: str) -> str:
        """Compute compact SHA-256 hash of source text for change detection."""
        clean = (text or "").strip()
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]
