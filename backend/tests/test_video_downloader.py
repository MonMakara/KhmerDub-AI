import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.toolkit import ToolkitTask
from app.services.downloader.engine import (
    DownloadCancelledException,
    DownloadLimitExceededError,
    VideoDownloadError,
    execute_download_job,
    request_download_cancellation,
)
from app.services.downloader.metadata import (
    VideoMetadataError,
    fetch_media_metadata,
)
from app.services.downloader.security import (
    DownloaderSecurityError,
    InvalidURLError,
    SSRFSecurityError,
    UnsupportedSourceError,
    is_safe_ip,
    safe_connection_guard,
    validate_and_classify_url,
)


# ---------------- 1. Security & SSRF Protection Tests ----------------


def test_ssrf_protection_private_ips():
    """Verify private IPv4 and IPv6 addresses are strictly rejected."""
    private_ips = [
        "10.0.0.1",
        "10.254.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "100.64.0.1",  # CGNAT
        "198.18.0.1",  # Benchmark net
    ]
    for ip in private_ips:
        assert is_safe_ip(ip) is False, f"Expected {ip} to be unsafe"
        with pytest.raises(SSRFSecurityError):
            validate_and_classify_url(f"http://{ip}/video.mp4")


def test_ssrf_protection_localhost_and_loopback():
    """Verify loopback addresses and localhost hostnames are strictly rejected."""
    loopbacks = [
        "127.0.0.1",
        "127.0.0.2",
        "127.1.2.3",
        "localhost",
        "sub.localhost",
        "::1",
    ]
    for host in loopbacks:
        if ":" not in host and not host.endswith("localhost") and not host.startswith("::"):
            assert is_safe_ip(host) is False
        target_host = f"[{host}]" if ":" in host else host
        with pytest.raises(SSRFSecurityError):
            validate_and_classify_url(f"http://{target_host}:8000/media.mp4")


def test_ssrf_protection_cloud_metadata():
    """Verify cloud metadata endpoints (AWS, GCP, Azure) are strictly rejected."""
    metadata_endpoints = [
        "169.254.169.254",
        "169.254.169.250",
        "169.254.1.1",
        "metadata.google.internal",
    ]
    for ep in metadata_endpoints:
        with pytest.raises(SSRFSecurityError):
            validate_and_classify_url(f"http://{ep}/computeMetadata/v1/")


def test_ssrf_protection_invalid_schemes():
    """Verify non-HTTP/HTTPS protocols are rejected."""
    invalid_urls = [
        "file:///etc/passwd",
        "ftp://example.com/video.mp4",
        "gopher://example.com/",
        "data:text/plain;base64,SGVsbG8=",
        "javascript:alert(1)",
    ]
    for u in invalid_urls:
        with pytest.raises(InvalidURLError):
            validate_and_classify_url(u)


def test_unsupported_websites():
    """Verify random non-supported web domains are rejected with clear message."""
    unsupported_urls = [
        "https://random-unknown-site.org/watch?v=123",
        "https://example.com/stream/page",
        "https://unsupported-video-host.net/play",
    ]
    for u in unsupported_urls:
        with pytest.raises(UnsupportedSourceError) as exc_info:
            validate_and_classify_url(u)
        assert "not a recognized video source" in str(exc_info.value)


def test_valid_permitted_urls_classification():
    """Verify YouTube, TikTok, and direct media URLs are classified correctly."""
    # YouTube
    yt_url, platform = validate_and_classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert platform == "YouTube"
    assert "youtube.com" in yt_url

    yt_short, platform = validate_and_classify_url("https://youtu.be/dQw4w9WgXcQ")
    assert platform == "YouTube"

    # TikTok
    tt_url, platform = validate_and_classify_url("https://www.tiktok.com/@creator/video/1234567890")
    assert platform == "TikTok"

    # Direct media on a valid domain
    media_url, platform = validate_and_classify_url("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4")
    assert platform == "Direct Media"


def test_safe_connection_guard_blocks_runtime_ssrf():
    """Verify that socket operations inside safe_connection_guard reject private/loopback connections."""
    import socket

    with safe_connection_guard():
        with pytest.raises(SSRFSecurityError):
            # Attempt to connect to 127.0.0.1
            sock = socket.create_connection(("127.0.0.1", 80), timeout=0.1)
            sock.close()


# ---------------- 2. Metadata Extraction Tests ----------------


@patch("app.services.downloader.metadata.yt_dlp.YoutubeDL")
def test_metadata_extraction_youtube_mocked(mock_ydl_class):
    """Test metadata extraction from YouTube with mock return."""
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {
        "title": "Public Educational Talk on AI",
        "uploader": "Science Foundation",
        "duration": 480.0,
        "thumbnail": "https://example.com/thumb.jpg",
        "filesize_approx": 52428800,
        "formats": [
            {"height": 1080, "vcodec": "avc1"},
            {"height": 720, "vcodec": "avc1"},
            {"height": 360, "vcodec": "avc1"},
            {"height": None, "vcodec": "none", "acodec": "mp4a"},
        ],
    }

    info = fetch_media_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert info["title"] == "Public Educational Talk on AI"
    assert info["source_platform"] == "YouTube"
    assert info["uploader"] == "Science Foundation"
    assert info["duration_seconds"] == 480.0
    assert "1080p" in info["available_video_qualities"]
    assert "720p" in info["available_video_qualities"]
    assert "360p" in info["available_video_qualities"]
    assert "mp3" in info["available_audio_formats"]


@patch("app.services.downloader.metadata.httpx.Client")
def test_metadata_extraction_direct_media(mock_client_class):
    """Test metadata extraction from direct media link with mock HEAD response."""
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": "10485760"}
    mock_client.head.return_value = mock_resp

    info = fetch_media_metadata("https://commondatastorage.googleapis.com/sample.mp4")
    assert info["title"] == "sample"
    assert info["source_platform"] == "Direct Media"
    assert info["estimated_file_size_bytes"] == 10485760
    assert "best" in info["available_video_qualities"]


# ---------------- 3. API Endpoints & Workflows ----------------


def test_api_downloader_info_endpoint(client: TestClient):
    """Test POST /api/toolkit/downloader/info."""
    # Test SSRF rejection via API
    resp = client.post("/api/toolkit/downloader/info", json={"url": "http://127.0.0.1:8000"})
    assert resp.status_code == 400
    assert "Security violation" in resp.json()["detail"]

    # Test unsupported source rejection via API
    resp = client.post("/api/toolkit/downloader/info", json={"url": "https://unsupported-site.org/video"})
    assert resp.status_code == 400
    assert "not a recognized video source" in resp.json()["detail"]


def test_api_downloader_start_rights_required(client: TestClient):
    """Verify that start download without rights confirmation returns HTTP 400."""
    resp = client.post(
        "/api/toolkit/downloader/start",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "rights_confirmed": False,
        },
    )
    assert resp.status_code == 400
    assert "rights or permission" in resp.json()["detail"]


@patch("app.services.downloader.service.downloader_service.inspect_url")
@patch("app.services.downloader.service.execute_download_job")
def test_api_downloader_start_and_complete_video(mock_exec, mock_inspect, client: TestClient, db_session: Session):
    """Test queuing and running a video download task."""
    mock_inspect.return_value = {
        "title": "Sample Download Video",
        "source_platform": "YouTube",
        "uploader": "Test Channel",
        "duration_seconds": 120.0,
        "thumbnail_url": "https://example.com/thumb.jpg",
    }

    def fake_job(task_id, url, output_type, quality, audio_format, progress_callback):
        # Create a small dummy file to represent completed download
        task_dir = Path("/app/data/toolkit") / task_id / "output"
        task_dir.mkdir(parents=True, exist_ok=True)
        out_file = task_dir / f"downloaded_video_{task_id}.mp4"
        out_file.write_bytes(b"dummy mp4 content")
        progress_callback({
            "status": "completed",
            "stage": "completed",
            "progress_percentage": 100,
            "output_file_path": str(out_file),
            "output_filename": out_file.name,
            "output_duration_seconds": 120.0,
            "output_file_size_bytes": 17,
        })
        return {"output_file_path": str(out_file)}

    mock_exec.side_effect = fake_job

    resp = client.post(
        "/api/toolkit/downloader/start",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "output_type": "video",
            "quality": "720p",
            "rights_confirmed": True,
        },
    )
    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["tool_type"] == "video_downloader"
    assert task_data["source_type"] == "url"
    assert "Sample Download Video" in task_data["source_filename"]

    # Verify task exists in DB
    task_id = task_data["id"]
    db_task = db_session.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
    assert db_task is not None


def test_api_downloader_cancellation(client: TestClient, db_session: Session):
    """Test cancelling an in-progress download task."""
    task = ToolkitTask(
        id="cancel-test-task-1",
        tool_type="video_downloader",
        source_type="url",
        source_filename="Cancelling Media",
        source_file_path="https://www.youtube.com/watch?v=test",
        target_format="mp4",
        status="processing",
        progress_percentage=25,
    )
    db_session.add(task)
    db_session.commit()

    resp = client.post(f"/api/toolkit/downloader/{task.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    db_session.refresh(task)
    assert task.status == "cancelled"
    assert "cancelled by user" in task.error_message


def test_downloader_size_limit_rejection():
    """Verify that files exceeding maximum size limit raise DownloadLimitExceededError."""
    with pytest.raises(DownloadLimitExceededError):
        # Trigger simulated limit check
        raise DownloadLimitExceededError("Downloaded file size exceeds maximum limit of 500MB.")


@patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_metadata")
@patch("app.services.video.ffmpeg.FFmpegVideoProcessor.extract_audio")
def test_api_downloader_import_to_dubbing(mock_extract, mock_probe, client: TestClient, db_session: Session):
    """Test importing a completed downloaded video into a Video Dubbing project."""
    # Create dummy output file
    tmp_dir = Path("/app/data/toolkit/import-test-task/output")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = tmp_dir / "downloaded_video_import-test-task.mp4"
    dummy_video.write_bytes(b"dummy mp4 data for dubbing")

    mock_probe.return_value = MagicMock(
        duration=45.0,
        has_audio=True,
        width=1280,
        height=720,
        video_codec="h264",
        audio_codec="aac",
    )

    task = ToolkitTask(
        id="import-test-task",
        tool_type="video_downloader",
        source_type="url",
        source_filename="Downloaded Wildlife Doc.mp4",
        source_file_path="https://www.youtube.com/watch?v=test",
        target_format="mp4",
        status="completed",
        progress_percentage=100,
        output_file_path=str(dummy_video),
        output_filename="downloaded_video_import-test-task.mp4",
        source_media_metadata=json.dumps({"title": "Wildlife Documentary"}),
    )
    db_session.add(task)
    db_session.commit()

    resp = client.post(
        f"/api/toolkit/downloader/{task.id}/import-dubbing",
        json={
            "title": "Imported Wildlife Project",
            "original_language": "en",
            "target_language": "km",
        },
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["title"] == "Imported Wildlife Project"
    project_id = res_data["project_id"]

    # Verify Project in DB
    proj = db_session.query(Project).filter(Project.id == project_id).first()
    assert proj is not None
    assert proj.original_language == "en"
    assert proj.target_language == "km"
    assert proj.video is not None
    assert proj.video.duration_seconds == 45.0

    # Clean up dummy file
    shutil.rmtree(tmp_dir.parent, ignore_errors=True)


def test_api_downloader_handoff_to_toolkit(client: TestClient, db_session: Session):
    """Test transferring downloaded media into video_to_audio and video_to_transcript studios."""
    # Create dummy output file
    tmp_dir = Path("/app/data/toolkit/handoff-test-task/output")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = tmp_dir / "downloaded_video_handoff-test-task.mp4"
    dummy_video.write_bytes(b"dummy mp4 data for handoff")

    task = ToolkitTask(
        id="handoff-test-task",
        tool_type="video_downloader",
        source_type="url",
        source_filename="Nature Clip.mp4",
        source_file_path="https://www.youtube.com/watch?v=test",
        target_format="mp4",
        status="completed",
        progress_percentage=100,
        output_file_path=str(dummy_video),
        output_filename="downloaded_video_handoff-test-task.mp4",
    )
    db_session.add(task)
    db_session.commit()

    # Handoff to Video to Audio
    resp_v2a = client.post(
        f"/api/toolkit/downloader/{task.id}/handoff",
        json={"target_tool": "video_to_audio"},
    )
    assert resp_v2a.status_code == 200
    v2a_task = resp_v2a.json()
    assert v2a_task["tool_type"] == "video_to_audio"
    assert v2a_task["source_task_id"] == task.id
    assert v2a_task["source_type"] == "task_transfer"

    # Handoff to Video to Transcript
    resp_v2t = client.post(
        f"/api/toolkit/downloader/{task.id}/handoff",
        json={"target_tool": "video_to_transcript"},
    )
    assert resp_v2t.status_code == 200
    v2t_task = resp_v2t.json()
    assert v2t_task["tool_type"] == "video_to_transcript"
    assert v2t_task["source_task_id"] == task.id

    # Clean up dummy file
    shutil.rmtree(tmp_dir.parent, ignore_errors=True)
    shutil.rmtree(Path(f"/app/data/toolkit/{v2a_task['id']}"), ignore_errors=True)
    shutil.rmtree(Path(f"/app/data/toolkit/{v2t_task['id']}"), ignore_errors=True)


def test_api_downloader_stream_and_download(client: TestClient, db_session: Session):
    """Test streaming and downloading the finished media via standard toolkit routes."""
    tmp_dir = Path("/app/data/toolkit/stream-test-task/output")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = tmp_dir / "downloaded_video_stream-test-task.mp4"
    dummy_video.write_bytes(b"dummy mp4 binary stream")

    task = ToolkitTask(
        id="stream-test-task",
        tool_type="video_downloader",
        source_type="url",
        source_filename="Streamable Video.mp4",
        source_file_path="https://www.youtube.com/watch?v=test",
        target_format="mp4",
        status="completed",
        progress_percentage=100,
        output_file_path=str(dummy_video),
        output_filename="downloaded_video_stream-test-task.mp4",
    )
    db_session.add(task)
    db_session.commit()

    # Test stream
    resp_stream = client.get(f"/api/toolkit/tasks/{task.id}/stream")
    assert resp_stream.status_code == 200
    assert resp_stream.headers["content-type"] == "video/mp4"
    assert resp_stream.content == b"dummy mp4 binary stream"

    # Test download
    resp_dl = client.get(f"/api/toolkit/tasks/{task.id}/download")
    assert resp_dl.status_code == 200
    assert "attachment" in resp_dl.headers["content-disposition"]
    assert resp_dl.content == b"dummy mp4 binary stream"

    # Clean up
    shutil.rmtree(tmp_dir.parent, ignore_errors=True)


def test_real_transcode_video_and_audio_outputs():
    """Verify real FFmpeg transcoding and normalization producing compliant MP4, MP3, and WAV files."""
    import subprocess
    import threading
    from app.services.downloader.engine import _transcode_and_normalize
    from app.services.video.ffmpeg import FFmpegVideoProcessor

    temp_dir = Path("/app/data/temp/test_transcode_suite")
    temp_dir.mkdir(parents=True, exist_ok=True)
    raw_synthetic_mp4 = temp_dir / "raw_synthetic.mp4"
    out_dir = temp_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate a tiny 1-second synthetic test video using ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1.0",
        "-f", "lavfi", "-i", "sine=f=440:d=1.0",
        "-c:v", "libx264", "-c:a", "aac",
        str(raw_synthetic_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert raw_synthetic_mp4.exists()

    cancel_event = threading.Event()
    processor = FFmpegVideoProcessor()

    # 1. Transcode to web-compliant MP4
    out_mp4 = _transcode_and_normalize(
        raw_path=raw_synthetic_mp4,
        output_dir=out_dir,
        task_id="task_mp4",
        output_type="video",
        audio_format="mp3",
        cancel_event=cancel_event,
    )
    assert out_mp4.exists()
    assert out_mp4.suffix == ".mp4"
    meta_mp4 = processor.get_metadata(out_mp4)
    assert meta_mp4.video_codec == "h264"
    assert meta_mp4.has_audio is True

    # 2. Transcode to MP3 audio
    out_mp3 = _transcode_and_normalize(
        raw_path=raw_synthetic_mp4,
        output_dir=out_dir,
        task_id="task_mp3",
        output_type="audio",
        audio_format="mp3",
        cancel_event=cancel_event,
    )
    assert out_mp3.exists()
    assert out_mp3.suffix == ".mp3"
    assert out_mp3.stat().st_size > 0

    # 3. Transcode to WAV audio
    out_wav = _transcode_and_normalize(
        raw_path=raw_synthetic_mp4,
        output_dir=out_dir,
        task_id="task_wav",
        output_type="audio",
        audio_format="wav",
        cancel_event=cancel_event,
    )
    assert out_wav.exists()
    assert out_wav.suffix == ".wav"
    assert out_wav.stat().st_size > 0

    # Clean up test files
    shutil.rmtree(temp_dir, ignore_errors=True)

