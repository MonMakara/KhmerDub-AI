import io
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.models.project import Project
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import (
    CorruptedVideoError,
    NoAudioTrackError,
)


@pytest.fixture(scope="session")
def sample_video_with_audio(tmp_path_factory) -> Path:
    """Generate a tiny valid MP4 video with audio using FFmpeg."""
    out_dir = tmp_path_factory.mktemp("media")
    video_path = out_dir / "valid_sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264",
        "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


@pytest.fixture(scope="session")
def sample_video_silent(tmp_path_factory) -> Path:
    """Generate a tiny valid MP4 video without audio track."""
    out_dir = tmp_path_factory.mktemp("media_silent")
    video_path = out_dir / "silent_sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
        "-c:v", "libx264",
        "-an",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


def test_ffmpeg_processor_metadata_valid(sample_video_with_audio: Path):
    processor = FFmpegVideoProcessor()
    meta = processor.get_metadata(sample_video_with_audio)
    assert meta.duration_seconds > 0.5
    assert meta.width == 320
    assert meta.height == 240
    assert meta.has_audio is True
    assert meta.video_codec == "h264"
    assert meta.audio_codec == "aac"


def test_ffmpeg_processor_metadata_silent(sample_video_silent: Path):
    processor = FFmpegVideoProcessor()
    meta = processor.get_metadata(sample_video_silent)
    assert meta.width == 320
    assert meta.height == 240
    assert meta.has_audio is False
    assert meta.audio_codec is None


def test_ffmpeg_processor_corrupted(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"garbage not a valid mp4 header")
    processor = FFmpegVideoProcessor()
    with pytest.raises(CorruptedVideoError):
        processor.get_metadata(corrupt_file)


def test_ffmpeg_processor_empty_file(tmp_path: Path):
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")
    processor = FFmpegVideoProcessor()
    with pytest.raises(CorruptedVideoError):
        processor.get_metadata(empty_file)


def test_ffmpeg_audio_extraction_valid(sample_video_with_audio: Path, tmp_path: Path):
    processor = FFmpegVideoProcessor()
    wav_out = tmp_path / "extracted.wav"
    extracted = processor.extract_audio(sample_video_with_audio, wav_out)
    assert extracted.exists()
    assert extracted.stat().st_size > 0


def test_ffmpeg_audio_extraction_no_audio(sample_video_silent: Path, tmp_path: Path):
    processor = FFmpegVideoProcessor()
    wav_out = tmp_path / "should_fail.wav"
    with pytest.raises(NoAudioTrackError):
        processor.extract_audio(sample_video_silent, wav_out)


def test_upload_valid_video_endpoint(client: TestClient, sample_video_with_audio: Path):
    # 1. Create project
    proj_res = client.post("/api/projects", json={"title": "Test Upload Project"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Upload file
    with open(sample_video_with_audio, "rb") as f:
        upload_res = client.post(
            f"/api/projects/{proj_id}/upload",
            files={"file": ("sample.mp4", f, "video/mp4")},
        )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] in ["uploaded", "audio_extracted"]
    assert data["video"] is not None
    assert data["video"]["filename"] == "sample.mp4"
    assert data["video"]["width"] == 320
    assert data["video"]["height"] == 240
    assert data["video"]["video_codec"] == "h264"
    assert data["video"]["audio_codec"] == "aac"

    # 3. Check video preview endpoint
    video_stream_res = client.get(f"/api/projects/{proj_id}/video")
    assert video_stream_res.status_code == 200
    assert "video/mp4" in video_stream_res.headers["content-type"]

    # 4. Check jobs endpoint
    jobs_res = client.get(f"/api/projects/{proj_id}/jobs")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    assert len(jobs) >= 1
    assert jobs[0]["job_type"] == "extract_audio"


def test_upload_corrupted_file_endpoint(client: TestClient):
    proj_res = client.post("/api/projects", json={"title": "Corrupted Test"})
    proj_id = proj_res.json()["id"]

    corrupt_data = io.BytesIO(b"This is completely invalid video data")
    upload_res = client.post(
        f"/api/projects/{proj_id}/upload",
        files={"file": ("corrupt.mp4", corrupt_data, "video/mp4")},
    )
    assert upload_res.status_code == 400
    assert "corrupted" in upload_res.json()["detail"].lower() or "unable" in upload_res.json()["detail"].lower()


def test_upload_invalid_extension_endpoint(client: TestClient):
    proj_res = client.post("/api/projects", json={"title": "Invalid Extension"})
    proj_id = proj_res.json()["id"]

    data = io.BytesIO(b"Plain text file")
    upload_res = client.post(
        f"/api/projects/{proj_id}/upload",
        files={"file": ("document.txt", data, "text/plain")},
    )
    assert upload_res.status_code == 400
    assert "only mp4" in upload_res.json()["detail"].lower()


def test_upload_nonexistent_project_endpoint(client: TestClient, sample_video_with_audio: Path):
    with open(sample_video_with_audio, "rb") as f:
        res = client.post(
            "/api/projects/non-existent-uuid/upload",
            files={"file": ("sample.mp4", f, "video/mp4")},
        )
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"


def test_upload_max_size_limit(client: TestClient, monkeypatch):
    from app.core.config import settings
    # Temporarily set max size to 1MB to test the 413 limit safely without generating 500MB file
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    proj_res = client.post("/api/projects", json={"title": "Oversized Test"})
    proj_id = proj_res.json()["id"]

    # 1.5 MB of data
    large_data = io.BytesIO(b"0" * (1024 * 1024 + 500 * 1024))
    res = client.post(
        f"/api/projects/{proj_id}/upload",
        files={"file": ("large.mp4", large_data, "video/mp4")},
    )
    assert res.status_code == 413
    assert "maximum allowed size" in res.json()["detail"].lower()
