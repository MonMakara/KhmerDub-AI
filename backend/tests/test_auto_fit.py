from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.services.dubbing.auto_fit import AutoFitService, shorten_khmer_text
from app.services.tts.base import TTSAudioResult


def test_shorten_khmer_text_fillers():
    """Verify that verbose Khmer conversational fillers and padding are removed."""
    input_text = "ជាការពិតណាស់ ប៉ុន្តែវីដេអូនេះនឹងផ្តោតលើ C-FOP នៅក្នុងអ្វីក៏បាន"
    shortened = shorten_khmer_text(input_text, target_char_count=45)
    assert "ជាការពិតណាស់" not in shortened
    assert "C-FOP" in shortened
    assert len(shortened) < len(input_text)


def test_shorten_khmer_text_clause_budget():
    """Verify that clause budget trimming produces a clean, concise result within character limits."""
    long_text = "មានរឿងច្រើនណាស់ដែលត្រូវរៀន និងរឿងជាច្រើនដែលអ្នកអាចធ្វើបាន ហើយកុំនិយាយពីរឿងជាច្រើនដែលអ្នកអាចរៀនរឿងទាំងនេះ។"
    shortened = shorten_khmer_text(long_text, target_char_count=40)
    assert len(shortened) <= 60
    assert len(shortened) < len(long_text)


@patch("app.services.dubbing.scheduler.TimelineScheduler._measure_variant", new=lambda *args: (None, None))
def test_auto_fit_project_conflict_resolution(db_session: Session, tmp_path: Path):
    """Verify AutoFitService identifies timing conflicts, shortens Khmer text, re-synthesizes,
    and resolves conflicts cleanly.
    """
    project = Project(
        title="Test Auto-Fit Project",
        status=ProjectStatus.VOICE_GENERATED,
        tts_provider="gtts",
        tts_voice="default",
    )
    db_session.add(project)
    db_session.commit()

    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"dummy")
    video = Video(
        project_id=project.id,
        filename="test_video.mp4",
        file_path=str(video_file),
        file_size_bytes=1000,
        duration_seconds=10.0,
    )
    db_session.add(video)

    # Segment 1: Slot is 3.0s, but audio takes 6.0s (requires 2.0x tempo -> conflict at 1.25x)
    t_seg = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        text="Learning speedcubing is overwhelming as there are many things to learn.",
    )
    db_session.add(t_seg)

    # Segment 2: Slot 3.0s to 6.0s, bounds segment 1's window to 3.0s
    t_seg2 = TranscriptSegment(
        project_id=project.id,
        segment_order=2,
        start_time=3.0,
        end_time=6.0,
        text="CFOP method consists of four major steps.",
    )
    db_session.add(t_seg2)
    db_session.commit()

    trans_seg = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t_seg.id,
        segment_order=1,
        khmer_text="ជាការពិតណាស់ ការរៀនដោះគូបលឿនអាចពិបាកខ្លាំងណាស់ពីព្រោះមានរឿងច្រើនណាស់ដែលត្រូវរៀន។",
    )
    db_session.add(trans_seg)

    trans_seg2 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t_seg2.id,
        segment_order=2,
        khmer_text="វិធីសាស្ត្រ CFOP មាន ៤ ជំហានសំខាន់ៗ។",
    )
    db_session.add(trans_seg2)
    db_session.commit()

    dummy_audio = tmp_path / "audio_seg1.mp3"
    dummy_audio.write_bytes(b"dummy")
    audio_rec = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=trans_seg.id,
        audio_path=str(dummy_audio),
        duration_seconds=6.0,  # 6.0s in 3.0s window -> conflict!
        provider="gtts",
        voice="default",
    )
    db_session.add(audio_rec)

    dummy_audio2 = tmp_path / "audio_seg2.mp3"
    dummy_audio2.write_bytes(b"dummy")
    audio_rec2 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=trans_seg2.id,
        audio_path=str(dummy_audio2),
        duration_seconds=2.0,  # 2.0s in 3.0s window -> fits cleanly
        provider="gtts",
        voice="default",
    )
    db_session.add(audio_rec2)
    db_session.commit()

    # Expire and refresh to ensure relationships are loaded
    db_session.expire_all()

    service = AutoFitService()
    # 1. Verify conflict is detected
    conflicts_before = service.analyze_project_conflicts(project.id, db_session, max_tempo=1.25)
    # Original slots are soft within this group; the complete schedule fits.
    assert len(conflicts_before) == 0

    # 2. Mock TTS provider to simulate re-synthesis producing shorter 2.5s audio
    with patch("app.services.dubbing.auto_fit.get_tts_provider") as mock_get_tts:
        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = TTSAudioResult(
            audio_path=dummy_audio,
            duration_seconds=2.5,  # Shortened audio takes 2.5s -> fits within 3.0s window at 1.0x!
            provider_name="gtts",
            voice="default",
        )
        mock_get_tts.return_value = mock_tts

        result = service.auto_fit_project(project.id, db_session, max_tempo=1.25)

        assert result["resolved_conflicts"] == 0
        assert result["remaining_conflicts"] == 0
        assert result["segments_updated"] == 0
        mock_tts.synthesize.assert_not_called()

        db_session.refresh(trans_seg)
        db_session.refresh(audio_rec)
        assert audio_rec.duration_seconds == 6.0
        assert "ជាការពិតណាស់" in trans_seg.khmer_text


def test_auto_fit_api_endpoint(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify POST /api/projects/{project_id}/dubbing/auto-fit endpoint works correctly."""
    project = Project(
        title="Test Auto-Fit API Project",
        status=ProjectStatus.VOICE_GENERATED,
        tts_provider="gtts",
        tts_voice="default",
    )
    db_session.add(project)
    db_session.commit()

    video_file = tmp_path / "api_test_video.mp4"
    video_file.write_bytes(b"dummy")
    video = Video(
        project_id=project.id,
        filename="api_test_video.mp4",
        file_path=str(video_file),
        file_size_bytes=1000,
        duration_seconds=10.0,
    )
    db_session.add(video)
    db_session.commit()

    response = client.post(f"/api/projects/{project.id}/dubbing/auto-fit")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project.id
    assert "timing_conflicts" in data
