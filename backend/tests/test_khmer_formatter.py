from app.services.translation.formatter import KhmerTextFormatter


def test_empty_and_whitespace_inputs():
    assert KhmerTextFormatter.format("") == ""
    assert KhmerTextFormatter.format("   ") == ""
    assert KhmerTextFormatter.format(None) == ""


def test_pure_khmer_spacing_compaction():
    raw = "វីដេអូ នេះ ពន្យល់ អំពី របៀប ដែល ដំណើរការ។"
    expected = "វីដេអូនេះពន្យល់អំពីរបៀបដែលដំណើរការ។"
    assert KhmerTextFormatter.format(raw) == expected


def test_punctuation_spacing_attachment():
    # In Khmer, punctuation must cling to preceding word without space,
    # with a space after if followed by the next sentence.
    raw = "សួស្តី ! តើ អ្នក សុខសប្បាយ ទេ ? ខ្ញុំ សុខសប្បាយ ។"
    formatted = KhmerTextFormatter.format(raw)
    assert formatted == "សួស្តី! តើអ្នកសុខសប្បាយទេ? ខ្ញុំសុខសប្បាយ។"


def test_latin_english_term_preservation():
    # Spacing between Khmer words and English terms must be preserved
    raw = "សួស្តី អញ្ជើញ មក កាន់ KhmerDub AI"
    formatted = KhmerTextFormatter.format(raw)
    assert formatted == "សួស្តីអញ្ជើញមកកាន់ KhmerDub AI"
    assert "KhmerDub AI" in formatted


def test_numbers_preservation():
    raw = "មាន 10 នាក់ កំពុង ប្រើប្រាស់ កម្មវិធី Python 3 នេះ។"
    formatted = KhmerTextFormatter.format(raw)
    assert "10" in formatted
    assert "Python 3" in formatted
    assert formatted == "មាន 10 នាក់កំពុងប្រើប្រាស់កម្មវិធី Python 3 នេះ។"


def test_khmer_repetition_mark_leka():
    # Khmer repetition sign ៗ
    raw = "ឆ្ងាញ់ ៗ ណាស់ ។"
    formatted = KhmerTextFormatter.format(raw)
    assert formatted == "ឆ្ងាញ់ៗណាស់។"


def test_non_khmer_passthrough():
    # Pure English text should retain normal spaces
    english = "Hello world from KhmerDub AI."
    assert KhmerTextFormatter.format(english) == "Hello world from KhmerDub AI."


def test_conjunction_and_clause_spacing():
    # Conjunctions like ដើម្បី (in order to) and និង (and) must have clause spacing
    raw = "វិស្វករប្រើគណិតវិទ្យាដើម្បីសាងសង់ហេដ្ឋារចនាសម្ព័ន្ធនិងទូរគមនាគមន៍។"
    formatted = KhmerTextFormatter.format(raw)
    assert formatted == "វិស្វករប្រើគណិតវិទ្យា ដើម្បីសាងសង់ហេដ្ឋារចនាសម្ព័ន្ធ និងទូរគមនាគមន៍។"

