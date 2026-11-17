import pytest
from app.services.translation.glossary import KhmerGlossary
from app.services.translation.prompts import (
    build_batch_translation_prompt,
    build_single_translation_prompt,
)
from app.services.dubbing.auto_fit import shorten_khmer_text


def test_rubik_terminology_glossary_alignment():
    """Verify Rubik's cube technical terminology is properly protected and corrected."""
    # "cross" hallucinated as transit / crossing
    raw_1 = "តោះធ្វើការឆ្លងកាត់ទាំងអស់"
    aligned_1 = KhmerGlossary.align_terminology("Now let's do that entire cross solution.", raw_1)
    assert "សញ្ញាបូក" in aligned_1
    assert "ឆ្លងកាត់" not in aligned_1

    # "cross" hallucinated as religious crucifix
    raw_2 = "ផ្លាស់ទីឈើឆ្កាងដើម្បីរុញក្រហម"
    aligned_2 = KhmerGlossary.align_terminology("Move the cross so you can get the red into the empty spot", raw_2)
    assert "សញ្ញាបូក" in aligned_2
    assert "ឈើឆ្កាង" not in aligned_2

    # "three move insert" hallucinated as 3 moving persons
    raw_3 = "ជាមួយនឹងអ្នកផ្លាស់ទីទាំងបីដែលខ្ញុំទើបនិយាយ"
    aligned_3 = KhmerGlossary.align_terminology("With the three mover that I just talked about", raw_3)
    assert "៣ ចលនា" in aligned_3
    assert "អ្នកផ្លាស់ទី" not in aligned_3

    # "inspection time"
    raw_4 = "ត្រូវប្រុងប្រយ័ត្នក្នុងអំឡុងពេលត្រួតពិនិត្យ"
    aligned_4 = KhmerGlossary.align_terminology("Look out for this during inspection time", raw_4)
    assert "ពេលពិនិត្យ" in aligned_4

    # "green solids" -> green solved
    raw_5 = "នៅទីនេះយើងមានវត្ថុរឹងពណ៌បៃតង"
    aligned_5 = KhmerGlossary.align_terminology("Here we have green solids", raw_5)
    assert "ពណ៌បៃតងដោះស្រាយរួច" in aligned_5
    assert "វត្ថុរឹង" not in aligned_5


def test_prompts_duration_budget_injection():
    """Verify single and batch prompts inject duration budgets and character guidelines."""
    single_p = build_single_translation_prompt(
        "If you have trouble solving the cross, I'm here to help you.",
        duration=2.68,
    )
    assert "2.7s" in single_p
    assert "recommended maximum" in single_p

    batch_p = build_batch_translation_prompt(
        ["Cross tips", "Inspect the cube"],
        durations=[2.5, 4.0],
    )
    assert "duration_seconds" in batch_p
    assert "max_recommended_khmer_chars" in batch_p
    assert "2.5" in batch_p
    assert "4.0" in batch_p


def test_segment_2_pacing_and_character_reduction():
    """Verify Segment #2 (Rubik's cube intro) can be concisely phrased to fit a ~2.68s slot."""
    verbose_seg2 = "ប្រសិនបើអ្នកមានបញ្ហាក្នុងការដោះស្រាយផ្នែកខ្វែងឱ្យមានប្រសិទ្ធភាពនោះខ្ញុំនៅទីនេះដើម្បីជួយអ្នក។"
    # Target character budget for 2.68s slot (~32 chars)
    shortened = shorten_khmer_text(verbose_seg2, target_char_count=35)
    assert len(shortened) <= 45
    assert "សញ្ញាបូក" in shortened
    assert "ជួយ" in shortened
    assert "ដោះ" in shortened or "ដោះស្រាយ" in shortened


def test_segment_54_and_long_instructions_shortening():
    """Verify Segment #54 (complex 148-character sentence) is compressed while keeping moves intact."""
    verbose_seg54 = "មួយក្នុងចំណោមនោះគឺជាអ្វីដែលខ្ញុំទើបនឹងនិយាយទៅហើយគឺការផ្លាស់ទីឈើឆ្កាងដើម្បីឱ្យអ្នកអាចរុញពណ៌ក្រហមចូលទៅកន្លែងទទេហើយបន្ទាប់មកផ្លាស់ទីឈើឆ្កាងត្រឡប់មកវិញ។"
    shortened = shorten_khmer_text(verbose_seg54, target_char_count=80)
    assert len(shortened) < 100
    assert "សញ្ញាបូក" in shortened
    assert "ក្រហម" in shortened
    assert "ទទេ" in shortened
