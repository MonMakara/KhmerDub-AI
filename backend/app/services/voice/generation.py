"""Validation for the installed VoxCPM2 generator's bounded output."""


def validate_generation_length(frame_count: int, text_token_count: int, max_len: int = 2000) -> None:
    """Reject cap exhaustion even when VoxCPM's internal retries return audio.

    VoxCPM2 retries overlong outputs three times, then yields the final bad case.
    Its wrapper provides no EOS flag, so this check only detects known limits;
    passing it cannot establish lexical completeness.
    """
    badcase_limit = max(1, text_token_count) * 6.0
    if frame_count >= min(badcase_limit, max_len - 1):
        raise ValueError("VoxCPM2 generation reached a length/bad-case limit; speech completion requires retry or review.")
