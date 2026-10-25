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
from app.models.project import Project, ProjectStatus, Video
from app.models.toolkit import ToolkitTask

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

    # Planned tools
    assert "video_to_transcript" in tools
    assert tools["video_to_transcript"]["status"] == "planned"
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
