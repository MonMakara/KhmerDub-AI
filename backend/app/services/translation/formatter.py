import re
from typing import Optional


class KhmerTextFormatter:
    """Natural text formatter for Khmer script.

    Standard Khmer orthography is a scriptio continua writing system where words
    within a clause are written continuously without inter-word spacing.
    Spaces in Khmer represent clause/sentence boundaries or separate foreign words/numbers.

    This formatter:
    1. Removes artificial word-level spaces inserted by neural subword tokenizers (like SentencePiece).
    2. Preserves meaningful spaces around Latin/English terms (e.g. 'KhmerDub AI').
    3. Preserves meaningful spaces around numerical figures (e.g. '100 នាក់').
    4. Attaches Khmer and Western punctuation marks to the preceding word without leading space.
    5. Preserves trailing spaces after punctuation marks separating clauses or sentences.
    6. Preserves valid Khmer Unicode encoding without corruption.
    """

    # Khmer character ranges
    KHMER_CHAR = r"[\u1780-\u17D3\u17D7\u17DD]"
    KHMER_PUNCT = r"[\u17D4-\u17DA]"
    KHMER_DIGIT = r"[\u17E0-\u17E9]"
    ALL_PUNCT_ATTACH = r"[!?,;:\u17D4\u17D5\u17D6\u17D7\u17D8\u17D9\u17DA]"
    SENTENCE_END_PUNCT = r"[!?,;:\u17D4\u17D5]"

    # Standard Khmer conjunctions and phrase markers that require clause spacing in Cambodian orthography
    KHMER_PHRASE_MARKERS = [
        "ដើម្បី",      # in order to / to
        "ប៉ុន្តែ",      # but
        "ពីព្រោះ",      # because
        "ដូច្នេះ",      # therefore
        "ដូចនេះ",      # thus
        "ហេតុនេះ",     # hence
        "ប្រសិនបើ",    # if
        "ដូចជា",       # such as
        "ជាពិសេស",     # especially
        "ទោះបីជា",     # although
        "ទោះជា",       # even if
        "ព្រមទាំង",     # as well as
        "ឬក៏",        # or
        "និង",        # and
    ]

    @classmethod
    def format(cls, text: Optional[str]) -> str:
        """Format raw Khmer text into natural Cambodian orthography."""
        if not text:
            return ""

        s = text.strip()
        if not s:
            return ""

        # Step 1: Normalize all multiple whitespace characters to a single space
        s = re.sub(r"[ \t\r\n]+", " ", s)

        # Step 2: Remove spaces immediately preceding punctuation marks
        # In Khmer, punctuation clings directly to the preceding word
        s = re.sub(rf"\s+({cls.ALL_PUNCT_ATTACH})", r"\1", s)

        # Step 3: Ensure a single space after sentence-ending punctuation when followed by another word
        s = re.sub(rf"({cls.SENTENCE_END_PUNCT})([^\s0-9])", r"\1 \2", s)

        # Step 4: Collapse unnatural word-level spaces between pure Khmer characters
        # e.g., 'វីដេអូ នេះ ពន្យល់' -> 'វីដេអូនេះពន្យល់'
        # Perform twice to handle overlapping regex capture groups
        s = re.sub(rf"({cls.KHMER_CHAR})\s+({cls.KHMER_CHAR})", r"\1\2", s)
        s = re.sub(rf"({cls.KHMER_CHAR})\s+({cls.KHMER_CHAR})", r"\1\2", s)

        # Step 4b: Ensure standard Cambodian phrase-boundary spacing before conjunctions and clause markers
        for marker in cls.KHMER_PHRASE_MARKERS:
            s = re.sub(rf"({cls.KHMER_CHAR})({marker})", r"\1 \2", s)

        # Step 5: Ensure space between Khmer text and Latin/English alphanumeric words
        # e.g., 'មកកាន់KhmerDub' -> 'មកកាន់ KhmerDub'
        # e.g., 'AIវីដេអូ' -> 'AI វីដេអូ'
        latin_word = r"[A-Za-z]"
        s = re.sub(rf"({cls.KHMER_CHAR})({latin_word})", r"\1 \2", s)
        s = re.sub(rf"({latin_word})({cls.KHMER_CHAR})", r"\1 \2", s)

        # Step 6: Ensure space between Khmer text and Arabic/ASCII digits
        # e.g., 'មាន10នាក់' -> 'មាន 10 នាក់'
        ascii_digit = r"[0-9]"
        s = re.sub(rf"({cls.KHMER_CHAR})({ascii_digit})", r"\1 \2", s)
        s = re.sub(rf"({ascii_digit})({cls.KHMER_CHAR})", r"\1 \2", s)

        # Step 7: Clean up any double spaces that may have been created
        s = re.sub(r"[ \t]+", " ", s)

        return s.strip()
