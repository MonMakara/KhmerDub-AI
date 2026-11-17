import pytest
from pathlib import Path
import tempfile
import shutil
import math
from unittest.mock import MagicMock

from app.services.dubbing.scheduler import TimelineScheduler, ScheduledPiece
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.video.ffmpeg import FFmpegVideoProcessor


class TestIntelligentPerSegmentSpeed:
    """Tests verifying intelligent per-segment speech speed optimization:
    1. Naturally fitting segments remain at 1.00x.
    2. Only overflowing segments are accelerated (1.01x - 1.25x).
    3. Overflows > 1.25x are capped safely at 1.25x and reported honestly.
    4. No innocent segments in groups are accelerated due to adjacent overflow.
    5. Pure pitch-preserving time stretching with micro-fades.
    """

    def test_naturally_fitting_segments_remain_unaccelerated(self):
        """Naturally fitting segments must remain at 1.00x speaking speed."""
        scheduler = TimelineScheduler(max_tempo=1.25)
        items = [
            {
                "idx": 0,
                "segment_order": 1,
                "segment_id": "seg_1",
                "start_time": 0.0,
                "end_time": 4.0,
                "orig_duration": 4.0,
                "raw_duration": 3.2,  # Fits naturally in 4.0s
                "trimmed_duration": 3.2,
            },
            {
                "idx": 1,
                "segment_order": 2,
                "segment_id": "seg_2",
                "start_time": 5.0,
                "end_time": 8.0,
                "orig_duration": 3.0,
                "raw_duration": 2.5,  # Fits naturally in 3.0s
                "trimmed_duration": 2.5,
            },
        ]
        groups = scheduler.schedule_timeline(items, target_duration=10.0)
        pieces = [p for g in groups for p in g.pieces]
        assert len(pieces) == 2

        p1 = pieces[0]
        assert p1.status == "natural"
        assert p1.applied_tempo == 1.0
        assert p1.overflow_seconds == 0.0

        p2 = pieces[1]
        assert p2.status == "natural"
        assert p2.applied_tempo == 1.0
        assert p2.overflow_seconds == 0.0

    def test_overflowing_segments_accelerate_minimally(self):
        """Only speech segments that exceed their available window are accelerated (1.01x - 1.25x)."""
        scheduler = TimelineScheduler(max_tempo=1.25)
        items = [
            {
                "idx": 0,
                "segment_order": 1,
                "segment_id": "seg_1",
                "start_time": 0.0,
                "end_time": 4.0,
                "orig_duration": 4.0,
                "raw_duration": 3.0,  # Natural
                "trimmed_duration": 3.0,
            },
            {
                "idx": 1,
                "segment_order": 2,
                "segment_id": "seg_2",
                "start_time": 4.5,
                "end_time": 7.0,
                "orig_duration": 2.5,
                "raw_duration": 2.85,  # Exceeds slot (2.5s) before next segment at 7.0s
                "trimmed_duration": 2.85,
            },
            {
                "idx": 2,
                "segment_order": 3,
                "segment_id": "seg_3",
                "start_time": 7.0,
                "end_time": 10.0,
                "orig_duration": 3.0,
                "raw_duration": 2.5,
                "trimmed_duration": 2.5,
            },
        ]
        groups = scheduler.schedule_timeline(items, target_duration=10.0)
        pieces = [p for g in groups for p in g.pieces]

        p1 = pieces[0]
        assert p1.status == "natural"
        assert p1.applied_tempo == 1.0

        p2 = pieces[1]
        assert p2.status == "speed_adjusted"
        assert 1.01 <= p2.applied_tempo <= 1.25
        assert p2.overflow_seconds == 0.0

    def test_excessive_shortages_capped_at_safe_max(self):
        """Segments requiring >1.25x are capped safely at 1.25x and report true shortages."""
        scheduler = TimelineScheduler(max_tempo=1.25)
        items = [
            {
                "idx": 0,
                "segment_order": 1,
                "segment_id": "seg_1",
                "start_time": 0.0,
                "end_time": 3.0,
                "orig_duration": 3.0,
                "raw_duration": 6.0,  # Requires 2.0x in a 3.0s window -> exceeds 1.25x cap!
                "trimmed_duration": 6.0,
            },
            {
                "idx": 1,
                "segment_order": 2,
                "segment_id": "seg_2",
                "start_time": 3.0,
                "end_time": 6.0,
                "orig_duration": 3.0,
                "raw_duration": 2.5,
                "trimmed_duration": 2.5,
            },
        ]
        groups = scheduler.schedule_timeline(items, target_duration=6.0)
        p = groups[0].pieces[0]

        assert p.status == "needs_optimization"
        assert p.applied_tempo == 1.25
        assert p.overflow_seconds > 0.5

    def test_no_indiscriminate_acceleration_in_groups(self):
        """When an adjacent segment in a group overflows, naturally fitting segments must NOT be sped up."""
        scheduler = TimelineScheduler(max_tempo=1.25)
        items = [
            {
                "idx": 0,
                "segment_order": 1,
                "segment_id": "seg_1",
                "start_time": 0.0,
                "end_time": 2.0,
                "orig_duration": 2.0,
                "raw_duration": 4.5,  # Huge overflow in seg 1
                "trimmed_duration": 4.5,
            },
            {
                "idx": 1,
                "segment_order": 2,
                "segment_id": "seg_2",
                "start_time": 2.1,  # Close gap, conversational group
                "end_time": 5.0,
                "orig_duration": 2.9,
                "raw_duration": 2.0,  # Fits naturally in 2.9s!
                "trimmed_duration": 2.0,
            },
        ]
        groups = scheduler.schedule_timeline(items, target_duration=10.0)
        pieces = [p for g in groups for p in g.pieces]

        p2 = [p for p in pieces if p.segment_order == 2][0]
        # Segment 2 fits naturally, its tempo MUST NOT be dragged up to 1.25x
        assert p2.applied_tempo == 1.0
        assert p2.status == "natural"

    def test_render_speech_piece_pitch_preserved_audio(self):
        """Verify render_speech_piece correctly applies atempo filter and micro-fades to audio files."""
        sync = AudioSynchronizationService()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            src_wav = tmppath / "input.wav"
            out_wav = tmppath / "output_speed.wav"
            out_mp3 = tmppath / "output_speed.mp3"

            # Generate 2 seconds of test tone at 440 Hz
            import subprocess
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=2.0",
                "-ar", "24000", "-ac", "1",
                str(src_wav),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # Accelerate by 1.20x to WAV
            sync.render_speech_piece(src_wav, out_wav, tempo_factor=1.20, apply_micro_fade=True)
            assert out_wav.exists()
            vp = FFmpegVideoProcessor()
            wav_dur = vp.get_audio_duration(out_wav)
            # 2.0s / 1.20 = ~1.667s
            assert abs(wav_dur - 1.667) < 0.08

            # Accelerate by 1.15x to MP3
            sync.render_speech_piece(src_wav, out_mp3, tempo_factor=1.15, apply_micro_fade=True)
            assert out_mp3.exists()
            mp3_dur = vp.get_audio_duration(out_mp3)
            # 2.0s / 1.15 = ~1.739s
            assert abs(mp3_dur - 1.739) < 0.08
