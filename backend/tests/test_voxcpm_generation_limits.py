import pytest
from app.services.voice.generation import validate_generation_length


def test_rejects_output_after_model_badcase_retries_are_exhausted():
    with pytest.raises(ValueError, match='limit'):
        validate_generation_length(61, 10)


def test_rejects_absolute_generation_cap_even_for_long_text():
    with pytest.raises(ValueError, match='limit'):
        validate_generation_length(2000, 1000)


def test_normal_eos_does_not_imply_lexical_verification():
    validate_generation_length(59, 10)
