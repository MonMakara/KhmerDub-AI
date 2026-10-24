import re
from typing import List, Tuple

# Domain-specific terminology mapping and hallucination corrections
# Each rule is a tuple: (english_regex, khmer_raw_hallucination_regex, corrected_khmer_replacement)
GLOSSARY_RULES = [
    # AI, Data & Machine Learning technical terminology
    (
        r"\b(?:artificial\s+intelligence|AI)\b",
        r"(?:ស្មារតី\s*)?អចលនទ្រព្យ|ប្រវត្តិវិទ្យា(?:សាស្ត្រ)?|អត្ថន័យ\s*អុីធីធីសែល|ចំណេះដឹង\s*សិប្បកម្ម",
        "បញ្ញាសិប្បនិម្មិត",
    ),
    (
        r"\bdeep\s+learning\b",
        r"ការរៀនជ្រៅ|ការរៀនយ៉ាងជ្រៅ",
        "ការរៀនស៊ីជម្រៅ",
    ),
    (
        r"\bneural\s+networks?\b",
        r"បណ្តាញសរសៃប្រសាទ",
        "បណ្តាញប្រសាទសិប្បនិម្មិត",
    ),
    (
        r"\bhow\s+(?:it|artificial\s+intelligence|AI|this|the\s+system|the\s+algorithm)\s+works?\b",
        r"ធ្វើការ(?!ងារ)",
        "ដំណើរការ",
    ),
    (
        r"\bmachine\s+translation\b",
        r"ការបកប្រែដោយម៉ាស៊ីន|ការបកប្រែម៉ាស៊ីន",
        "ការបកប្រែដោយម៉ាស៊ីន",
    ),
    (
        r"\bopen\s+source\b",
        r"ប្រភពបើក(?!ចំហ)",
        "ប្រភពបើកចំហ",
    ),
    (
        r"\bvideo\s+dubbing\b",
        r"ការចម្លងវីដេអូ",
        "ការបញ្ចូលសំឡេងវីដេអូ",
    ),
    (
        r"\bspeech\s+synthesis\b",
        r"ការបង្កើតសំឡេង",
        "ការសំយោគសំឡេង",
    ),
    (
        r"\bspeech\s+recognition\b",
        r"ការទទួលស្គាល់សំឡេង",
        "ការសម្គាល់សំឡេង",
    ),
    # Greetings & Common Expressions
    (
        r"^\s*good\s+morning\b\s*[,!]?",
        r"^\s*(?:ថ្ងៃអាទិត្យល្អ|ព្រឹកល្អ)\s*[,!]?",
        "អរុណសួស្តី! ",
    ),
    (
        r"^\s*good\s+afternoon\b\s*[,!]?",
        r"^\s*(?:ថ្ងៃត្រង់ល្អ|រសៀលល្អ)\s*[,!]?",
        "ទិវាសួស្តី! ",
    ),
    (
        r"^\s*good\s+evening\b\s*[,!]?",
        r"^\s*ល្ងាចល្អ\s*[,!]?",
        "សាយណ្ហសួស្តី! ",
    ),
    (
        r"^\s*good\s+night\b\s*[,!]?",
        r"^\s*យប់ល្អ\s*[,!]?",
        "រាត្រីសួស្តី! ",
    ),
    (
        r"\bhow\s+are\s+you(?:\s+today)?\b",
        r"តើ\s*អ្នក\s*មាន\s*សុខភាព\s*យ៉ាងម៉េច(?:\s*នៅ\s*ថ្ងៃ\s*នេះ)?|តើ\s*អ្នក\s*មាន\s*ជីវភាព\s*ដូចម្តេច",
        "តើថ្ងៃនេះអ្នកសុខសប្បាយជាទេ",
    ),
    (
        r"\bwelcome\s+to\b",
        r"អញ្ជើញ\s*មក\s*កាន់",
        "សូមស្វាគមន៍មកកាន់",
    ),
]


class KhmerGlossary:
    """Applies terminology alignment and corrects known neural model hallucinations."""

    @classmethod
    def align_terminology(cls, english_source: str, khmer_translation: str) -> str:
        """Correct known mistranslations and terminology in Khmer output based on English context."""
        if not english_source or not khmer_translation:
            return khmer_translation

        result = khmer_translation

        for eng_pattern, khm_pattern, replacement in GLOSSARY_RULES:
            if re.search(eng_pattern, english_source, flags=re.IGNORECASE):
                result = re.sub(khm_pattern, replacement, result)

        return result
