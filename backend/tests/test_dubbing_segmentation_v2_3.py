import subprocess
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
    ProcessingJob,
    JobStatus,
)
from app.services.dubbing.grouper import DubbingGrouper, DubbingGroupDefinition
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.workers.translation import process_translation


def make_sine_wav(path: Path, duration: float, sample_rate: int = 44100, freq: int = 440) -> Path:
    """Generate a clean synthetic PCM WAV tone file for testing."""
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


# ---------------------------------------------------------------------------
# Test 1: DubbingGrouper Algorithm Tests
# ---------------------------------------------------------------------------

def test_dubbing_grouper_coalesces_short_adjacent_segments():
    """Verify short staccato sentences (<2.2s) with brief pauses (<1.05s) merge into cohesive dubbing units."""
    grouper = DubbingGrouper(min_duration=2.2, target_duration=6.0, max_duration=9.5, max_merge_pause=1.05)

    segments = [
        TranscriptSegment(id="s1", segment_order=1, start_time=0.0, end_time=1.76, text="Once upon a time,"),
        TranscriptSegment(id="s2", segment_order=2, start_time=1.82, end_time=3.52, text="in a quiet ancient bamboo grove,"),
        TranscriptSegment(id="s3", segment_order=3, start_time=3.60, end_time=4.86, text="a young farmer planted a seed."),
        # Long pause here: 4.86 -> 6.50 = 1.64s pause (>1.05s)
        TranscriptSegment(id="s4", segment_order=4, start_time=6.50, end_time=10.00, text="He watered it faithfully every single morning."),
    ]

    groups = grouper.group_segments(segments)

    # Should form 2 groups: s1+s2+s3 in Group 1, s4 in Group 2 (due to long pause)
    assert len(groups) == 2
    g1 = groups[0]
    assert g1.unit_order == 1
    assert g1.source_segment_ids == ["s1", "s2", "s3"]
    assert g1.start_time == 0.0
    assert g1.end_time == 4.86
    assert "Once upon a time, in a quiet ancient bamboo grove, a young farmer planted a seed." in g1.combined_english_text

    g2 = groups[1]
    assert g2.unit_order == 2
    assert g2.source_segment_ids == ["s4"]
    assert g2.start_time == 6.50
    assert g2.end_time == 10.00


def test_dubbing_grouper_respects_max_duration():
    """Verify grouping does not exceed max_duration (9.5s) even if pause is small."""
    grouper = DubbingGrouper(min_duration=2.2, target_duration=6.0, max_duration=8.0, max_merge_pause=1.05)

    segments = [
        TranscriptSegment(id="s1", segment_order=1, start_time=0.0, end_time=4.0, text="Sentence number one is fairly descriptive."),
        TranscriptSegment(id="s2", segment_order=2, start_time=4.1, end_time=8.5, text="Sentence number two continues the ongoing narrative."),
    ]
    # Total duration would be 8.5s > 8.0s max, and s1 is already 4.0s (>= min_duration)
    groups = grouper.group_segments(segments)
    assert len(groups) == 2
    assert groups[0].source_segment_ids == ["s1"]
    assert groups[1].source_segment_ids == ["s2"]


def test_dubbing_grouper_empty_and_single():
    """Test boundary conditions: empty input or single segment."""
    grouper = DubbingGrouper()
    assert grouper.group_segments([]) == []

    single = [TranscriptSegment(id="s1", segment_order=1, start_time=1.0, end_time=2.0, text="Hello.")]
    res = grouper.group_segments(single)
    assert len(res) == 1
    assert res[0].source_segment_ids == ["s1"]
    assert res[0].start_time == 1.0
    assert res[0].end_time == 2.0


# ---------------------------------------------------------------------------
# Test 2: Translation Worker Dubbing Units Integration
# ---------------------------------------------------------------------------

def test_translation_worker_v2_3_grouping_persistence():
    """Verify translation worker creates grouped TranslationSegments for v2.3 projects and links TranscriptSegments."""
    db: Session = SessionLocal()
    try:
        project = Project(
            id="test-v2-3-worker",
            title="Test V2.3 Worker Project",
            original_language="en",
            target_language="km",
            pipeline_version="v2.3",
            status=ProjectStatus.TRANSCRIBED,
        )
        db.add(project)

        s1 = TranscriptSegment(id="t_v23_1", project_id=project.id, segment_order=1, start_time=0.0, end_time=1.5, text="First short sentence.")
        s2 = TranscriptSegment(id="t_v23_2", project_id=project.id, segment_order=2, start_time=1.6, end_time=3.2, text="Second connected thought.")
        s3 = TranscriptSegment(id="t_v23_3", project_id=project.id, segment_order=3, start_time=5.0, end_time=8.5, text="Third independent sentence after a break.")
        db.add_all([s1, s2, s3])
        db.commit()

        job = ProcessingJob(
            id="job-v2-3-worker",
            project_id=project.id,
            job_type="translate",
            status=JobStatus.PENDING,
            progress_percentage=0,
        )
        db.add(job)
        db.commit()

        # Mock the translation provider to return predictable Khmer output
        mock_provider_instance = MagicMock()
        mock_provider_instance.translate.side_effect = lambda texts, **kw: [f"ខ្មែរ: {t}" for t in texts]

        with patch("app.workers.translation.NLLBTranslationProvider", return_value=mock_provider_instance):
            process_translation(project.id, job.id, db=db)

        db.refresh(project)
        db.refresh(job)
        assert job.status == JobStatus.COMPLETED
        assert project.status == ProjectStatus.TRANSLATED
        trans_segs = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project.id)
            .order_by(TranslationSegment.segment_order)
            .all()
        )

        # Expected: 2 dubbing units (s1+s2 grouped, s3 separate)
        assert len(trans_segs) == 2

        u1 = trans_segs[0]
        assert u1.segment_order == 1
        assert u1.start_time == 0.0
        assert u1.end_time == 3.2
        assert "t_v23_1" in u1.source_segment_ids
        assert "t_v23_2" in u1.source_segment_ids
        assert u1.source_text == "First short sentence. Second connected thought."

        u2 = trans_segs[1]
        assert u2.segment_order == 2
        assert u2.start_time == 5.0
        assert u2.end_time == 8.5
        assert u2.source_segment_ids == '["t_v23_3"]'

        # Check that TranscriptSegments have dubbing_unit_id linked
        db.refresh(s1)
        db.refresh(s2)
        db.refresh(s3)
        assert s1.dubbing_unit_id == u1.id
        assert s2.dubbing_unit_id == u1.id
        assert s3.dubbing_unit_id == u2.id

    finally:
        # Cleanup
        db.query(ProcessingJob).filter(ProcessingJob.project_id == "test-v2-3-worker").delete()
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == "test-v2-3-worker").delete()
        db.query(TranslationSegment).filter(TranslationSegment.project_id == "test-v2-3-worker").delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == "test-v2-3-worker").delete()
        db.query(Project).filter(Project.id == "test-v2-3-worker").delete()
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Test 3: Per-Sentence Transcript Edit Invalidation
# ---------------------------------------------------------------------------

def test_transcript_edit_invalidates_parent_dubbing_unit():
    """Verify editing a TranscriptSegment marks the parent TranslationSegment and its GeneratedAudio as outdated."""
    from app.api.endpoints.projects import update_transcript_segment
    from app.schemas.project import TranscriptSegmentUpdate

    db: Session = SessionLocal()
    try:
        project = Project(
            id="test-v2-3-edit",
            title="Test V2.3 Edit Invalidation",
            pipeline_version="v2.3",
            status=ProjectStatus.VOICE_GENERATED,
        )
        db.add(project)

        u1 = TranslationSegment(
            id="u1-edit",
            project_id=project.id,
            segment_order=1,
            khmer_text="អត្ថបទដើម",
            source_text="Sentence A. Sentence B.",
            source_segment_ids='["t-a", "t-b"]',
            start_time=0.0,
            end_time=4.0,
            is_outdated=False,
        )
        db.add(u1)

        aud1 = GeneratedAudio(
            id="aud-u1",
            project_id=project.id,
            translation_segment_id="u1-edit",
            audio_path="/tmp/fake.wav",
            duration_seconds=3.8,
            is_outdated=False,
            provider="edge",
            voice="km-KH-PisethNeural",
        )
        db.add(aud1)

        t_a = TranscriptSegment(
            id="t-a",
            project_id=project.id,
            segment_order=1,
            start_time=0.0,
            end_time=2.0,
            text="Sentence A.",
            dubbing_unit_id="u1-edit",
        )
        t_b = TranscriptSegment(
            id="t-b",
            project_id=project.id,
            segment_order=2,
            start_time=2.1,
            end_time=4.0,
            text="Sentence B.",
            dubbing_unit_id="u1-edit",
        )
        db.add_all([t_a, t_b])
        db.commit()

        # Update t_a with modified text
        payload = TranscriptSegmentUpdate(text="Sentence A modified by user.")
        res = update_transcript_segment(project_id=project.id, segment_id="t-a", payload=payload, db=db)

        assert res.text == "Sentence A modified by user."
        assert res.is_manually_edited is True

        # Refresh u1 and aud1
        db.refresh(u1)
        db.refresh(aud1)
        assert u1.is_outdated is True
        assert "Sentence A modified by user." in u1.source_text
        assert aud1.is_outdated is True

    finally:
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == "test-v2-3-edit").delete()
        db.query(TranslationSegment).filter(TranslationSegment.project_id == "test-v2-3-edit").delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == "test-v2-3-edit").delete()
        db.query(Project).filter(Project.id == "test-v2-3-edit").delete()
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Test 4: Subtitles Alignment Preservation
# ---------------------------------------------------------------------------

def test_subtitles_service_preserves_fine_grained_cues():
    """Verify subtitle generation keeps individual transcript timestamps intact even when translation is grouped."""
    from app.services.subtitles.service import SubtitleService

    db: Session = SessionLocal()
    try:
        project = Project(
            id="test-v2-3-subs",
            title="Test V2.3 Subtitles",
            pipeline_version="v2.3",
            status=ProjectStatus.VOICE_GENERATED,
        )
        db.add(project)

        # 3 transcript segments
        s1 = TranscriptSegment(id="sub-s1", project_id=project.id, segment_order=1, start_time=0.5, end_time=2.0, text="First subtitle line.")
        s2 = TranscriptSegment(id="sub-s2", project_id=project.id, segment_order=2, start_time=2.1, end_time=4.0, text="Second subtitle line.")
        s3 = TranscriptSegment(id="sub-s3", project_id=project.id, segment_order=3, start_time=4.2, end_time=6.0, text="Third subtitle line.")
        db.add_all([s1, s2, s3])

        # 1 grouped translation segment for s1+s2
        u1 = TranslationSegment(
            id="sub-u1",
            project_id=project.id,
            segment_order=1,
            khmer_text="បន្ទាត់ទីមួយ និងបន្ទាត់ទីពីរ",
            start_time=0.5,
            end_time=4.0,
            source_segment_ids='["sub-s1", "sub-s2"]',
        )
        # 1 translation segment for s3
        u2 = TranslationSegment(
            id="sub-u2",
            project_id=project.id,
            segment_order=2,
            khmer_text="បន្ទាត់ទីបី",
            start_time=4.2,
            end_time=6.0,
            source_segment_ids='["sub-s3"]',
        )
        db.add_all([u1, u2])
        db.commit()

        sub_service = SubtitleService()
        srt_en, _, _ = sub_service.export_subtitles(project.id, "en", "srt", db)
        assert "First subtitle line." in srt_en
        assert "Second subtitle line." in srt_en
        assert "Third subtitle line." in srt_en

        # Subtitles for Khmer
        srt_km, _, _ = sub_service.export_subtitles(project.id, "km", "srt", db)
        assert len(srt_km) > 0
        assert "បន្ទាត់ទីបី" in srt_km

    finally:
        db.query(TranslationSegment).filter(TranslationSegment.project_id == "test-v2-3-subs").delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == "test-v2-3-subs").delete()
        db.query(Project).filter(Project.id == "test-v2-3-subs").delete()
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Test 5: Audio Synchronization & Timing Optimizer for v2.3 Dubbing Units
# ---------------------------------------------------------------------------

def test_v2_3_synchronizer_uses_dubbing_unit_timing(tmp_path: Path):
    """Verify v2.3 synchronizer uses trans_seg.start_time and trans_seg.end_time."""
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "v23_timeline.wav"

    # Dubbing unit spanning 1.0s to 5.0s (slot = 4.0s)
    # Audio is 3.5s -> fits with natural speed 1.0x
    aud_wav = make_sine_wav(tmp_path / "unit1.wav", duration=3.5)

    u1 = TranslationSegment(
        id="unit-1",
        project_id="p-v23",
        segment_order=1,
        khmer_text="ឃ្លាវែងដែលមានអត្ថន័យពេញលេញ",
        start_time=1.0,
        end_time=5.0,
    )
    rec1 = GeneratedAudio(
        id="rec-1",
        project_id="p-v23",
        translation_segment_id="unit-1",
        audio_path=str(aud_wav),
        duration_seconds=3.5,
    )

    # Use dummy transcript segment; synchronizer should prefer u1.start_time / u1.end_time in v2.3
    dummy_t = TranscriptSegment(id="dt", project_id="p-v23", segment_order=1, start_time=0.0, end_time=1.0, text="dummy")

    res = sync.synchronize(
        project_id="p-v23",
        segment_items=[(dummy_t, u1, rec1)],
        target_duration=6.0,
        output_timeline_path=out_wav,
        strict_validation=True,
        pipeline_version="v2.3",
    )

    assert len(res.conflicts) == 0
    assert out_wav.exists()
    vp = FFmpegVideoProcessor()
    final_dur = vp.get_audio_duration(out_wav)
    assert abs(final_dur - 6.0) < 0.05


def test_v2_3_timing_optimizer_identifies_dubbing_unit_slack():
    """Verify TimingOptimizerService honors trans_seg.start_time / end_time in v2.3."""
    db: Session = SessionLocal()
    try:
        project = Project(
            id="test-v23-opt",
            title="Test V2.3 Timing Optimizer",
            pipeline_version="v2.3",
            status=ProjectStatus.VOICE_GENERATED,
        )
        db.add(project)

        # Unit 1: 0.0 -> 5.0 (slot: 5.0s, audio: 4.5s) -> fits naturally
        u1 = TranslationSegment(
            id="opt-u1",
            project_id=project.id,
            segment_order=1,
            khmer_text="ឃ្លាទីមួយ",
            start_time=0.0,
            end_time=5.0,
        )
        aud1 = GeneratedAudio(
            id="opt-a1",
            project_id=project.id,
            translation_segment_id="opt-u1",
            audio_path="/tmp/fake1.wav",
            duration_seconds=4.5,
        )
        # Unit 2: 5.5 -> 8.5 (slot: 3.0s, audio: 3.3s) -> fits with mild tempo ~1.10x <= 1.25x
        u2 = TranslationSegment(
            id="opt-u2",
            project_id=project.id,
            segment_order=2,
            khmer_text="ឃ្លាទីពីរ",
            start_time=5.5,
            end_time=8.5,
        )
        aud2 = GeneratedAudio(
            id="opt-a2",
            project_id=project.id,
            translation_segment_id="opt-u2",
            audio_path="/tmp/fake2.wav",
            duration_seconds=3.3,
        )
        db.add_all([u1, aud1, u2, aud2])
        db.commit()

        optimizer = TimingOptimizerService(max_tempo=1.25)
        analyses = optimizer.analyze_timeline(project.id, db)

        assert len(analyses) == 2
        # Unit 1 should be natural
        assert analyses[0].status == "natural"
        # Unit 2 should be speed_adjusted (fits comfortably within 1.25x)
        assert analyses[1].status == "speed_adjusted"
        assert analyses[1].overflow_seconds == 0.0

    finally:
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == "test-v23-opt").delete()
        db.query(TranslationSegment).filter(TranslationSegment.project_id == "test-v23-opt").delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == "test-v23-opt").delete()
        db.query(Project).filter(Project.id == "test-v23-opt").delete()
        db.commit()
        db.close()
