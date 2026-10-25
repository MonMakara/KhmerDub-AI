import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.exceptions import (
    EmptyTextError,
    LanguageNotSupportedError,
    TTSNetworkError,
)
from app.workers.tts import process_tts


def test_tts_language_support():
    provider = GoogleTTSProvider()
    assert provider.is_language_supported("km") is True
    assert provider.is_language_supported("KM") is True
    assert provider.is_language_supported("en") is True
    assert provider.is_language_supported("invalid_lang_xyz") is False


def test_tts_empty_text_raises(tmp_path: Path):
    provider = GoogleTTSProvider()
    out = tmp_path / "test.mp3"
    with pytest.raises(EmptyTextError):
        provider.synthesize("", out, language="km")
    with pytest.raises(EmptyTextError):
        provider.synthesize("   \n\t  ", out, language="km")


def test_tts_unsupported_language_raises(tmp_path: Path):
    provider = GoogleTTSProvider()
    out = tmp_path / "test.mp3"
    with pytest.raises(LanguageNotSupportedError):
        provider.synthesize("Hello", out, language="non_existent_xyz")


def test_tts_retry_on_network_error(tmp_path: Path):
    provider = GoogleTTSProvider(max_retries=3)
    out = tmp_path / "test_retry.mp3"

    mock_save = MagicMock()
    # Fails first attempt, succeeds on second attempt
    def side_effect(save_path):
        if mock_save.call_count == 1:
            raise OSError("Connection reset by peer")
        Path(save_path).write_bytes(b"dummy mp3 data")

    mock_save.side_effect = side_effect

    with patch("app.services.tts.google.gTTS") as mock_gtts_cls:
        mock_instance = MagicMock()
        mock_instance.save = mock_save
        mock_gtts_cls.return_value = mock_instance

        with patch.object(provider.video_processor, "get_audio_duration", return_value=1.5):
            with patch("time.sleep") as mock_sleep:
                res = provider.synthesize("សួស្តី", out, language="km")
                assert res.audio_path == out
                assert res.duration_seconds == 1.5
                assert mock_save.call_count == 2
                mock_sleep.assert_called_once_with(1.0)


def test_tts_exhausted_retries_raises_network_error(tmp_path: Path):
    provider = GoogleTTSProvider(max_retries=2)
    out = tmp_path / "test_fail.mp3"

    with patch("app.services.tts.google.gTTS") as mock_gtts_cls:
        mock_instance = MagicMock()
        mock_instance.save.side_effect = OSError("Host unreachable")
        mock_gtts_cls.return_value = mock_instance

        with patch("time.sleep"):
            with pytest.raises(TTSNetworkError):
                provider.synthesize("សួស្តី", out, language="km")


def test_tts_worker_missing_translations(db_session: Session):
    project = Project(
        title="No Translations Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.CREATED,
    )
    db_session.add(project)
    db_session.commit()

    job = ProcessingJob(
        project_id=project.id,
        job_type="tts",
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    process_tts(project.id, job.id, db=db_session)

    db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert "No translated Khmer segments found" in (job.error_message or "")


def test_tts_worker_success(db_session: Session, tmp_path: Path):
    project = Project(
        title="TTS Success Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.TRANSLATED,
    )
    db_session.add(project)
    db_session.commit()

    seg1 = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="សួស្តីអ្នកទាំងអស់គ្នា",
    )
    seg2 = TranslationSegment(
        project_id=project.id,
        segment_order=2,
        khmer_text="សូមស្វាគមន៍",
    )
    db_session.add_all([seg1, seg2])
    db_session.commit()

    job = ProcessingJob(
        project_id=project.id,
        job_type="tts",
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    def fake_synthesize(text, output_path, **kwargs):
        Path(output_path).write_bytes(b"dummy mp3")
        from app.services.tts.base import TTSAudioResult
        return TTSAudioResult(
            audio_path=output_path,
            duration_seconds=2.0,
            provider_name="gtts",
            voice="default",
            language="km",
        )

    with patch.object(GoogleTTSProvider, "synthesize", side_effect=fake_synthesize):
        process_tts(project.id, job.id, db=db_session)

    db_session.refresh(job)
    db_session.refresh(project)

    assert job.status == JobStatus.COMPLETED
    assert job.progress_percentage == 100
    assert project.status == ProjectStatus.VOICE_GENERATED

    audios = db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == project.id).all()
    assert len(audios) == 2
    assert all(a.is_outdated is False for a in audios)
    assert all(a.duration_seconds == 2.0 for a in audios)


def test_tts_api_nonexistent_project(client: TestClient):
    response = client.post("/api/projects/non-existent-id/tts")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_tts_api_no_translations(client: TestClient, db_session: Session):
    project = Project(
        title="Empty Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.CREATED,
    )
    db_session.add(project)
    db_session.commit()

    response = client.post(f"/api/projects/{project.id}/tts")
    assert response.status_code == 400
    assert "no khmer translation segments" in response.json()["detail"].lower()


def test_tts_audio_invalidation_on_translation_edit(client: TestClient, db_session: Session, tmp_path: Path):
    project = Project(
        title="Invalidation Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    t_seg = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="អត្ថបទដើម",
    )
    db_session.add(t_seg)
    db_session.commit()

    audio_file = tmp_path / "seg1.mp3"
    audio_file.write_bytes(b"fake audio")
    audio = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=t_seg.id,
        audio_path=str(audio_file),
        duration_seconds=1.8,
        provider="gtts",
        voice="default",
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Verify initially not outdated
    db_session.refresh(audio)
    assert audio.is_outdated is False

    # Patch the translation text
    res = client.patch(
        f"/api/projects/{project.id}/translations/{t_seg.id}",
        json={"khmer_text": "អត្ថបទថ្មីកែសម្រួល"},
    )
    assert res.status_code == 200
    assert res.json()["khmer_text"] == "អត្ថបទថ្មីកែសម្រួល"

    # Verify audio is now marked outdated
    db_session.refresh(audio)
    assert audio.is_outdated is True


def test_tts_single_segment_regenerate(client: TestClient, db_session: Session, tmp_path: Path):
    project = Project(
        title="Regenerate Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    t_seg = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="សូមស្វាគមន៍",
    )
    db_session.add(t_seg)
    db_session.commit()

    def fake_synthesize(text, output_path, **kwargs):
        Path(output_path).write_bytes(b"new regenerated audio")
        from app.services.tts.base import TTSAudioResult
        return TTSAudioResult(
            audio_path=output_path,
            duration_seconds=3.14,
            provider_name="gtts",
            voice="default",
            language="km",
        )

    with patch.object(GoogleTTSProvider, "synthesize", side_effect=fake_synthesize):
        res = client.post(f"/api/projects/{project.id}/tts/{t_seg.id}/regenerate")
        assert res.status_code == 200
        data = res.json()
        assert data["duration_seconds"] == 3.14
        assert data["is_outdated"] is False
        assert data["translation_segment_id"] == t_seg.id


def test_tts_stream_audio_endpoints(client: TestClient, db_session: Session, tmp_path: Path):
    project = Project(
        title="Stream Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(project)
    db_session.commit()

    t_seg = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="សាកល្បងសំឡេង",
    )
    db_session.add(t_seg)
    db_session.commit()

    audio_file = tmp_path / "valid_stream.mp3"
    audio_file.write_bytes(b"MP3_STREAM_CONTENT_BYTES")

    audio = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=t_seg.id,
        audio_path=str(audio_file),
        duration_seconds=2.5,
        provider="gtts",
        voice="default",
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Test GET /generated-audio
    list_res = client.get(f"/api/projects/{project.id}/generated-audio")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data["audios"]) == 1
    assert list_data["total_duration_seconds"] == 2.5
    assert list_data["audios"][0]["audio_url"] == f"/api/projects/{project.id}/tts/{t_seg.id}/audio"

    # Test GET streaming endpoint
    stream_res = client.get(f"/api/projects/{project.id}/tts/{t_seg.id}/audio")
    assert stream_res.status_code == 200
    assert "audio/mpeg" in stream_res.headers.get("content-type", "")
    assert "inline" in stream_res.headers.get("content-disposition", "")
    assert stream_res.content == b"MP3_STREAM_CONTENT_BYTES"

    # Test HEAD request on project streaming endpoint (Safari/Chrome browser capability probe)
    head_res = client.head(f"/api/projects/{project.id}/tts/{t_seg.id}/audio")
    assert head_res.status_code == 200
    assert "audio/mpeg" in head_res.headers.get("content-type", "")

    # Test direct /api/tts/stream/{audio.id} endpoint
    direct_res = client.get(f"/api/tts/stream/{audio.id}")
    assert direct_res.status_code == 200
    assert "audio/mpeg" in direct_res.headers.get("content-type", "")
    assert "inline" in direct_res.headers.get("content-disposition", "")
    assert direct_res.content == b"MP3_STREAM_CONTENT_BYTES"

    direct_head_res = client.head(f"/api/tts/stream/{audio.id}")
    assert direct_head_res.status_code == 200


def test_real_gtts_synthesis_integration(tmp_path: Path):
    """Real end-to-end gTTS test with actual network call and ffprobe duration verification."""
    provider = GoogleTTSProvider()
    out = tmp_path / "real_khmer_test.mp3"
    result = provider.synthesize("ជំរាបសួរ", out, language="km")

    assert result.audio_path.exists()
    assert result.audio_path.stat().st_size > 0
    assert result.duration_seconds > 0.0
    assert result.provider_name == "gtts"
    assert result.voice == "default"
    assert result.language == "km"
