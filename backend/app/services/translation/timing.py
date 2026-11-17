"""Conservative translation budgets reserve pauses before TTS is measured."""


def speaking_budget(start: float, end: float, next_start: float | None = None) -> float:
    duration = max(.1, end - start)
    # Long visual pauses are not an invitation to produce verbose translation.
    window = duration if next_start is None else min(duration + .35, max(.1, next_start - start))
    return max(.1, round(window - .13, 3))
