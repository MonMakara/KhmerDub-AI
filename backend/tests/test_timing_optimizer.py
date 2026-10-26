import math
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.services.dubbing.timing_optimizer import (
    TimingOptimizerService,
    SegmentTimingAnalysis,
    TimelineOptimizationResult,
)
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.video.ffmpeg import FFmpegVideoProcessor


@pytest.fixture
def test_audio_file():
    """Create a temporary 1-second 44.1kHz stereo audio clip for tests."""
    sync = AudioSynchronizationService()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)
    sync.generate_silence(1.0, path)
    yield path
    if path.exists():
        path.unlink()


def test_segment_timing_analysis_dataclass():
    analysis = SegmentTimingAnalysis(
        segment_order=1,
        transcript_segment_id="ts-1",
        translation_segment_id="tr-1",
        start_time=0.0,
        end_time=3.0,
        slot_duration=3.0,
        next_start=4.0,
        inter_segment_gap=1.0,
        available_window=3.92,
        effective_window=3.87,
        audio_path=None,
        raw_duration=3.5,
        trimmed_duration=3.5,
        required_tempo=0.90,
        tempo_factor=1.0,
        status="natural",
        overflow_seconds=0.0,
        khmer_text="សួស្តី",
        english_text="Hello",
        is_manually_edited=False,
    )
    assert analysis.status == "natural"
    assert analysis.slot_duration == 3.0
    assert analysis.available_window == 3.92
    assert analysis.inter_segment_gap == 1.0


def test_timing_optimizer_analyze_timeline_safe_gaps(db_session: Session, test_audio_file: Path):
    """Verify safe inter-sentence silence gap allocation and safe window calculations."""
    project = Project(
        title="Timing Gap Analysis Project",
        original_language="en",
        target_language="km",
        pipeline_version="v2",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="fake_video.mp4",
        file_path="/tmp/fake_video.mp4",
        file_size_bytes=1000,
        duration_seconds=12.0,
    )
    db_session.add(video)

    # Segment 1: 0.0s - 3.0s (3s slot, next starts at 5.0s -> 2.0s silence gap)
    t1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        text="First sentence.",
    )
    # Segment 2: 5.0s - 8.0s (3s slot, next starts at 8.2s -> 0.2s silence gap)
    t2 = TranscriptSegment(
        project_id=project.id,
        segment_order=2,
        start_time=5.0,
        end_time=8.0,
        text="Second sentence.",
    )
    # Segment 3: 8.2s - 10.0s (1.8s slot, video ends at 12.0s -> 2.0s gap)
    t3 = TranscriptSegment(
        project_id=project.id,
        segment_order=3,
        start_time=8.2,
        end_time=10.0,
        text="Third sentence.",
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    tr1 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t1.id,
        segment_order=1,
        khmer_text="ប្រយោគទីមួយ។",
    )
    tr2 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t2.id,
        segment_order=2,
        khmer_text="ប្រយោគទីពីរ។",
    )
    tr3 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t3.id,
        segment_order=3,
        khmer_text="ប្រយោគទីបី។",
    )
    db_session.add_all([tr1, tr2, tr3])
    db_session.commit()

    # Audio durations:
    # Seg 1: 2.5s (fits naturally in 3s slot)
    # Seg 2: 3.4s (exceeds 3.0s slot, but fits in safe gap window: 5.0s to 8.2s - 0.08s = 3.12s window, at 1.09x)
    # Seg 3: 4.0s (exceeds 1.8s slot, available window 12.0 - 8.2 - 0.05 = 3.75s, at 1.07x)
    a1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(test_audio_file),
        duration_seconds=2.5,
    )
    a2 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr2.id,
        audio_path=str(test_audio_file),
        duration_seconds=3.4,
    )
    a3 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr3.id,
        audio_path=str(test_audio_file),
        duration_seconds=2.2,
    )
    db_session.add_all([a1, a2, a3])
    db_session.commit()

    optimizer = TimingOptimizerService(max_tempo=1.25, min_pause_seconds=0.08, safety_margin_seconds=0.05)
    analyses = optimizer.analyze_timeline(project.id, db_session)

    assert len(analyses) == 3
    # Seg 1 has 2.0s gap, audio 2.5s <= effective window -> natural
    assert analyses[0].segment_order == 1
    assert analyses[0].status == "natural"
    assert analyses[0].inter_segment_gap == 2.0
    assert analyses[0].available_window == pytest.approx(4.92, rel=0.01)

    # Seg 2 has 0.2s gap, slot 3.0s, available 3.12s, effective 3.07s
    # Audio 3.4s / 3.07s = 1.11x <= 1.25x -> speed_adjusted
    assert analyses[1].segment_order == 2
    assert analyses[1].status == "speed_adjusted"
    assert analyses[1].required_tempo == pytest.approx(1.11, rel=0.02)
    assert analyses[1].overflow_seconds == 0.0


def test_timing_optimizer_large_overflow_triggers_optimization(db_session: Session, test_audio_file: Path):
    """Verify that segments exceeding 1.25x tempo are flagged as needs_optimization with real overflow."""
    project = Project(
        title="Overflow Project",
        original_language="en",
        target_language="km",
        pipeline_version="v2",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    # Slot 2.0s (0.0 to 2.0), next is 2.1s (gap 0.1s -> available window 2.02s, effective 1.97s)
    t1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=2.0,
        text="Short prompt.",
    )
    t2 = TranscriptSegment(
        project_id=project.id,
        segment_order=2,
        start_time=2.1,
        end_time=4.0,
        text="Next prompt.",
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    tr1 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t1.id,
        segment_order=1,
        khmer_text="សារខ្លីនេះគឺវែងណាស់សម្រាប់និយាយ។",
        is_manually_edited=False,
    )
    tr2 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t2.id,
        segment_order=2,
        khmer_text="សារបន្ទាប់។",
        is_manually_edited=False,
    )
    db_session.add_all([tr1, tr2])
    db_session.commit()

    # Generated audio is 5.0 seconds (way over 2.0s slot; even at 1.25x speed it takes 4.0s > 1.97s)
    a1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(test_audio_file),
        duration_seconds=5.0,
    )
    a2 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr2.id,
        audio_path=str(test_audio_file),
        duration_seconds=1.5,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    optimizer = TimingOptimizerService(max_tempo=1.25)
    analyses = optimizer.analyze_timeline(project.id, db_session)

    assert analyses[0].status == "needs_optimization"
    assert analyses[0].required_tempo > 1.25
    assert analyses[0].overflow_seconds > 1.0


def test_preserve_manually_edited_segments(db_session: Session, test_audio_file: Path):
    """Verify that manually edited translation segments are NEVER overwritten by auto-optimization."""
    project = Project(
        title="Manual Edit Preservation",
        original_language="en",
        target_language="km",
        pipeline_version="v2",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    t1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=2.0,
        text="User edited text.",
    )
    db_session.add(t1)
    db_session.commit()

    manual_text = "ការបកប្រែដោយដៃដែលអ្នកប្រើប្រាស់បានកែសម្រួលផ្ទាល់។"
    tr1 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t1.id,
        segment_order=1,
        khmer_text=manual_text,
        is_manually_edited=True,  # Crucial flag
    )
    db_session.add(tr1)
    db_session.commit()

    a1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(test_audio_file),
        duration_seconds=4.0,  # Overflowing
    )
    db_session.add(a1)
    db_session.commit()

    optimizer = TimingOptimizerService(max_tempo=1.25)
    result = optimizer.optimize_project(project.id, db_session)

    db_session.refresh(tr1)
    # Must preserve exact user text without modification
    assert tr1.khmer_text == manual_text
    assert tr1.is_manually_edited is True
    # Result should honestly report unresolved conflict for user review
    assert result.unresolved_conflicts == 1


def test_backward_compatibility_v1_vs_v2(client: TestClient, db_session: Session):
    """Verify that v1 projects retain legacy conflict calculation without auto-fit altering them."""
    # V1 project
    proj_v1 = Project(
        title="Legacy V1 Dubbing Project",
        original_language="en",
        target_language="km",
        pipeline_version="v1",
        status=ProjectStatus.VOICE_GENERATED,
    )
    # V2 project
    proj_v2 = Project(
        title="Modern V2 Dubbing Project",
        original_language="en",
        target_language="km",
        pipeline_version="v2",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add_all([proj_v1, proj_v2])
    db_session.commit()

    # Add identical segments to both
    for p in [proj_v1, proj_v2]:
        t1 = TranscriptSegment(
            project_id=p.id,
            segment_order=1,
            start_time=0.0,
            end_time=3.0,
            text="Testing backward compatibility.",
        )
        db_session.add(t1)
        db_session.commit()

        tr1 = TranslationSegment(
            project_id=p.id,
            transcript_segment_id=t1.id,
            segment_order=1,
            khmer_text="ការធ្វើតេស្តភាពឆបគ្នា។",
        )
        db_session.add(tr1)
        db_session.commit()

        a1 = GeneratedAudio(
            project_id=p.id,
            translation_segment_id=tr1.id,
            audio_path="audios/fake.wav",
            duration_seconds=3.2,  # 3.2s in 3.0s slot (required tempo ~1.07x)
        )
        db_session.add(a1)
        db_session.commit()

    # Query export status for v1
    res_v1 = client.get(f"/api/projects/{proj_v1.id}/export/status")
    assert res_v1.status_code == 200
    data_v1 = res_v1.json()
    assert data_v1["pipeline_version"] == "v1"
    # Legacy v1 does not populate timing_summary dict
    assert data_v1["timing_summary"] is None

    # Query export status for v2
    res_v2 = client.get(f"/api/projects/{proj_v2.id}/export/status")
    assert res_v2.status_code == 200
    data_v2 = res_v2.json()
    assert data_v2["pipeline_version"] == "v2"
    assert data_v2["timing_summary"] is not None
    assert data_v2["timing_summary"]["total_segments"] == 1
    assert data_v2["timing_summary"]["unresolved_conflicts"] == 0
    assert data_v2["timing_summary"]["status"] == "ready"


def test_bounded_sentence_optimization(db_session: Session, test_audio_file: Path):
    """Verify that optimization uses bounded retries and preserves voice seed."""
    project = Project(
        title="Bounded Optimization Project",
        original_language="en",
        target_language="km",
        pipeline_version="v2",
        tts_provider="gtts",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    t1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=2.0,
        text="A verbose English segment.",
    )
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t1.id,
        segment_order=1,
        khmer_text="នេះគឺជាការបកប្រែដែលវែងខ្លាំងណាស់ហើយមានពាក្យច្រើនលើសលប់។",
        is_manually_edited=False,
    )
    db_session.add(tr1)
    db_session.commit()

    a1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(test_audio_file),
        duration_seconds=3.8,  # > 2.0s slot at 1.25x
    )
    db_session.add(a1)
    db_session.commit()

    mock_tts_result = MagicMock()
    mock_tts_result.duration_seconds = 2.1  # Fits in 2.0s slot at 1.05x tempo!

    with patch("app.services.dubbing.timing_optimizer.get_tts_provider") as mock_get_tts:
        mock_provider = MagicMock()
        mock_provider.synthesize.return_value = mock_tts_result
        mock_get_tts.return_value = mock_provider

        optimizer = TimingOptimizerService(max_tempo=1.25)
        # Mock get_audio_duration: return 3.8s on initial silence trim (Tier 1), then 2.1s after re-synthesis (Tier 3)
        with patch.object(optimizer.video_processor, "get_audio_duration", side_effect=[3.8, 2.1]):
            result = optimizer.optimize_project(project.id, db_session)

            assert result.sentence_optimized >= 1
            assert result.unresolved_conflicts == 0
            assert result.is_export_ready is True
            # Verify synthesize was called with seed
            assert mock_provider.synthesize.called
            call_kwargs = mock_provider.synthesize.call_args[1]
            assert "seed" in call_kwargs


def test_silence_trimming_yield(test_audio_file: Path):
    """Verify silence trimming operates safely and preserves audio duration."""
    sync_service = AudioSynchronizationService()
    # Check that trim_audio_silence succeeds on a valid audio file
    trimmed_path = test_audio_file.parent / f"trimmed_{test_audio_file.name}"
    sync_service.trim_audio_silence(test_audio_file, trimmed_path)
    assert trimmed_path.exists()
    assert trimmed_path.stat().st_size > 0
    trimmed_path.unlink()
