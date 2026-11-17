import re

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
    # Rubik's Cube & Puzzle Mechanical Terminology
    (
        r"\b(?:cross|crosses)\b",
        r"ការឆ្លងកាត់|ឈើឆ្កាង|ឈើចាក់|ឆ្លងកាត់",
        "សញ្ញាបូក",
    ),
    (
        r"\bthree[\s-]move(?:r)?(?:\s+insert)?\b",
        r"អ្នកផ្លាស់ទីទាំងបី|រំកិលបីដង|ការផ្លាស់ទីបីដង",
        "ការបញ្ចូល ៣ ចលនា",
    ),
    (
        r"\binspection(?:\s+time)?\b",
        r"ក្នុងអំឡុងពេលត្រួតពិនិត្យ|ការត្រួតពិនិត្យ",
        "ពេលពិនិត្យ",
    ),
    (
        r"\b(?:first\s+)?pairs?\b",
        r"គូដំបូង",
        "គូទីមួយ",
    ),
    (
        r"\b(?:green|blue|red|orange|white|yellow)\s+solids?\b",
        r"វត្ថុរឹងពណ៌(\S+)",
        r"ពណ៌\1ដោះស្រាយរួច",
    ),
    (
        r"\b([RLUDFB]'?)\s+(?:move|turn)\b",
        r"(?:ការផ្លាស់ទី|ផ្លាស់ទី)\s*([RLUDFB]'?)",
        r"ចលនា \1",
    ),
    # Computer Hardware & Networking (Preserve standard English loanwords if mistranslated)
    (
        r"\bmotherboards?\b",
        r"ក្តារខៀនម្តាយ|មាតាក្តារ|ក្តារមេ|ក្តារខៀនមេ",
        "Motherboard",
    ),
    (
        r"\b(?:network\s+)?switch(?:es)?\b",
        r"កុងតាក់(?!ភ្លើង)|ឧបករណ៍កុងតាក់",
        "Switch",
    ),
    (
        r"\b(?:data\s+|system\s+|expansion\s+|internal\s+)?bus(?:es)?\b",
        r"ឡានក្រុង|រថយន្តក្រុង",
        "Bus",
    ),
    (
        r"\b(?:hardware\s+|network\s+|usb\s+|ethernet\s+)?port(?:s)?\b",
        r"កំពង់ផែ",
        "Port",
    ),
    (
        r"\b(?:cpu\s+)?socket(?:s)?\b",
        r"ព្រីភ្លើង|រន្ធដោតភ្លើង",
        "Socket",
    ),
    (
        r"\brouters?\b",
        r"អ្នកបញ្ជូនផ្លូវ|ឧបករណ៍បញ្ជូនផ្លូវ",
        "Router",
    ),
    (
        r"\bpackets?\b",
        r"កញ្ចប់ឥវ៉ាន់|កញ្ចប់ទំនិញ|កញ្ចប់ប្រៃសណីយ៍",
        "Packet",
    ),
    (
        r"\bcache\b",
        r"ឃ្លាំងសម្ងាត់|ប្រាក់កាស",
        "Cache",
    ),
    (
        r"\b(?:cpu\s+)?registers?\b",
        r"ការចុះឈ្មោះ",
        "Register",
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
