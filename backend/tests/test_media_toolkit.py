"""
KhmerDub AI — Phase 13E.1: Media Toolkit Foundation Integration Tests
Tests video upload, audio extraction (MP3, WAV, M4A), stream copying,
project video reuse, error handling, storage isolation, and endpoints.
"""

import io
import json
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    get_project_original_dir,
    get_toolkit_task_dir,
)
from app.database.session import SessionLocal
from app.main import app
from app.models.project import Project, ProjectStatus, Video, TranscriptSegment as ProjectTranscriptSegment
from app.models.toolkit import ToolkitTask, ToolkitTranscriptSegment
from app.services.transcription.base import TranscriptionSegment
from unittest.mock import patch

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_video_with_audio(tmp_path: Path) -> Path:
    """Generate a valid 2.5s MP4 video with an AAC audio track."""
    video_path = tmp_path / "sample_with_aac.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2.5:size=320x240:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        str(video_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return video_path


@pytest.fixture
def sample_video_without_audio(tmp_path: Path) -> Path:
    """Generate a valid 2.0s MP4 video containing NO audio track."""
    video_path = tmp_path / "sample_silent.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2.0:size=320x240:rate=24",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return video_path


def test_toolkit_capabilities_endpoint():
    """Verify capabilities mapping returns correct modules, status, and language mappings."""
    resp = client.get("/api/toolkit/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "1.0.0"

    tools = {t["id"]: t for t in data["tools"]}
    assert "video_to_audio" in tools
    assert tools["video_to_audio"]["status"] == "available"
    assert tools["video_to_audio"]["supported_formats"] == ["mp3", "wav", "m4a"]

    # Phase 13E.2 Active tools
    assert "video_to_transcript" in tools
    assert tools["video_to_transcript"]["status"] == "available"
    assert "video_to_text" in tools
    assert tools["video_to_text"]["status"] == "available"
    assert "audio_to_transcript" in tools
    assert tools["audio_to_transcript"]["status"] == "available"
    assert "audio_to_text" in tools
    assert tools["audio_to_text"]["status"] == "available"

    # Future planned tools
    assert "text_to_speech" in tools
    assert tools["text_to_speech"]["status"] == "planned"


    # Language capability mapping
    assert "transcription" in data["language_capabilities"]
    assert "speech_synthesis" in data["language_capabilities"]


def test_extract_audio_mp3_from_uploaded_video(sample_video_with_audio: Path, db_session: Session):
    """Test extracting audio as MP3 from an uploaded video file."""
    with open(sample_video_with_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("test_video.mp4", f, "video/mp4")},
            data={"target_format": "mp3"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    task_id = data["id"]
    assert data["tool_type"] == "video_to_audio"
    assert data["target_format"] == "mp3"
    assert data["status"] == "completed"
    assert data["progress_percentage"] == 100
    assert data["output_filename"].endswith(".mp3")
    assert data["output_duration_seconds"] > 2.0
    assert data["output_file_size_bytes"] > 0
    assert data["output_media_metadata"]["codec_name"] == "mp3"

    # Verify task exists in database
    db_task = db_session.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
    assert db_task is not None
    assert db_task.status == "completed"

    # Cleanup task
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_extract_audio_wav_from_uploaded_video(sample_video_with_audio: Path):
    """Test extracting audio as uncompressed 16-bit PCM WAV."""
    with open(sample_video_with_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("test_video.mp4", f, "video/mp4")},
            data={"target_format": "wav"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    task_id = data["id"]
    assert data["target_format"] == "wav"
    assert data["output_filename"].endswith(".wav")
    assert data["output_media_metadata"]["codec_name"] == "pcm_s16le"
    assert data["output_duration_seconds"] > 2.0

    # Cleanup
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_extract_audio_m4a_stream_remux(sample_video_with_audio: Path):
    """Test extracting AAC audio as M4A using direct stream remuxing without lossy re-encoding."""
    with open(sample_video_with_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("test_video.mp4", f, "video/mp4")},
            data={"target_format": "m4a"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    task_id = data["id"]
    assert data["target_format"] == "m4a"
    assert data["output_filename"].endswith(".m4a")
    assert data["output_media_metadata"]["codec_name"] == "aac"

    # Cleanup
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_extract_audio_reusing_project_video(db_session: Session, sample_video_with_audio: Path):
    """Test extracting audio by referencing an existing project video without re-uploading or duplicating storage."""
    proj_id = str(uuid.uuid4())
    project = Project(
        id=proj_id,
        title="Toolkit Project Video Test",
        status=ProjectStatus.UPLOADED,
    )
    db_session.add(project)

    # Place video in project storage
    orig_dir = get_project_original_dir(proj_id)
    dest_video = orig_dir / "project_source.mp4"
    dest_video.write_bytes(sample_video_with_audio.read_bytes())

    video_rec = Video(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        filename="project_source.mp4",
        file_path=str(dest_video),
        file_size_bytes=dest_video.stat().st_size,
        duration_seconds=2.5,
        video_codec="h264",
        audio_codec="aac",
    )
    db_session.add(video_rec)
    db_session.commit()

    resp = client.post(
        "/api/toolkit/extract-audio",
        data={"project_id": proj_id, "target_format": "mp3"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    task_id = data["id"]
    assert data["source_type"] == "project"
    assert data["source_project_id"] == proj_id
    assert data["source_filename"] == "project_source.mp4"
    assert data["status"] == "completed"
    assert data["output_duration_seconds"] > 2.0

    # Ensure project original video file was NOT modified or moved
    assert dest_video.exists()
    assert dest_video.stat().st_size > 0

    # Cleanup
    client.delete(f"/api/toolkit/tasks/{task_id}")
    db_session.query(Video).filter(Video.project_id == proj_id).delete()
    db_session.query(Project).filter(Project.id == proj_id).delete()
    db_session.commit()
    import shutil
    shutil.rmtree(orig_dir.parent, ignore_errors=True)


def test_extract_audio_silent_video_fails(sample_video_without_audio: Path):
    """Test that attempting to extract audio from a video without an audio track raises HTTP 400."""
    with open(sample_video_without_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("silent_video.mp4", f, "video/mp4")},
            data={"target_format": "mp3"},
        )

    assert resp.status_code == 400
    assert "does not contain an audio track" in resp.json()["detail"]


def test_extract_audio_invalid_corrupted_file():
    """Test that empty or non-media file upload raises HTTP 400."""
    corrupted_data = b"This is not a real video file contents."
    resp = client.post(
        "/api/toolkit/extract-audio",
        files={"file": ("fake_video.mp4", io.BytesIO(corrupted_data), "video/mp4")},
        data={"target_format": "mp3"},
    )
    assert resp.status_code == 400


def test_extract_audio_unsupported_format(sample_video_with_audio: Path):
    """Test that requesting an unsupported target format (e.g. ogg or flac) raises HTTP 400."""
    with open(sample_video_with_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("test_video.mp4", f, "video/mp4")},
            data={"target_format": "flac"},
        )
    assert resp.status_code == 400
    assert "Unsupported target format" in resp.json()["detail"]


def test_audio_streaming_and_download_endpoints(sample_video_with_audio: Path):
    """Test preview streaming and attachment download endpoints."""
    with open(sample_video_with_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/extract-audio",
            files={"file": ("stream_test.mp4", f, "video/mp4")},
            data={"target_format": "mp3"},
        )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # 1. Test Stream Endpoint
    stream_resp = client.get(f"/api/toolkit/tasks/{task_id}/stream")
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"] == "audio/mpeg"
    assert stream_resp.headers["content-disposition"].startswith("inline")
    assert len(stream_resp.content) > 0

    # 2. Test Download Endpoint
    dl_resp = client.get(f"/api/toolkit/tasks/{task_id}/download")
    assert dl_resp.status_code == 200
    assert "attachment" in dl_resp.headers["content-disposition"]
    assert len(dl_resp.content) == len(stream_resp.content)

    # 3. Test Task Details and List Endpoints
    get_resp = client.get(f"/api/toolkit/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id

    list_resp = client.get("/api/toolkit/tasks?tool_type=video_to_audio")
    assert list_resp.status_code == 200
    task_ids = [t["id"] for t in list_resp.json()]
    assert task_id in task_ids

    # 4. Test Task Deletion and Storage Isolation
    del_resp = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Confirm storage workspace directory was deleted
    task_dir = get_toolkit_task_dir(task_id)
    assert not task_dir.exists()


@pytest.fixture
def sample_audio_wav(tmp_path: Path) -> Path:
    """Generate a valid 2.0s 16kHz mono WAV audio file."""
    audio_path = tmp_path / "sample_audio.wav"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return audio_path


@pytest.fixture
def sample_audio_mp3(tmp_path: Path) -> Path:
    """Generate a valid 2.0s MP3 audio file."""
    audio_path = tmp_path / "sample_audio.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return audio_path


def test_video_to_transcript_uploaded_video(sample_video_with_audio: Path):
    """Test transcribing an uploaded video into timestamped segments (video_to_transcript)."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.2, text="Welcome to KhmerDub AI."),
        TranscriptionSegment(segment_order=2, start_time=1.2, end_time=2.4, text="Standalone transcription works perfectly."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("speech_video.mp4", f, "video/mp4")},
                data={
                    "tool_type": "video_to_transcript",
                    "target_format": "srt",
                    "language": "en",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_type"] == "video_to_transcript"
        assert data["status"] == "completed"
        assert len(data["segments"]) == 2
        assert data["segments"][0]["text"] == "Welcome to KhmerDub AI."
        assert data["segments"][0]["start_time"] == 0.0
        assert data["segments"][0]["end_time"] == 1.2
        assert data["segments"][1]["text"] == "Standalone transcription works perfectly."
        assert data["full_text"] == "Welcome to KhmerDub AI.\n\nStandalone transcription works perfectly."

        # Verify task is retrievable via GET
        task_id = data["id"]
        get_res = client.get(f"/api/toolkit/tasks/{task_id}")
        assert get_res.status_code == 200
        assert len(get_res.json()["segments"]) == 2


def test_audio_to_transcript_uploaded_audio(sample_audio_wav: Path):
    """Test transcribing standalone audio recording into timestamped segments (audio_to_transcript)."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.8, text="This is an audio recording."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_audio_wav, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("recording.wav", f, "audio/wav")},
                data={
                    "tool_type": "audio_to_transcript",
                    "target_format": "vtt",
                    "language": "en",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_type"] == "audio_to_transcript"
        assert len(data["segments"]) == 1
        assert data["segments"][0]["text"] == "This is an audio recording."


def test_video_to_text_plain_text(sample_video_with_audio: Path):
    """Test converting video speech to flowing plain text (video_to_text)."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.0, text="First sentence from video."),
        TranscriptionSegment(segment_order=2, start_time=1.0, end_time=2.2, text="Second sentence from video."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("talk.mp4", f, "video/mp4")},
                data={
                    "tool_type": "video_to_text",
                    "target_format": "txt",
                    "language": "en",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_type"] == "video_to_text"
        assert "First sentence from video." in data["full_text"]
        assert "Second sentence from video." in data["full_text"]


def test_audio_to_text_plain_text(sample_audio_mp3: Path):
    """Test converting standalone MP3 audio to flowing plain text (audio_to_text)."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.5, text="Podcast episode notes."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_audio_mp3, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("podcast.mp3", f, "audio/mpeg")},
                data={
                    "tool_type": "audio_to_text",
                    "target_format": "txt",
                    "language": "en",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_type"] == "audio_to_text"
        assert data["full_text"] == "Podcast episode notes."


def test_transcribe_reusing_project_transcripts(sample_video_with_audio: Path, db_session: Session):
    """Test that existing project transcripts are reused directly without re-transcribing."""
    # 1. Create project with video and transcript segments in DB
    proj = Project(
        id=str(uuid.uuid4()),
        title="Project With Transcript",
        status=ProjectStatus.TRANSCRIBED.value,
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        filename="project_video.mp4",
        file_path=str(sample_video_with_audio),
        file_size_bytes=sample_video_with_audio.stat().st_size,
        duration_seconds=2.5,
    )
    db_session.add(video)

    seg1 = ProjectTranscriptSegment(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        segment_order=1,
        start_time=0.0,
        end_time=1.5,
        text="Existing project line one.",
    )
    seg2 = ProjectTranscriptSegment(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        segment_order=2,
        start_time=1.5,
        end_time=2.5,
        text="Existing project line two.",
    )
    db_session.add_all([seg1, seg2])
    db_session.commit()

    # 2. Transcribe using project_id with reuse_existing=True
    # whisper_provider.transcribe should NOT be called!
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe") as mock_whisper:
        resp = client.post(
            "/api/toolkit/transcribe",
            data={
                "project_id": proj.id,
                "tool_type": "video_to_transcript",
                "target_format": "srt",
                "reuse_existing": "true",
            },
        )
        assert resp.status_code == 200
        mock_whisper.assert_not_called()

        data = resp.json()
        assert data["status"] == "completed"
        assert len(data["segments"]) == 2
        assert data["segments"][0]["text"] == "Existing project line one."
        assert data["segments"][1]["text"] == "Existing project line two."
        assert "reused_from_project" in json.dumps(data["output_media_metadata"])


def test_transcribe_khmer_language_unsupported_notice():
    """Test that requesting Khmer language explicitly returns a clear descriptive 400 error."""
    resp = client.post(
        "/api/toolkit/transcribe",
        data={
            "project_id": "dummy-project",
            "language": "km",
        },
    )
    assert resp.status_code == 400
    assert "Khmer speech recognition is not officially supported" in resp.json()["detail"]


def test_segment_edit_and_persistence(sample_video_with_audio: Path):
    """Test editing a transcript segment, verifying that edits persist across GET reloads."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.5, text="Original unedited text."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("edit_test.mp4", f, "video/mp4")},
                data={"tool_type": "video_to_transcript"},
            )
    assert resp.status_code == 200
    task_id = resp.json()["id"]
    segment_id = resp.json()["segments"][0]["id"]
    assert resp.json()["segments"][0]["is_edited"] is False

    # 1. Update segment text
    edit_resp = client.put(
        f"/api/toolkit/tasks/{task_id}/segments/{segment_id}",
        json={"text": "Corrected and verified text."},
    )
    assert edit_resp.status_code == 200
    edited_data = edit_resp.json()
    assert edited_data["text"] == "Corrected and verified text."
    assert edited_data["raw_text"] == "Original unedited text."
    assert edited_data["edited_text"] == "Corrected and verified text."
    assert edited_data["is_edited"] is True

    # 2. Reload task via GET and verify persistence across requests
    get_resp = client.get(f"/api/toolkit/tasks/{task_id}")
    assert get_resp.status_code == 200
    reloaded_seg = get_resp.json()["segments"][0]
    assert reloaded_seg["text"] == "Corrected and verified text."
    assert reloaded_seg["is_edited"] is True
    assert get_resp.json()["full_text"] == "Corrected and verified text."


def test_segment_reset_edits_single_and_all(sample_video_with_audio: Path):
    """Test resetting segment edits back to original verbatim raw ASR text."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.0, text="Raw line 1."),
        TranscriptionSegment(segment_order=2, start_time=1.0, end_time=2.0, text="Raw line 2."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("reset_test.mp4", f, "video/mp4")},
                data={"tool_type": "video_to_transcript"},
            )
    task_id = resp.json()["id"]
    seg1_id = resp.json()["segments"][0]["id"]
    seg2_id = resp.json()["segments"][1]["id"]

    # Edit both segments
    client.put(f"/api/toolkit/tasks/{task_id}/segments/{seg1_id}", json={"text": "Edited line 1."})
    client.put(f"/api/toolkit/tasks/{task_id}/segments/{seg2_id}", json={"text": "Edited line 2."})

    # Reset single segment (seg1)
    reset_single_resp = client.post(
        f"/api/toolkit/tasks/{task_id}/reset-edits",
        json={"segment_id": seg1_id},
    )
    assert reset_single_resp.status_code == 200
    get_after_single = client.get(f"/api/toolkit/tasks/{task_id}").json()
    assert get_after_single["segments"][0]["text"] == "Raw line 1."
    assert get_after_single["segments"][0]["is_edited"] is False
    assert get_after_single["segments"][1]["text"] == "Edited line 2."
    assert get_after_single["segments"][1]["is_edited"] is True

    # Reset all remaining edits
    reset_all_resp = client.post(f"/api/toolkit/tasks/{task_id}/reset-edits")
    assert reset_all_resp.status_code == 200
    get_after_all = client.get(f"/api/toolkit/tasks/{task_id}").json()
    assert get_after_all["segments"][0]["text"] == "Raw line 1."
    assert get_after_all["segments"][1]["text"] == "Raw line 2."
    assert get_after_all["segments"][1]["is_edited"] is False


def test_export_transcripts_formats(sample_video_with_audio: Path):
    """Test exporting transcript in TXT, SRT, VTT, JSON, and CSV formats."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.5, text="First export line."),
        TranscriptionSegment(segment_order=2, start_time=1.5, end_time=3.0, text="Second export line."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("export_test.mp4", f, "video/mp4")},
                data={"tool_type": "video_to_transcript"},
            )
    task_id = resp.json()["id"]

    # 1. TXT
    txt_resp = client.get(f"/api/toolkit/tasks/{task_id}/export/txt")
    assert txt_resp.status_code == 200
    assert "First export line." in txt_resp.text
    assert "Second export line." in txt_resp.text

    # 2. SRT
    srt_resp = client.get(f"/api/toolkit/tasks/{task_id}/export/srt")
    assert srt_resp.status_code == 200
    assert "00:00:00,000 --> 00:00:01,500" in srt_resp.text
    assert "First export line." in srt_resp.text

    # 3. VTT
    vtt_resp = client.get(f"/api/toolkit/tasks/{task_id}/export/vtt")
    assert vtt_resp.status_code == 200
    assert "WEBVTT" in vtt_resp.text
    assert "00:00:00.000 --> 00:00:01.500" in vtt_resp.text

    # 4. JSON
    json_resp = client.get(f"/api/toolkit/tasks/{task_id}/export/json")
    assert json_resp.status_code == 200
    json_cues = json_resp.json()
    assert len(json_cues) == 2
    assert json_cues[0]["text"] == "First export line."

    # 5. CSV
    csv_resp = client.get(f"/api/toolkit/tasks/{task_id}/export/csv")
    assert csv_resp.status_code == 200
    assert "sequence,start_time,end_time,duration_seconds" in csv_resp.text
    assert "First export line." in csv_resp.text


def test_transcribe_silent_video(sample_video_without_audio: Path):
    """Test that uploading a silent video without an audio track raises HTTP 400 gracefully."""
    with open(sample_video_without_audio, "rb") as f:
        resp = client.post(
            "/api/toolkit/transcribe",
            files={"file": ("silent.mp4", f, "video/mp4")},
            data={"tool_type": "video_to_transcript"},
        )
    assert resp.status_code == 400
    assert "does not contain an audio track" in resp.json()["detail"].lower()


def test_transcription_deletion_cascades_segments(sample_video_with_audio: Path, db_session: Session):
    """Test that deleting a transcription task cascades and cleans up all segment records and workspace files."""
    mock_segments = [
        TranscriptionSegment(segment_order=1, start_time=0.0, end_time=1.0, text="Temp line."),
    ]
    with patch("app.api.endpoints.toolkit.whisper_provider.transcribe", return_value=mock_segments):
        with open(sample_video_with_audio, "rb") as f:
            resp = client.post(
                "/api/toolkit/transcribe",
                files={"file": ("cascade_test.mp4", f, "video/mp4")},
                data={"tool_type": "video_to_transcript"},
            )
    task_id = resp.json()["id"]

    # Verify segments exist in DB
    segs = db_session.query(ToolkitTranscriptSegment).filter(ToolkitTranscriptSegment.task_id == task_id).all()
    assert len(segs) == 1

    # Delete task
    del_res = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_res.status_code == 200

    # Verify segments were cascaded in DB
    segs_after = db_session.query(ToolkitTranscriptSegment).filter(ToolkitTranscriptSegment.task_id == task_id).all()
    assert len(segs_after) == 0

    # Verify task directory cleaned up
    assert not get_toolkit_task_dir(task_id).exists()

