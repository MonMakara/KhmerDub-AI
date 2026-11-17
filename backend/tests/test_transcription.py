import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.models.project import Project, Video, ProcessingJob, ProjectStatus, JobStatus
from app.services.transcription.base import TranscriptionSegment
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.exceptions import ModelLoadError
from app.workers.transcription import process_transcription


@dataclass
class DummySegment:
    start: float
    end: float
    text: str


@dataclass
class DummyInfo:
    language: str = "en"
    language_probability: float = 0.99


def test_transcription_provider_interface_with_mock(tmp_path: Path):
    audio_file = tmp_path / "test_audio.wav"
    audio_file.write_bytes(b"dummy audio content")

    mock_segments = [
        DummySegment(start=0.0, end=1.5, text="Hello world"),
        DummySegment(start=1.5, end=3.0, text="Welcome to KhmerDub AI"),
    ]

    provider = FasterWhisperTranscriptionProvider(model_size="base", device="cpu", compute_type="int8")

    with patch.object(provider, "get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter(mock_segments), DummyInfo())
        mock_get_model.return_value = mock_model

        results = provider.transcribe(audio_file, language="en")

        assert len(results) == 2
        assert results[0].segment_order == 1
        assert results[0].start_time == 0.0
        assert results[0].end_time == 1.5
        assert results[0].text == "Hello world"

        assert results[1].segment_order == 2
        assert results[1].start_time == 1.5
        assert results[1].end_time == 3.0
        assert results[1].text == "Welcome to KhmerDub AI"


def test_transcription_empty_audio_file(tmp_path: Path):
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")

    provider = FasterWhisperTranscriptionProvider()
    results = provider.transcribe(empty_file)
    assert results == []


def test_transcription_missing_audio_file(tmp_path: Path):
    missing_file = tmp_path / "nonexistent.wav"
    provider = FasterWhisperTranscriptionProvider()
    with pytest.raises(FileNotFoundError):
        provider.transcribe(missing_file)


def test_transcription_invalid_compute_type_on_cpu():
    provider = FasterWhisperTranscriptionProvider(device="cpu", compute_type="float16")
    with pytest.raises(ModelLoadError) as exc_info:
        provider.get_model()
    assert "not supported on CPU" in str(exc_info.value)


def test_transcription_api_missing_audio(client: TestClient):
    proj_res = client.post("/api/projects", json={"title": "No Audio Project"})
    proj_id = proj_res.json()["id"]

    res = client.post(f"/api/projects/{proj_id}/transcribe")
    assert res.status_code == 400
    assert "extracted audio file not found" in res.json()["detail"].lower()


def test_transcription_api_nonexistent_project(client: TestClient):
    res = client.post("/api/projects/invalid-id/transcribe")
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"


def test_transcription_workflow_and_crud(client: TestClient, db_session, tmp_path: Path):
    # 1. Setup project with video and extracted audio file in DB
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF dummy wav audio data")

    proj = Project(title="Full STT Test", status=ProjectStatus.AUDIO_EXTRACTED)
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    video = Video(
        project_id=proj.id,
        filename="sample.mp4",
        file_path=str(tmp_path / "sample.mp4"),
        file_size_bytes=1000,
        duration_seconds=3.0,
        extracted_audio_path=str(audio_path),
    )
    db_session.add(video)
    db_session.commit()

    # 2. Trigger transcription endpoint with mocked background provider
    mock_segments = [
        DummySegment(start=0.0, end=1.5, text="First sentence."),
        DummySegment(start=1.5, end=3.0, text="Second sentence."),
    ]

    with patch(
        "app.workers.transcription.FasterWhisperTranscriptionProvider.transcribe",
        return_value=[
            TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.5, text="First sentence."),
            TranscriptionSegment(segment_order=2, start_time=1.5, end_time=3.0, text="Second sentence."),
        ],
    ):
        res = client.post(f"/api/projects/{proj.id}/transcribe")
        assert res.status_code == 200
        job_data = res.json()
        assert job_data["job_type"] == "transcribe"
        assert job_data["status"] == "pending"
        job_id = job_data["id"]

        # Run worker synchronously
        process_transcription(proj.id, job_id, db=db_session)

    # 3. Verify project status is now 'transcribed'
    proj_detail = client.get(f"/api/projects/{proj.id}").json()
    assert proj_detail["status"] == "transcribed"

    # 4. GET /transcript
    transcript_res = client.get(f"/api/projects/{proj.id}/transcript")
    assert transcript_res.status_code == 200
    t_data = transcript_res.json()
    assert t_data["status"] == "transcribed"
    assert len(t_data["segments"]) == 2
    seg1 = t_data["segments"][0]
    assert seg1["text"] == "First sentence."
    assert seg1["start_time"] == 0.0

    # 5. PATCH /transcript/{segment_id}
    patch_res = client.patch(
        f"/api/projects/{proj.id}/transcript/{seg1['id']}",
        json={"text": "Edited first sentence."},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["text"] == "Edited first sentence."

    # Verify persistence
    updated_transcript = client.get(f"/api/projects/{proj.id}/transcript").json()
    assert updated_transcript["segments"][0]["text"] == "Edited first sentence."

    # 6. Test retranscription replaces segments without duplicates
    with patch(
        "app.workers.transcription.FasterWhisperTranscriptionProvider.transcribe",
        return_value=[
            TranscriptionSegment(segment_order=1, start_time=0.0, end_time=3.0, text="Single combined sentence."),
        ],
    ):
        res2 = client.post(f"/api/projects/{proj.id}/transcribe")
        assert res2.status_code == 200
        process_transcription(proj.id, res2.json()["id"], db=db_session)

    re_transcript = client.get(f"/api/projects/{proj.id}/transcript").json()
    assert len(re_transcript["segments"]) == 1
    assert re_transcript["segments"][0]["text"] == "Single combined sentence."


def test_concurrent_transcription_conflict(client: TestClient, db_session, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"dummy")

    proj = Project(title="Conflict Test", status=ProjectStatus.AUDIO_EXTRACTED)
    db_session.add(proj)
    db_session.commit()

    video = Video(
        project_id=proj.id,
        filename="test.mp4",
        file_path="test.mp4",
        file_size_bytes=100,
        extracted_audio_path=str(audio_path),
    )
    db_session.add(video)

    # Active job in progress
    active_job = ProcessingJob(
        project_id=proj.id,
        job_type="transcribe",
        status=JobStatus.RUNNING,
    )
    db_session.add(active_job)
    db_session.commit()

    # Attempt to trigger duplicate transcription
    res = client.post(f"/api/projects/{proj.id}/transcribe")
    assert res.status_code == 409
    assert "already in progress" in res.json()["detail"].lower()


def test_real_whisper_model_inference_execution(tmp_path: Path):
    """Real inference test using faster-whisper on CPU without mocks."""
    # Generate a clean 16kHz mono audio file with 1000Hz tone
    tone_wav = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-ar", "16000", "-ac", "1",
            str(tone_wav),
        ],
        check=True,
        capture_output=True,
    )

    provider = FasterWhisperTranscriptionProvider(
        model_size="tiny.en",
        device="cpu",
        compute_type="int8",
    )
    # Ensure real model initializes and transcribes without throwing errors
    segments = provider.transcribe(tone_wav, language="en")
    assert isinstance(segments, list)


def test_clean_whisper_text_annotations():
    """Verify that hallucinated music and sound effect annotations are stripped."""
    from app.services.transcription.whisper import clean_whisper_text

    assert clean_whisper_text("[Music]") == ""
    assert clean_whisper_text("(music)") == ""
    assert clean_whisper_text("♪♪♪") == ""
    assert clean_whisper_text("[Applause] Thank you everyone!") == "Thank you everyone!"
    assert clean_whisper_text("Hello world [Music] welcome back!") == "Hello world welcome back!"
    assert clean_whisper_text("[Laughter] That was funny.") == "That was funny."
    assert clean_whisper_text("   [music]   ") == ""
    assert clean_whisper_text("...") == ""
