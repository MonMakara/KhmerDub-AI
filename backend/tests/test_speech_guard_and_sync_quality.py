import math
import subprocess
from pathlib import Path
import pytest

from app.services.dubbing.speech_guard import SpeechGuardService, SafeSilenceBoundary, SpeechInspectionResult
from app.services.dubbing.scheduler import TimelineScheduler, ScheduledPiece
from app.services.dubbing.synchronizer import AudioSynchronizationService


def test_speech_guard_inspection_lexical_unverified(tmp_path: Path):
    """Test that automated inspection always flags lexical status as requiring human listening."""
    guard = SpeechGuardService()

    # Non-existent file
    missing = tmp_path / "nonexistent.mp3"
    res = guard.inspect_speech_audio(missing, expected_text="សួស្តី")
    assert res.is_decodable is False
    assert res.completeness_status == "invalid"
    assert res.lexical_status == "unverified_human_listening_required"

    # Generate a valid tone/sine audio file
    valid_wav = tmp_path / "sine.wav"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1.5",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(valid_wav)
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    res_valid = guard.inspect_speech_audio(valid_wav, expected_text="តេស្តសំឡេងធម្មតា")
    assert res_valid.is_decodable is True
    assert res_valid.is_silent is False
    assert res_valid.completeness_status == "plausibly_complete"
    assert res_valid.lexical_status == "unverified_human_listening_required"


def test_speech_guard_conservative_boundary_detection(tmp_path: Path):
    """Test that boundary detection safely identifies dead silence padding at start/end
    while preserving 60ms speech safety margins and leaving internal pauses completely intact."""
    guard = SpeechGuardService(safety_margin_seconds=0.06)

    # Create audio: 0.3s silence + 1.0s tone + 0.4s internal silence + 1.0s tone + 0.3s silence
    # Total = 3.0s
    padded_wav = tmp_path / "padded.wav"
    filter_expr = (
        "aevalsrc=0:d=0.3[s1];"
        "sine=frequency=440:d=1.0[t1];"
        "aevalsrc=0:d=0.4[s2];"
        "sine=frequency=880:d=1.0[t2];"
        "aevalsrc=0:d=0.3[s3];"
        "[s1][t1][s2][t2][s3]concat=n=5:v=0:a=1[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filter_expr,
        "-map", "[out]",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(padded_wav)
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    boundary = guard.detect_speech_boundaries(padded_wav)
    assert boundary.raw_duration >= 2.95
    # Leading padding is 0.3s. With 0.06s margin, trim_start should be around 0.24s (0.30 - 0.06)
    assert 0.18 <= boundary.trim_start <= 0.26
    # Trailing silence starts at 2.7s. With 0.06s margin, trim_end should be around 2.76s
    assert 2.70 <= boundary.trim_end <= 2.82
    # Internal pause (0.4s between t1 and t2) is NOT stripped!
    # Trimmed duration is roughly 2.76 - 0.24 = ~2.52s (reclaiming ~0.48s of dead boundary padding)
    assert 2.45 <= boundary.trimmed_duration <= 2.60
    assert boundary.has_trimming is True


def test_priority_cascade_natural_vs_boundary_trim_vs_speed_adjustment():
    """Verify Quality-First priority order:
    Priority A: Raw fits slot -> tempo=1.0x, has_boundary_trim=False, status='natural'
    Priority B: Raw exceeds slot, but trimmed fits -> tempo=1.0x, has_boundary_trim=True, status='natural'
    Priority C: Trimmed exceeds slot -> tempo<=1.25x, has_boundary_trim=True, status='speed_adjusted'
    """
    scheduler = TimelineScheduler(max_tempo=1.25, safety_margin_seconds=0.05)

    items = [
        # Segment 1: Raw (1.8s) fits in 2.0s slot -> Priority A (1.0x natural, no trim)
        {
            "segment_order": 1,
            "segment_id": "seg1",
            "start_time": 0.0,
            "end_time": 2.0,
            "orig_duration": 2.0,
            "raw_duration": 1.8,
            "trimmed_duration": 1.6,
            "has_boundary_trim": True,
            "trim_start": 0.1,
            "trim_end": 1.7,
        },
        # Segment 2: Slot is 2.0s (starts at 2.0, next segment at 4.0).
        # Raw (2.2s) exceeds window (2.0s), but trimmed (1.9s) fits window (2.0s) -> Priority B (1.0x natural with trim!)
        {
            "segment_order": 2,
            "segment_id": "seg2",
            "start_time": 2.0,
            "end_time": 4.0,
            "orig_duration": 2.0,
            "raw_duration": 2.2,
            "trimmed_duration": 1.9,
            "has_boundary_trim": True,
            "trim_start": 0.15,
            "trim_end": 2.05,
        },
        # Segment 3: Slot is 2.0s (starts at 4.0, group limit 6.0).
        # Raw (2.6s) and trimmed (2.3s) exceed window (2.0s) -> Priority C (speed adjusted up to 1.25x with trim)
        {
            "segment_order": 3,
            "segment_id": "seg3",
            "start_time": 4.0,
            "end_time": 6.0,
            "orig_duration": 2.0,
            "raw_duration": 2.6,
            "trimmed_duration": 2.3,
            "has_boundary_trim": True,
            "trim_start": 0.15,
            "trim_end": 2.45,
        },
    ]

    groups = scheduler.schedule_timeline(items, target_duration=6.0)
    assert len(groups) >= 1

    all_pieces = [p for g in groups for p in g.pieces]
    assert len(all_pieces) == 3

    p1 = all_pieces[0]
    assert p1.status == "natural"
    assert p1.applied_tempo == 1.0
    assert p1.has_boundary_trim is False

    p2 = all_pieces[1]
    assert p2.status == "natural"
    assert p2.applied_tempo == 1.0
    assert p2.has_boundary_trim is True  # Preserves natural 1.0x voice using safe boundary trim!

    p3 = all_pieces[2]
    assert p3.status == "speed_adjusted"
    assert 1.05 <= p3.applied_tempo <= 1.25
    assert p3.has_boundary_trim is True


def test_honest_unresolved_conflict_reporting():
    """Verify Priority D: Genuine overflow cannot fit even at 1.25x with trimming.
    System honestly reports needs_optimization with non-zero overflow without text deletion or truncation."""
    scheduler = TimelineScheduler(max_tempo=1.25, safety_margin_seconds=0.05)

    items = [
        {
            "segment_order": 1,
            "segment_id": "seg_long",
            "start_time": 0.0,
            "end_time": 2.0,
            "orig_duration": 2.0,
            "raw_duration": 5.0,  # 5.0s in a 2.0s slot
            "trimmed_duration": 4.8,  # Even with trimming, 4.8 / 1.25 = 3.84s >> 2.0s
            "has_boundary_trim": True,
            "trim_start": 0.1,
            "trim_end": 4.9,
            "khmer_text": "អត្ថបទវែងណាស់ដែលមិនអាចបញ្ចូលក្នុងរយៈពេលខ្លីបាន",
        }
    ]

    groups = scheduler.schedule_timeline(items, target_duration=2.5)
    assert len(groups) == 1
    p = groups[0].pieces[0]

    assert p.status == "needs_optimization"
    assert p.overflow_seconds > 0.5
    assert groups[0].group_status == "needs_optimization"
    assert groups[0].group_overflow > 0.5


def test_authoritative_schedule_alignment_and_no_drift(tmp_path: Path):
    """Verify that AudioSynchronizationService strictly adheres to ScheduledPiece.allocated_start,
    guaranteeing zero cumulative drift and an exact match to target_duration."""
    sync_svc = AudioSynchronizationService()

    # Create dummy audio files
    audio1 = tmp_path / "a1.wav"
    audio2 = tmp_path / "a2.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=400:duration=1.0", "-c:a", "pcm_s16le", str(audio1)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=600:duration=1.2", "-c:a", "pcm_s16le", str(audio2)], check=True, capture_output=True)

    items = [
        {"segment_order": 1, "segment_id": "s1", "start_time": 1.0, "end_time": 2.5, "orig_duration": 1.5, "raw_duration": 1.0, "audio_path": audio1},
        {"segment_order": 2, "segment_id": "s2", "start_time": 4.0, "end_time": 5.5, "orig_duration": 1.5, "raw_duration": 1.2, "audio_path": audio2},
    ]

    target_dur = 8.0
    out_timeline = tmp_path / "final_timeline.wav"
    res = sync_svc.synchronize_timed_segments(
        task_id="test_drift",
        segments=items,
        output_timeline_path=out_timeline,
        target_duration=target_dur,
        strict_validation=True,
    )

    assert res.conflicts == []
    # Duration must match target_dur within 0.05s
    assert abs(res.total_duration_seconds - target_dur) <= 0.05


def test_digital_silence_is_rejected_not_marked_complete(tmp_path: Path):
    audio = tmp_path / 'digital_silence.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', '1', str(audio)], check=True)
    result = SpeechGuardService().inspect_speech_audio(audio, expected_text='សួស្តី')
    assert result.is_silent
    assert result.completeness_status == 'invalid'
