import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.tts.base import TTSAudioResult
from app.services.tts.edge import EdgeTTSProvider
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.registry import (
    list_supported_voices,
    is_valid_voice_combination,
    get_tts_provider,
)
from app.services.tts.exceptions import (
    EmptyTextError,
    VoiceNotSupportedError,
)
from app.workers.tts import process_tts, synthesize_segment_audio
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.video.ffmpeg import FFmpegVideoProcessor


def test_voice_registry_and_validation():
    """Verify registry returns all supported voices and validates correctly."""
    voices = list_supported_voices()
    assert len(voices) >= 3

    # Google Khmer is removed; Microsoft Piseth and Sreymom remain available
    providers_and_voices = [(v["provider"], v["voice"]) for v in voices]
    assert ("gtts", "default") not in providers_and_voices
    assert ("edge", "km-KH-PisethNeural") in providers_and_voices
    assert ("edge", "km-KH-SreymomNeural") in providers_and_voices

    # Valid combinations
    assert is_valid_voice_combination("gtts", "default") is False
    assert is_valid_voice_combination("edge", "km-KH-PisethNeural") is True
    assert is_valid_voice_combination("edge", "km-KH-SreymomNeural") is True

    # Invalid combinations
    assert is_valid_voice_combination("gtts", "km-KH-PisethNeural") is False
    assert is_valid_voice_combination("edge", "default") is False
    assert is_valid_voice_combination("unknown", "unknown") is False

    # Factory instantiation
    assert isinstance(get_tts_provider("gtts"), GoogleTTSProvider)
    assert isinstance(get_tts_provider("edge"), EdgeTTSProvider)
    with pytest.raises(ValueError):
        get_tts_provider("unsupported_provider")


def test_edge_tts_provider_validations(tmp_path: Path):
    """Verify input validation and error handling in EdgeTTSProvider."""
    provider = EdgeTTSProvider()
    out = tmp_path / "out.mp3"

    # Empty text
    with pytest.raises(EmptyTextError):
        provider.synthesize("", out)
    with pytest.raises(EmptyTextError):
        provider.synthesize("   \t\n ", out)

    # Unsupported voice
    with pytest.raises(VoiceNotSupportedError):
        provider.synthesize("សួស្តី", out, voice="unsupported-voice-123")


def test_edge_tts_provider_mocked_synthesis(tmp_path: Path):
    """Verify EdgeTTSProvider retry logic and successful synthesis flow."""
    provider = EdgeTTSProvider(max_retries=2)
    out = tmp_path / "test_edge.mp3"

    # Simulate success
    def fake_run(coro):
        coro.close()
        out.write_bytes(b"dummy edge mp3 data")

    with patch.object(provider, "_run_async_safely", side_effect=fake_run):
        with patch.object(provider.video_processor, "get_audio_duration", return_value=2.4):
            res = provider.synthesize("សួស្តី", out, voice="km-KH-PisethNeural")
            assert res.audio_path == out
            assert res.duration_seconds == 2.4
            assert res.provider_name == "edge"
            assert res.voice == "km-KH-PisethNeural"


def test_edge_tts_retry_on_network_failure(tmp_path: Path):
    """Verify EdgeTTSProvider retries on transient network errors."""
    provider = EdgeTTSProvider(max_retries=2)
    out = tmp_path / "retry_edge.mp3"

    call_count = 0

    def fake_run(coro):
        nonlocal call_count
        call_count += 1
        coro.close()
        if call_count == 1:
            raise OSError("Network connection refused")
        out.write_bytes(b"dummy recovered mp3")

    with patch.object(provider, "_run_async_safely", side_effect=fake_run):
        with patch.object(provider.video_processor, "get_audio_duration", return_value=1.8):
            with patch("time.sleep") as mock_sleep:
                res = provider.synthesize("សួស្តី", out, voice="km-KH-SreymomNeural")
                assert res.duration_seconds == 1.8
                assert call_count == 2
                mock_sleep.assert_called_once_with(1.0)


def test_edge_tts_retry_on_no_audio_received(tmp_path: Path):
    """Verify EdgeTTSProvider catches NoAudioReceived and retries with backoff."""
    from edge_tts.exceptions import NoAudioReceived

    provider = EdgeTTSProvider(max_retries=3)
    out = tmp_path / "retry_no_audio.mp3"

    call_count = 0

    def fake_run(coro):
        nonlocal call_count
        call_count += 1
        coro.close()
        if call_count == 1:
            raise NoAudioReceived("No audio was received. Please verify that your parameters are correct.")
        out.write_bytes(b"recovered edge audio")

    with patch.object(provider, "_run_async_safely", side_effect=fake_run):
        with patch.object(provider.video_processor, "get_audio_duration", return_value=2.1):
            with patch("time.sleep") as mock_sleep:
                res = provider.synthesize("សួស្តីកម្ពុជា", out, voice="km-KH-PisethNeural")
                assert res.duration_seconds == 2.1
                assert call_count == 2
                mock_sleep.assert_called_once_with(1.0)


def test_api_get_voices(client: TestClient):
    """Verify GET /api/tts/voices returns the supported voices."""
    res = client.get("/api/tts/voices")
    assert res.status_code == 200
    data = res.json()
    assert "voices" in data
    assert "default_provider" in data
    assert "default_voice" in data
    assert data["default_provider"] == "edge"
    assert data["default_voice"] == "km-KH-PisethNeural"

    voice_names = [v["voice"] for v in data["voices"]]
    assert "default" not in voice_names
    assert "km-KH-PisethNeural" in voice_names
    assert "km-KH-SreymomNeural" in voice_names


def test_api_voice_preview_validation(client: TestClient):
    """Verify validation on POST /api/tts/preview."""
    # Invalid voice
    res = client.post(
        "/api/tts/preview",
        json={"provider": "edge", "voice": "invalid_voice"},
    )
    assert res.status_code == 400

    # Text too long (> 200 chars)
    res = client.post(
        "/api/tts/preview",
        json={
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "text": "ក" * 205,
        },
    )
    assert res.status_code == 400


def test_api_voice_preview_success(client: TestClient, tmp_path: Path):
    """Verify POST /api/tts/preview returns audio/mpeg stream."""
    with patch("app.services.tts.edge.EdgeTTSProvider.synthesize") as mock_synth:
        def fake_synth(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"fake preview mp3 stream")
            return TTSAudioResult(
                audio_path=Path(output_path),
                duration_seconds=1.2,
                provider_name="edge",
                voice="km-KH-PisethNeural",
            )

        mock_synth.side_effect = fake_synth

        res = client.post(
            "/api/tts/preview",
            json={
                "provider": "edge",
                "voice": "km-KH-PisethNeural",
                "text": "សួស្តី KhmerDub",
            },
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/mpeg"
        assert res.content == b"fake preview mp3 stream"


def test_project_voice_selection_and_invalidation(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
):
    """Verify changing project voice updates project and invalidates audio and export."""
    # 1. Create project
    create_res = client.post("/api/projects", json={"title": "Voice Test Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Check default voice
    get_res = client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    pdata = get_res.json()
    assert pdata["tts_provider"] == "edge"
    assert pdata["tts_voice"] == "km-KH-PisethNeural"

    # Add dummy video and generated audio
    video = Video(
        project_id=project_id,
        filename="test.mp4",
        file_path=str(tmp_path / "dummy.mp4"),
        file_size_bytes=1000,
        exported_video_path=str(tmp_path / "exported.mp4"),
        is_export_outdated=False,
    )
    db_session.add(video)

    audio = GeneratedAudio(
        project_id=project_id,
        audio_path=str(tmp_path / "dummy.mp3"),
        duration_seconds=2.0,
        provider="gtts",
        voice="default",
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # 2. Update voice with invalid pairing
    patch_invalid = client.patch(
        f"/api/projects/{project_id}/voice",
        json={"tts_provider": "invalid", "tts_voice": "default"},
    )
    assert patch_invalid.status_code == 400

    # 3. Update voice to Sreymom
    patch_valid = client.patch(
        f"/api/projects/{project_id}/voice",
        json={"tts_provider": "edge", "tts_voice": "km-KH-SreymomNeural"},
    )
    assert patch_valid.status_code == 200
    updated_data = patch_valid.json()
    assert updated_data["tts_provider"] == "edge"
    assert updated_data["tts_voice"] == "km-KH-SreymomNeural"

    # 4. Verify invalidation flags
    db_session.expire_all()
    reloaded_audio = db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).first()
    reloaded_video = db_session.query(Video).filter(Video.project_id == project_id).first()

    assert reloaded_audio.is_outdated is True
    assert reloaded_video.is_export_outdated is True


def test_tts_worker_uses_project_voice(db_session: Session, tmp_path: Path):
    """Verify process_tts uses the voice and provider configured on the project."""
    project = Project(
        title="Edge TTS Project",
        original_language="en",
        target_language="km",
        tts_provider="edge",
        tts_voice="km-KH-SreymomNeural",
        status=ProjectStatus.TRANSLATED,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    segment = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="សួស្តីកម្ពុជា",
        is_outdated=False,
    )
    db_session.add(segment)

    job = ProcessingJob(
        project_id=project.id,
        job_type="tts",
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    with patch("app.services.tts.edge.EdgeTTSProvider.synthesize") as mock_synth:
        def fake_synth(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"edge fake audio")
            return TTSAudioResult(
                audio_path=Path(output_path),
                duration_seconds=3.1,
                provider_name="edge",
                voice="km-KH-SreymomNeural",
            )

        mock_synth.side_effect = fake_synth

        process_tts(project.id, job.id, db=db_session)

        db_session.refresh(job)
        db_session.refresh(project)
        assert job.status == JobStatus.COMPLETED
        assert project.status == ProjectStatus.VOICE_GENERATED

        audio = (
            db_session.query(GeneratedAudio)
            .filter(GeneratedAudio.project_id == project.id)
            .first()
        )
        assert audio is not None
        assert audio.provider == "edge"
        assert audio.voice == "km-KH-SreymomNeural"
        assert audio.duration_seconds == 3.1
        assert audio.is_outdated is False


def test_real_edge_tts_synthesis(tmp_path: Path):
    """Integration test with live Edge TTS service to synthesize Khmer speech for Piseth and Sreymom."""
    provider = EdgeTTSProvider()
    proc = FFmpegVideoProcessor()

    sample_text = "ជំរាបសួរ។ នេះជាការសាកល្បងសំឡេងខ្មែរ។"

    # Test Piseth (Male)
    out_piseth = tmp_path / "real_piseth.mp3"
    res_piseth = provider.synthesize(
        text=sample_text,
        output_path=out_piseth,
        voice="km-KH-PisethNeural",
    )
    assert out_piseth.exists()
    assert out_piseth.stat().st_size > 0
    assert res_piseth.duration_seconds > 0.5
    assert res_piseth.provider_name == "edge"
    assert res_piseth.voice == "km-KH-PisethNeural"
    dur_piseth = proc.get_audio_duration(out_piseth)
    assert dur_piseth > 0.5

    # Test Sreymom (Female)
    out_sreymom = tmp_path / "real_sreymom.mp3"
    res_sreymom = provider.synthesize(
        text=sample_text,
        output_path=out_sreymom,
        voice="km-KH-SreymomNeural",
    )
    assert out_sreymom.exists()
    assert out_sreymom.stat().st_size > 0
    assert res_sreymom.duration_seconds > 0.5
    assert res_sreymom.provider_name == "edge"
    assert res_sreymom.voice == "km-KH-SreymomNeural"
    dur_sreymom = proc.get_audio_duration(out_sreymom)
    assert dur_sreymom > 0.5


def test_edge_tts_dubbing_pipeline_compatibility(tmp_path: Path):
    """Verify Edge TTS generated MP3 audio works smoothly with AudioSynchronizationService."""
    provider = EdgeTTSProvider()
    proc = FFmpegVideoProcessor()
    synchronizer = AudioSynchronizationService(video_processor=proc)

    # Generate real Edge TTS audio segment
    sample_text = "សួស្តី KhmerDub AI"
    seg_mp3 = tmp_path / "edge_segment.mp3"
    result = provider.synthesize(
        text=sample_text,
        output_path=seg_mp3,
        voice="km-KH-PisethNeural",
    )
    assert seg_mp3.exists()

    timeline_wav = tmp_path / "dubbed_timeline.wav"
    t1 = TranscriptSegment(id="t1", project_id="p_test", segment_order=1, start_time=0.5, end_time=3.0, text="Hello AI")
    tr1 = TranslationSegment(id="tr1", project_id="p_test", segment_order=1, khmer_text=sample_text)
    a1 = GeneratedAudio(
        id="a1",
        project_id="p_test",
        translation_segment_id="tr1",
        audio_path=str(seg_mp3),
        duration_seconds=result.duration_seconds,
        provider="edge",
        voice="km-KH-PisethNeural",
    )

    sync_result = synchronizer.synchronize(
        project_id="p_test",
        segment_items=[(t1, tr1, a1)],
        target_duration=4.0,
        output_timeline_path=timeline_wav,
    )

    assert sync_result.timeline_path.exists()
    final_dur = proc.get_audio_duration(sync_result.timeline_path)
    assert abs(final_dur - 4.0) < 0.15


def test_tts_worker_resumes_without_resynthesizing_current_audio(db_session: Session, tmp_path: Path):
    """Verify process_tts skips segments that already have current valid audio on disk."""
    from app.workers.tts import get_audio_segment_path

    project = Project(
        title="Resume TTS Project",
        original_language="en",
        target_language="km",
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
        status=ProjectStatus.TRANSLATED,
    )
    db_session.add(project)
    db_session.commit()

    seg1 = TranslationSegment(project_id=project.id, segment_order=1, khmer_text="ផ្នែកមួយ", is_outdated=False)
    seg2 = TranslationSegment(project_id=project.id, segment_order=2, khmer_text="ផ្នែកពីរ", is_outdated=False)
    db_session.add_all([seg1, seg2])
    db_session.commit()

    # Seg1 already has a valid file and GeneratedAudio
    seg1_path = get_audio_segment_path(project.id, seg1.id)
    seg1_path.parent.mkdir(parents=True, exist_ok=True)
    seg1_path.write_bytes(b"existing audio bytes for seg1")

    aud1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=seg1.id,
        audio_path=str(seg1_path),
        duration_seconds=2.5,
        provider="edge",
        voice="km-KH-PisethNeural",
        is_outdated=False,
    )
    db_session.add(aud1)

    job = ProcessingJob(project_id=project.id, job_type="tts", status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    synthesized_segments = []

    with patch("app.workers.tts.synthesize_segment_audio") as mock_synth:
        def fake_synth(project_id, segment, **kwargs):
            synthesized_segments.append(segment.segment_order)
            out_p = get_audio_segment_path(project_id, segment.id)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(b"newly synthesized bytes")
            aud = GeneratedAudio(
                project_id=project_id,
                translation_segment_id=segment.id,
                audio_path=str(out_p),
                duration_seconds=1.5,
                provider="edge",
                voice="km-KH-PisethNeural",
                is_outdated=False,
            )
            db_session.add(aud)
            db_session.commit()
            return aud

        mock_synth.side_effect = fake_synth

        process_tts(project.id, job.id, db=db_session)

        # seg1 should be skipped because it is current; seg2 should be synthesized
        assert synthesized_segments == [2]
        db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED


def test_removed_google_voice_cannot_be_selected(client: TestClient):
    response = client.post("/api/projects", json={
        "title": "Removed voice", "tts_provider": "gtts", "tts_voice": "default",
    })
    assert response.status_code == 400
