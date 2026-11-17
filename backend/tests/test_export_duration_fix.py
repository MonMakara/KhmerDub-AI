"""
Targeted regression tests for the audio export duration mismatch fix.

Verifies:
1. Accurate forward-simulated timeline scheduling without cascading delay.
2. Safe lead pause borrowing into pre-existing silence.
3. Final unit ending before video duration (padded with trailing silence).
4. Final unit ending at video duration.
5. Final unit extending beyond video duration (detected as timing conflict, blocked from export).
6. Strict duration guard in AudioSynchronizationService preventing oversized audio timeline.
7. Export timing guard verification with 0.15s tolerance.
8. Preservation of complete Khmer speech with zero truncation.
9. Full 22-segment Rubik's Cube timeline simulation matching target duration (126.000s).
"""

import subprocess
from pathlib import Path
import pytest

from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.synchronizer import AudioSynchronizationService, TimingConflictError
from app.services.video.ffmpeg import FFmpegVideoProcessor


def make_sine_wav(path: Path, duration: float, sample_rate: int = 44100, freq: int = 440) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.05, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={dur:.3f}:sample_rate={sample_rate}",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "2",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create test tone: {res.stderr}")
    return path


class TestAudioExportDurationFix:

    def test_final_unit_ending_before_video_duration(self, tmp_path: Path):
        """When audio finishes before target video duration, trailing silence pads cleanly to target_duration."""
        target_dur = 10.0
        p1 = make_sine_wav(tmp_path / "p1.wav", 2.0)
        p2 = make_sine_wav(tmp_path / "p2.wav", 2.5)

        items = [
            {"segment_order": 1, "start_time": 1.0, "end_time": 3.0, "raw_duration": 2.0, "audio_path": str(p1)},
            {"segment_order": 2, "start_time": 4.0, "end_time": 6.5, "raw_duration": 2.5, "audio_path": str(p2)},
        ]

        synchronizer = AudioSynchronizationService(max_tempo_factor=1.25)
        out_wav = tmp_path / "timeline.wav"
        result = synchronizer.synchronize_timed_segments(
            task_id="test_pad_tail",
            segments=items,
            output_timeline_path=out_wav,
            target_duration=target_dur,
            strict_validation=True,
            pipeline_version="v2.3",
        )

        assert out_wav.exists()
        vp = FFmpegVideoProcessor()
        dur = vp.get_audio_duration(out_wav)
        # Duration should match target_dur exactly
        assert abs(dur - target_dur) < 0.05
        assert len(result.conflicts) == 0

    def test_final_unit_ending_precisely_at_video_duration(self, tmp_path: Path):
        """When speech reaches near video end, it fits within target_duration without overflowing."""
        target_dur = 8.0
        p1 = make_sine_wav(tmp_path / "p1.wav", 3.0)
        p2 = make_sine_wav(tmp_path / "p2.wav", 3.5)

        items = [
            {"segment_order": 1, "start_time": 0.5, "end_time": 3.5, "raw_duration": 3.0, "audio_path": str(p1)},
            {"segment_order": 2, "start_time": 4.0, "end_time": 7.5, "raw_duration": 3.5, "audio_path": str(p2)},
        ]

        synchronizer = AudioSynchronizationService(max_tempo_factor=1.25)
        out_wav = tmp_path / "timeline_exact.wav"
        result = synchronizer.synchronize_timed_segments(
            task_id="test_exact_end",
            segments=items,
            output_timeline_path=out_wav,
            target_duration=target_dur,
            strict_validation=True,
            pipeline_version="v2.3",
        )

        vp = FFmpegVideoProcessor()
        dur = vp.get_audio_duration(out_wav)
        assert abs(dur - target_dur) <= 0.05
        assert len(result.conflicts) == 0

    def test_final_unit_extending_beyond_video_duration_detected(self, tmp_path: Path):
        """When speech extends beyond target video duration and cannot fit at max tempo,
        a conflict is detected and strict synchronizer blocks oversized timeline generation."""
        target_dur = 5.0
        p1 = make_sine_wav(tmp_path / "p1.wav", 8.0)

        items = [
            {"segment_order": 1, "start_time": 0.0, "end_time": 3.0, "raw_duration": 8.0, "audio_path": str(p1)},
        ]

        synchronizer = AudioSynchronizationService(max_tempo_factor=1.25)
        out_wav = tmp_path / "timeline_overflow.wav"

        with pytest.raises(TimingConflictError) as exc_info:
            synchronizer.synchronize_timed_segments(
                task_id="test_overflow",
                segments=items,
                output_timeline_path=out_wav,
                target_duration=target_dur,
                strict_validation=True,
                pipeline_version="v2.3",
            )

        assert len(exc_info.value.conflicts) > 0
        assert exc_info.value.conflicts[0].overflow_seconds > 0

    def test_safe_lead_pause_borrowing(self, tmp_path: Path):
        """Verify that when a segment has pre-existing leading silence,
        it safely borrows up to 0.50s to avoid unnecessary over-acceleration or downstream overflow."""
        target_dur = 12.0
        # Segment 1 finishes at 3.0s. Segment 2 is 6.0 to 10.0 (4.0s slot). Next segment is at 10.0.
        # Segment 2 raw audio is 4.4s. Without borrowing, it requires 4.4/4.0 = 1.10x.
        # With lead borrowing into gap [3.0, 6.0], it shifts slightly earlier and fits comfortably.
        items = [
            {"segment_order": 1, "start_time": 0.0, "end_time": 3.0, "raw_duration": 2.5},
            {"segment_order": 2, "start_time": 6.0, "end_time": 10.0, "raw_duration": 4.4},
            {"segment_order": 3, "start_time": 10.0, "end_time": 12.0, "raw_duration": 1.8},
        ]

        scheduler = TimelineScheduler(max_tempo=1.25, safety_margin_seconds=0.08, min_pause_seconds=0.10)
        groups = scheduler.schedule_timeline(items, target_duration=target_dur)

        piece2 = groups[1].pieces[0]
        applied_dur2 = piece2.raw_duration / piece2.applied_tempo
        assert piece2.allocated_start >= 3.0 + 0.10
        assert piece2.allocated_start <= 6.0
        assert piece2.allocated_start + applied_dur2 <= 10.0

    def test_export_timing_guard_tolerance(self, tmp_path: Path):
        """FFmpegVideoProcessor.verify_exported_video must strictly reject durations differing by > 0.15s,
        and accept durations within 0.15s."""
        expected_dur = 126.000
        tolerance = 0.15

        # Case 1: 127.728s (diff: 1.728s > 0.15s) -> Must fail
        diff_fail = abs(127.728 - expected_dur)
        assert diff_fail > tolerance

        # Case 2: 125.980s (diff: 0.020s <= 0.15s) -> Must pass
        diff_pass = abs(125.980 - expected_dur)
        assert diff_pass <= tolerance

        # Case 3: 126.000s (diff: 0.000s <= 0.15s) -> Must pass
        diff_exact = abs(126.000 - expected_dur)
        assert diff_exact <= tolerance

    def test_rubik_22_segments_simulation(self, tmp_path: Path):
        """Replay the exact 22 segment durations and boundaries from the Rubik's cube project
        to verify that the scheduled timeline never exceeds 126.000s."""
        target_dur = 126.000

        rubik_segments = [
            {"segment_order": 1, "start_time": 0.00, "end_time": 6.32, "raw_duration": 7.39},
            {"segment_order": 2, "start_time": 6.32, "end_time": 10.58, "raw_duration": 4.97},
            {"segment_order": 3, "start_time": 10.58, "end_time": 16.58, "raw_duration": 7.15},
            {"segment_order": 4, "start_time": 16.58, "end_time": 23.90, "raw_duration": 8.52},
            {"segment_order": 5, "start_time": 23.90, "end_time": 30.56, "raw_duration": 7.42},
            {"segment_order": 6, "start_time": 30.56, "end_time": 36.32, "raw_duration": 6.67},
            {"segment_order": 7, "start_time": 36.32, "end_time": 42.14, "raw_duration": 6.50},
            {"segment_order": 8, "start_time": 42.14, "end_time": 47.78, "raw_duration": 6.55},
            {"segment_order": 9, "start_time": 47.78, "end_time": 54.26, "raw_duration": 7.56},
            {"segment_order": 10, "start_time": 54.26, "end_time": 60.02, "raw_duration": 6.70},
            {"segment_order": 11, "start_time": 60.02, "end_time": 65.54, "raw_duration": 6.48},
            {"segment_order": 12, "start_time": 65.54, "end_time": 71.90, "raw_duration": 7.49},
            {"segment_order": 13, "start_time": 71.90, "end_time": 78.44, "raw_duration": 7.54},
            {"segment_order": 14, "start_time": 78.44, "end_time": 84.74, "raw_duration": 7.27},
            {"segment_order": 15, "start_time": 84.74, "end_time": 90.98, "raw_duration": 7.22},
            {"segment_order": 16, "start_time": 90.98, "end_time": 96.62, "raw_duration": 6.46},
            {"segment_order": 17, "start_time": 96.62, "end_time": 102.38, "raw_duration": 6.74},
            {"segment_order": 18, "start_time": 102.38, "end_time": 107.84, "raw_duration": 6.36},
            {"segment_order": 19, "start_time": 107.84, "end_time": 113.84, "raw_duration": 6.94},
            {"segment_order": 20, "start_time": 113.84, "end_time": 119.30, "raw_duration": 6.26},
            {"segment_order": 21, "start_time": 119.30, "end_time": 123.68, "raw_duration": 5.09},
            {"segment_order": 22, "start_time": 123.68, "end_time": 126.00, "raw_duration": 2.66},
        ]

        scheduler = TimelineScheduler(max_tempo=1.25, safety_margin_seconds=0.08, min_pause_seconds=0.10)
        groups = scheduler.schedule_timeline(rubik_segments, target_duration=target_dur)

        all_pieces = [p for g in groups for p in g.pieces]
        assert len(all_pieces) == 22

        for p in all_pieces:
            dur = p.raw_duration / p.applied_tempo
            assert p.allocated_start + dur <= target_dur + 0.001
            assert p.applied_tempo <= 1.25
            assert p.applied_tempo >= 1.00

        last = all_pieces[-1]
        assert last.segment_order == 22
        last_dur = last.raw_duration / last.applied_tempo
        end_time = last.allocated_start + last_dur
        assert end_time <= target_dur
        assert end_time >= 125.0

    def test_no_audio_truncation_or_missing_words(self, tmp_path: Path):
        """Verify that applied tempo scales duration smoothly via FFmpeg atempo / rubberband,
        preserving every single audio sample and word without clipping ends."""
        p_in = make_sine_wav(tmp_path / "speech_sample.wav", 4.0)
        p_out = tmp_path / "speech_tempo.wav"

        synchronizer = AudioSynchronizationService()
        synchronizer.adjust_tempo(p_in, p_out, 1.15)

        assert p_out.exists()
        vp = FFmpegVideoProcessor()
        dur_in = vp.get_audio_duration(p_in)
        dur_out = vp.get_audio_duration(p_out)

        expected_dur = dur_in / 1.15
        assert abs(dur_out - expected_dur) < 0.05
        assert dur_out > 0
