"""
KhmerDub AI — Phase 13C: VoxCPM2 Custom Voice Cloning Integration Tests
Tests provider interface, database authorization checks, audio transcode/sync,
outdated audio invalidation, error resilience, and end-to-end dubbing compatibility.
"""

import shutil
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.storage import (
    get_audio_segment_path,
    get_project_output_dir,
    get_timeline_audio_path,
    get_voice_profile_audio_path,
)
from app.database.session import SessionLocal
from app.main import app
from app.models.project import (
    GeneratedAudio,
    JobStatus,
    ProcessingJob,
    Project,
    ProjectStatus,
    TranscriptSegment,
    TranslationSegment,
    Video,
)
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.tts.base import TTSAudioResult
from app.services.tts.exceptions import (
    EmptyTextError,
    TTSNetworkError,
    VoiceNotSupportedError,
)
from app.services.tts.registry import (
    get_tts_provider,
    is_valid_voice_combination,
    list_supported_voices,
)
from app.services.tts.voxcpm import VoxCPM2TTSProvider

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def authorized_profile(db_session: Session):
    """Fixture providing an authorized custom voice profile with dummy reference audio."""
    profile_id = str(uuid.uuid4())
    consent_id = str(uuid.uuid4())

    consent = VoiceConsent(
        id=consent_id,
        speaker_name="Authorized Tester",
        authorized_by="Admin",
        consent_statement="I authorize custom voice cloning.",
        is_authorized=True,
        signature_hash="test_signature_hash_12345",
    )
    db_session.add(consent)

    profile = VoiceProfile(
        id=profile_id,
        name="Test_Authorized_Voice",
        gender="male",
        language="km",
        reference_audio_path=f"voice_profiles/{profile_id}/reference.wav",
        reference_audio_duration=10.0,
        reference_audio_sample_rate=48000,
        audio_format="wav",
        is_active=True,
        consent_id=consent_id,
    )
    db_session.add(profile)
    db_session.commit()

    # Create dummy reference WAV on disk
    audio_path = get_voice_profile_audio_path(profile_id)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    # Generate 1-second 48kHz mono test tone
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    yield profile

    # Cleanup
    db_session.query(VoiceProfile).filter(VoiceProfile.id == profile_id).delete()
    db_session.query(VoiceConsent).filter(VoiceConsent.id == consent_id).delete()
    db_session.commit()
    if audio_path.parent.exists():
        shutil.rmtree(audio_path.parent, ignore_errors=True)


@pytest.fixture
def unauthorized_profile(db_session: Session):
    """Fixture providing an unauthorized voice profile (consent is_authorized = False)."""
    profile_id = str(uuid.uuid4())
    consent_id = str(uuid.uuid4())

    consent = VoiceConsent(
        id=consent_id,
        speaker_name="Unauthorized Speaker",
        authorized_by="Unknown",
        consent_statement="No consent.",
        is_authorized=False,
        signature_hash="unauthorized_hash_000",
    )
    db_session.add(consent)

    profile = VoiceProfile(
        id=profile_id,
        name="Test_Unauthorized_Voice",
        gender="female",
        language="km",
        reference_audio_path=f"voice_profiles/{profile_id}/reference.wav",
        is_active=True,
        consent_id=consent_id,
    )
    db_session.add(profile)
    db_session.commit()

    yield profile

    db_session.query(VoiceProfile).filter(VoiceProfile.id == profile_id).delete()
    db_session.query(VoiceConsent).filter(VoiceConsent.id == consent_id).delete()
    db_session.commit()


def test_custom_voice_registry_and_validation(authorized_profile, unauthorized_profile, db_session):
    """Verify registry correctly lists and validates authorized vs unauthorized custom voices."""
    voices = list_supported_voices(db=db_session)
    custom_entries = [v for v in voices if v.get("is_custom")]

    # Authorized profile must appear
    assert any(v["voice"] == authorized_profile.id for v in custom_entries)

    # Unauthorized profile must NOT appear
    assert not any(v["voice"] == unauthorized_profile.id for v in custom_entries)

    # Validation checks
    assert is_valid_voice_combination("voxcpm", authorized_profile.id, db=db_session) is True
    assert is_valid_voice_combination("voxcpm", unauthorized_profile.id, db=db_session) is False
    assert is_valid_voice_combination("voxcpm", "nonexistent-profile-id", db=db_session) is False

    # Factory instantiation
    provider = get_tts_provider("voxcpm")
    assert isinstance(provider, VoxCPM2TTSProvider)


def test_voxcpm_provider_input_validations(authorized_profile, unauthorized_profile, tmp_path):
    """Verify input validations, unauthorized profile rejection, and missing audio handling."""
    provider = VoxCPM2TTSProvider()
    out = tmp_path / "out.mp3"

    # Empty text
    with pytest.raises(EmptyTextError):
        provider.synthesize("", out, voice=authorized_profile.id)

    # Default voice rejected (requires custom profile)
    with pytest.raises(VoiceNotSupportedError):
        provider.synthesize("សួស្តី", out, voice="default")

    # Unauthorized profile rejected
    with pytest.raises(VoiceNotSupportedError) as exc_info:
        provider.synthesize("សួស្តី", out, voice=unauthorized_profile.id)
    assert "legal consent" in str(exc_info.value).lower()

    # Non-existent profile
    with pytest.raises(VoiceNotSupportedError):
        provider.synthesize("សួស្តី", out, voice=str(uuid.uuid4()))


def test_voxcpm_offline_worker_handling(authorized_profile, tmp_path):
    """Verify clean error message when GPU worker is offline."""
    # Point provider to non-existent port
    provider = VoxCPM2TTSProvider(worker_url="http://127.0.0.1:59999")
    assert provider.is_worker_online() is False

    out = tmp_path / "out.mp3"
    with pytest.raises(TTSNetworkError) as exc_info:
        provider.synthesize("សួស្តី", out, voice=authorized_profile.id)
    assert "offline" in str(exc_info.value).lower()


def test_voxcpm_mocked_synthesis_and_mp3_transcode(authorized_profile, tmp_path):
    """Verify synthesis flow and automatic transcode to 192k MP3."""
    provider = VoxCPM2TTSProvider()
    out_mp3 = tmp_path / "segment.mp3"

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        if "/health" in url:
            mock_resp.read.return_value = b'{"status": "online", "gpu_name": "RTX 4060", "vram_free_gb": 6.5}'
            return mock_resp
        elif "/synthesize" in url:
            import json
            body = json.loads(req.data.decode("utf-8"))
            out_p = Path(body["output_audio_path"])
            out_p.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "sine=frequency=500:duration=2.5",
                "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                str(out_p),
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            mock_resp.read.return_value = b'{"success": true, "duration_seconds": 2.5, "sample_rate": 48000, "generation_time_s": 2.1}'
            return mock_resp

        raise ValueError(f"Unexpected url {url}")

    with patch("app.services.tts.voxcpm.urllib.request.urlopen", side_effect=mock_urlopen):
        result = provider.synthesize(
            text="សួស្តីបងប្អូនទាំងអស់គ្នា",
            output_path=out_mp3,
            voice=authorized_profile.id,
        )

        assert isinstance(result, TTSAudioResult)
        assert result.provider_name == "voxcpm"
        assert result.voice == authorized_profile.id
        assert out_mp3.exists()
        assert out_mp3.stat().st_size > 0
        assert result.duration_seconds > 2.0


def test_api_tts_voices_includes_custom_voices(authorized_profile):
    """Verify GET /api/tts/voices includes custom authorized voice."""
    res = client.get("/api/tts/voices")
    assert res.status_code == 200
    data = res.json()
    assert "voices" in data

    custom_voice = next((v for v in data["voices"] if v["voice"] == authorized_profile.id), None)
    assert custom_voice is not None
    assert custom_voice["provider"] == "voxcpm"
    assert custom_voice["is_custom"] is True


@patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", new=lambda self: True)
def test_project_voice_selection_and_audio_invalidation(authorized_profile, db_session):
    """Verify changing project voice to custom voice marks existing audio and exports as outdated."""
    proj = Project(
        title="VoxCPM Project Test",
        original_language="en",
        target_language="km",
        tts_provider="gtts",
        tts_voice="default",
        status=ProjectStatus.COMPLETED,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    # Add video record with exported path
    video = Video(
        project_id=proj.id,
        filename="test.mp4",
        file_path="uploads/test.mp4",
        file_size_bytes=1024,
        duration_seconds=10.0,
        exported_video_path="outputs/test_out.mp4",
        is_export_outdated=False,
    )
    db_session.add(video)

    # Add existing generated audio
    audio = GeneratedAudio(
        project_id=proj.id,
        audio_path="temp/audio1.mp3",
        duration_seconds=3.0,
        provider="gtts",
        voice="default",
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Update project voice to custom voice
    res = client.patch(
        f"/api/projects/{proj.id}/voice",
        json={"tts_provider": "voxcpm", "tts_voice": authorized_profile.id},
    )
    assert res.status_code == 200
    updated_proj = res.json()
    assert updated_proj["tts_provider"] == "voxcpm"
    assert updated_proj["tts_voice"] == authorized_profile.id

    # Verify existing audio was marked outdated
    db_session.refresh(audio)
    assert audio.is_outdated is True

    # Verify export is marked outdated
    db_session.refresh(video)
    assert video.is_export_outdated is True

    # Cleanup
    db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == proj.id).delete()
    db_session.query(Video).filter(Video.project_id == proj.id).delete()
    db_session.query(Project).filter(Project.id == proj.id).delete()
    db_session.commit()


def test_dubbing_synchronization_with_voxcpm_audio(authorized_profile, tmp_path, db_session):
    """Verify AudioSynchronizationService seamlessly aligns VoxCPM2 generated audio."""
    proj_id = str(uuid.uuid4())
    t_seg_id = str(uuid.uuid4())
    trans_seg_id = str(uuid.uuid4())

    proj = Project(id=proj_id, title="Sync Test", original_language="en", target_language="km")
    db_session.add(proj)

    t_seg = TranscriptSegment(
        id=t_seg_id, project_id=proj_id, segment_order=1, start_time=1.0, end_time=4.0, text="Hello world"
    )
    db_session.add(t_seg)

    trans_seg = TranslationSegment(
        id=trans_seg_id, project_id=proj_id, transcript_segment_id=t_seg_id, segment_order=1, khmer_text="សួស្តីពិភពលោក"
    )
    db_session.add(trans_seg)

    # Generate test audio at segment path
    audio_path = get_audio_segment_path(proj_id, trans_seg_id)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0", "-ar", "48000", "-ac", "1", str(audio_path)],
        capture_output=True, check=True
    )

    audio_rec = GeneratedAudio(
        project_id=proj_id,
        translation_segment_id=trans_seg_id,
        audio_path=str(audio_path),
        duration_seconds=3.0,
        provider="voxcpm",
        voice=authorized_profile.id,
        is_outdated=False,
    )
    db_session.add(audio_rec)
    db_session.commit()

    sync_service = AudioSynchronizationService()
    timeline_path = get_timeline_audio_path(proj_id)

    res = sync_service.synchronize(
        project_id=proj_id,
        segment_items=[(t_seg, trans_seg, audio_rec)],
        target_duration=5.0,
        output_timeline_path=timeline_path,
    )

    assert timeline_path.exists()
    assert timeline_path.stat().st_size > 0
    assert len(res.conflicts) == 0

    # Cleanup
    db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == proj_id).delete()
    db_session.query(TranslationSegment).filter(TranslationSegment.project_id == proj_id).delete()
    db_session.query(TranscriptSegment).filter(TranscriptSegment.project_id == proj_id).delete()
    db_session.query(Project).filter(Project.id == proj_id).delete()
    db_session.commit()
    shutil.rmtree(get_project_output_dir(proj_id), ignore_errors=True)


def test_voxcpm_seed_parameter_forwarded_to_worker(authorized_profile: VoiceProfile, tmp_path: Path):
    """Phase 13D: Verify that seed parameter is forwarded in the request payload to the GPU worker."""
    provider = VoxCPM2TTSProvider()
    out_path = tmp_path / "final_test.wav"
    worker_wav = tmp_path / "worker_out.wav"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = (
        b'{"success": true, "duration_seconds": 2.5, "sample_rate": 48000, "generation_time_s": 1.2, "output_audio_path": "'
        + str(worker_wav).encode("utf-8")
        + b'", "peak_vram_gb": 5.5, "cache_hit": true}'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    captured_payloads = []

    def mock_urlopen(req, *args, **kwargs):
        if hasattr(req, "data") and req.data:
            import json
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
        return mock_resp

    with patch.object(provider, "check_worker_health", return_value={"status": "online", "url": "http://127.0.0.1:8002"}):
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Create dummy worker output file so copy/transcode succeeds
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.5", "-ar", "48000", "-ac", "1", str(worker_wav)],
                capture_output=True, check=True
            )
            result = provider.synthesize(
                text="សូមស្វាគមន៍",
                output_path=out_path,
                voice=authorized_profile.id,
                seed=998877,
            )

    assert result.duration_seconds > 0
    assert out_path.exists()
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["seed"] == 998877
    assert captured_payloads[0]["text"] == "សូមស្វាគមន៍"


@patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", new=lambda self: True)
def test_multi_segment_project_seed_deterministic_derivation(db_session: Session, authorized_profile: VoiceProfile):
    """Phase 13D: Verify process_tts derives deterministic seed and synthesizes all segments consistently."""
    import hashlib
    from app.workers.tts import process_tts

    proj_id = str(uuid.uuid4())
    expected_seed = int(hashlib.md5(proj_id.encode("utf-8")).hexdigest()[:8], 16)

    project = Project(
        id=proj_id,
        title="Test Multi Segment Determinism",
        tts_provider="voxcpm",
        tts_voice=authorized_profile.id,
        status=ProjectStatus.TRANSLATED,
    )
    db_session.add(project)

    t_seg_1 = TranscriptSegment(id=f"{proj_id}-ts-1", project_id=proj_id, segment_order=1, start_time=0.0, end_time=3.0, text="One")
    t_seg_2 = TranscriptSegment(id=f"{proj_id}-ts-2", project_id=proj_id, segment_order=2, start_time=3.5, end_time=6.5, text="Two")
    db_session.add_all([t_seg_1, t_seg_2])
    db_session.flush()

    tr_seg_1 = TranslationSegment(id=f"{proj_id}-tr-1", project_id=proj_id, transcript_segment_id=t_seg_1.id, segment_order=1, khmer_text="មួយ")
    tr_seg_2 = TranslationSegment(id=f"{proj_id}-tr-2", project_id=proj_id, transcript_segment_id=t_seg_2.id, segment_order=2, khmer_text="ពីរ")
    db_session.add_all([tr_seg_1, tr_seg_2])

    job = ProcessingJob(id=f"job-{proj_id}", project_id=proj_id, job_type="tts", status=JobStatus.PENDING, progress_percentage=0)
    db_session.add(job)
    db_session.commit()

    captured_seeds = []

    def mock_synthesize(text, output_path, voice=None, seed=None, **kwargs):
        captured_seeds.append(seed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0", "-ar", "48000", "-ac", "1", str(output_path)],
            capture_output=True, check=True
        )
        return TTSAudioResult(audio_path=output_path, duration_seconds=2.0, provider_name="voxcpm", voice=voice or "default")

    with patch("app.workers.tts.get_tts_provider") as mock_get_provider:
        mock_provider = MagicMock()
        mock_provider.synthesize.side_effect = mock_synthesize
        mock_get_provider.return_value = mock_provider

        process_tts(proj_id, job.id, db=db_session)

    db_session.refresh(job)
    db_session.refresh(project)
    assert job.status == JobStatus.COMPLETED
    assert project.status == ProjectStatus.VOICE_GENERATED
    assert len(captured_seeds) == 2
    assert captured_seeds[0] == expected_seed
    assert captured_seeds[1] == expected_seed

    # Cleanup
    db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == proj_id).delete()
    db_session.query(TranslationSegment).filter(TranslationSegment.project_id == proj_id).delete()
    db_session.query(TranscriptSegment).filter(TranscriptSegment.project_id == proj_id).delete()
    db_session.query(ProcessingJob).filter(ProcessingJob.project_id == proj_id).delete()
    db_session.query(Project).filter(Project.id == proj_id).delete()
    db_session.commit()
    shutil.rmtree(get_project_output_dir(proj_id), ignore_errors=True)
