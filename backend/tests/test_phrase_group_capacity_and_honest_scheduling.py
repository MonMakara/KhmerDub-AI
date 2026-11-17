import pytest
from app.services.dubbing.scheduler import TimelineScheduler, ScheduledPiece, ScheduledGroup

def test_phrase_group_placement_and_honest_overflow():
    """Verify that conversational phrase groups correctly schedule audio pieces,
    verify non-overlapping sequential placement, and honestly flag pieces that
    require excess tempo above the ceiling.
    """
    scheduler = TimelineScheduler(max_tempo=1.25, min_pause_seconds=0.08)

    # Segment 1: Slot 7.10s, raw audio 11.54s (needs 9.23s at 1.25x, +1.24s over native effective slot)
    # Segment 2: Slot 7.66s, raw audio 8.66s (needs 6.93s at 1.25x, fits within effective window)
    # Segment 3: Slot 8.02s, raw audio 12.50s (needs 10.00s at 1.25x, +1.43s over native effective slot)
    # Segment 4: Slot 8.92s, raw audio 12.19s (needs 9.75s at 1.25x, +0.88s over native effective slot)
    # Segment 5: Slot 10.06s, raw audio 8.52s (needs only 8.52s at 1.00x, fits natural)
    items = [
        {"segment_order": 28, "start_time": 183.74, "end_time": 190.84, "raw_duration": 11.54},
        {"segment_order": 29, "start_time": 191.78, "end_time": 199.44, "raw_duration": 8.66},
        {"segment_order": 30, "start_time": 199.96, "end_time": 207.98, "raw_duration": 12.50},
        {"segment_order": 31, "start_time": 208.58, "end_time": 217.50, "raw_duration": 12.19},
        {"segment_order": 32, "start_time": 217.50, "end_time": 227.56, "raw_duration": 8.52},
    ]

    groups = scheduler.schedule_timeline(items, target_duration=228.09, max_tempo=1.25)

    # Must form 1 group encompassing the sequence
    assert len(groups) == 1
    g = groups[0]

    # Verify sequential, non-overlapping placement
    for i in range(len(g.pieces) - 1):
        curr_p = g.pieces[i]
        next_p = g.pieces[i + 1]
        assert curr_p.scheduled_end <= next_p.scheduled_start, (
            f"Overlap detected: #{curr_p.segment_order} ends at {curr_p.scheduled_end} "
            f"but #{next_p.segment_order} starts at {next_p.scheduled_start}"
        )

    # Pieces 29 and 32 fit cleanly
    p29 = next(p for p in g.pieces if p.segment_order == 29)
    assert p29.overflow_seconds == 0.0

    p32 = next(p for p in g.pieces if p.segment_order == 32)
    assert p32.status in ("natural", "speed_adjusted")
    assert p32.overflow_seconds == 0.0

    # These takes use neighboring space but the complete measured group fits.
    # Keep alignment review evidence without inventing a physical shortage.
    for order in (28, 30, 31):
        piece = next(p for p in g.pieces if p.segment_order == order)
        assert piece.overflow_seconds == 0
        assert piece.local_overflow_seconds > 0
    assert g.group_overflow == 0

    # Final piece must end before target duration
    last_p = g.pieces[-1]
    assert last_p.scheduled_end <= 228.09

def test_continuous_speech_boundary_not_severed():
    """Verify that zero-gap segments (e.g. piece 31 and 32 with gap=0.0s) are not
    artificially split across group boundaries.
    """
    scheduler = TimelineScheduler(max_tempo=1.25)
    items = [
        {"segment_order": 1, "start_time": 0.0, "end_time": 5.0, "raw_duration": 5.0},
        {"segment_order": 2, "start_time": 5.0, "end_time": 10.0, "raw_duration": 5.0},
        {"segment_order": 3, "start_time": 10.0, "end_time": 15.0, "raw_duration": 5.0},
    ]
    groups = scheduler.schedule_timeline(items, target_duration=20.0)
    assert len(groups) == 1
    assert [p.segment_order for p in groups[0].pieces] == [1, 2, 3]

def test_genuine_group_overflow_reported_honestly():
    """Verify that when a group physically exceeds available time even at max tempo,
    the overflow is honestly attributed without false suppression.
    """
    scheduler = TimelineScheduler(max_tempo=1.25, min_pause_seconds=0.08)
    # Available window: 10.0s. Raw audio: 20.0s. At 1.25x -> 16.0s (exceeds by ~6s).
    items = [
        {"segment_order": 1, "start_time": 0.0, "end_time": 10.0, "raw_duration": 20.0},
    ]
    groups = scheduler.schedule_timeline(items, target_duration=10.0, max_tempo=1.25)
    assert len(groups) == 1
    g = groups[0]
    assert g.group_overflow > 0.05
    assert len(g.pieces) == 1
    p = g.pieces[0]
    assert p.status == "needs_optimization"
    assert p.overflow_seconds > 0.05
