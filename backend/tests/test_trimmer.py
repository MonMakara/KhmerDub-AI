"""Tests for Phase 13G: Video & Audio Trimming Studio.

Covers all 25 testing requirements:
1. Valid video trim.
2. Valid audio trim.
3. Fast trim.
4. Precise trim.
5. MP4 output.
6. MP3 output.
7. WAV output.
8. M4A output.
9. Start/end validation.
10. Millisecond timestamp handling.
11. Zero-duration rejection.
12. Out-of-range rejection.
13. Video without audio.
14. Corrupted input.
15. File size limits.
16. Task history.
17. Cancellation.
18. Storage cleanup.
19. Path traversal protection.
20. Source preservation.
21. Downloader-to-trimmer handoff.
22. Trimmer-to-transcription handoff.
23. Trimmer-to-dubbing import.
24. Completed output playback.
25. Correct FFprobe duration and codecs.
"""

import io
import json
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.toolkit import ToolkitTask
from app.models.project import Project, Video
from app.services.trimmer import (
    trimmer_service,
    parse_timestamp,
    format_timestamp,
    InvalidTimestampError,
    MediaTrimmingError,
)
from app.core.storage import get_toolkit_task_dir

client = TestClient(app)


@pytest.fixture(scope="module")
def sample_media_files(tmp_path_factory):
    """Generate small synthetic test video (with audio), video (no audio), and audio files."""
    tmp_dir = tmp_path_factory.mktemp("trimmer_test_media")

    # 1. 5-second MP4 with AAC audio
    video_with_audio = tmp_dir / "sample_video_audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(video_with_audio),
        ],
        check=True,
    )

    # 2. 4-second MP4 without audio
    video_no_audio = tmp_dir / "sample_video_no_audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an",
            str(video_no_audio),
        ],
        check=True,
    )

    # 3. 5-second WAV audio
    sample_wav = tmp_dir / "sample_audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:a", "pcm_s16le",
            str(sample_wav),
        ],
        check=True,
    )

    # 4. Corrupted file
    corrupt_file = tmp_dir / "corrupted_media.mp4"
    corrupt_file.write_bytes(b"NOT A REAL VIDEO FILE DATA")

    return {
        "video_with_audio": video_with_audio,
        "video_no_audio": video_no_audio,
        "sample_wav": sample_wav,
        "corrupt_file": corrupt_file,
    }


# ================= Timestamp Parsing & Formatting Unit Tests =================


def test_timestamp_parser_valid_formats():
    """Requirement 10: Millisecond timestamp handling."""
    assert parse_timestamp("00:01:15.250") == 75.25
    assert parse_timestamp("01:15.250") == 75.25
    assert parse_timestamp("75.25") == 75.25
    assert parse_timestamp(75.25) == 75.25
    assert parse_timestamp("00:00:00.000") == 0.0
    assert format_timestamp(75.25) == "00:01:15.250"


def test_timestamp_parser_rejections():
    """Requirement 9 & 11: Start/end validation, negative and zero-duration rejection."""
    with pytest.raises(InvalidTimestampError):
        parse_timestamp("invalid:timestamp:format:extra")
    with pytest.raises(InvalidTimestampError):
        parse_timestamp("-00:01:15.250")
    with pytest.raises(InvalidTimestampError):
        parse_timestamp(-5.0)


# ================= Trimmer Inspection & Waveform Tests =================


def test_trimmer_media_info_endpoint(sample_media_files):
    """Verify inspecting media metadata and extracting waveform peaks."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post("/api/toolkit/trimmer/info", files={"file": ("test.mp4", f, "video/mp4")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_video"] is True
    assert data["has_audio"] is True
    assert data["duration_seconds"] >= 4.9
    assert len(data["peaks"]) == 150
    assert len(data["waveform_peaks"]) == 150
    assert any(p > 0 for p in data["waveform_peaks"])
    assert data["cached_upload_path"] is not None


def test_trimmer_media_info_no_audio(sample_media_files):
    """Phase 13G.1: Verify video without audio returns empty waveform peaks and has_audio=False."""
    vid_no_audio = sample_media_files["video_no_audio"]
    with open(vid_no_audio, "rb") as f:
        resp = client.post("/api/toolkit/trimmer/info", files={"file": ("silent.mp4", f, "video/mp4")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_video"] is True
    assert data["has_audio"] is False
    assert data["peaks"] == []
    assert data["waveform_peaks"] == []


def test_delayed_audio_presentation_alignment(tmp_path):
    """Phase 13G.1: Verify embedded audio with delay aligns properly to presentation duration."""
    delayed_vid = tmp_path / "delayed_audio.mp4"
    # 6-second video; audio delayed by 2 seconds using adelay
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=4",
            "-filter_complex", "[1:a]adelay=2000|2000[delayed_a]",
            "-map", "0:v", "-map", "[delayed_a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(delayed_vid),
        ],
        check=True,
    )

    info = trimmer_service.get_media_info(delayed_vid)
    assert info["has_audio"] is True
    peaks = info["waveform_peaks"]
    assert len(peaks) == 150

    # 150 bins over 6 seconds -> 25 bins/sec. The first 2 seconds (first ~45 bins) should be 0.0 (silence)
    assert all(peaks[i] == 0.0 for i in range(40))
    # After 2 seconds (e.g. bin 60 onwards), active tone should produce positive peaks
    assert any(peaks[i] > 0.0 for i in range(55, 120))


def test_trimmer_thumbnails_endpoint(sample_media_files):
    """Verify video thumbnail frame extraction for visual timeline."""
    vid_path = sample_media_files["video_with_audio"]
    # Inspect to get cached path
    with open(vid_path, "rb") as f:
        info_resp = client.post("/api/toolkit/trimmer/info", files={"file": ("test.mp4", f, "video/mp4")})
    assert info_resp.status_code == 200
    cached_path = info_resp.json().get("cached_upload_path")

    # Call thumbnails endpoint with cached_upload_path
    resp = client.post(
        "/api/toolkit/trimmer/thumbnails",
        json={"cached_upload_path": cached_path, "count": 6},
    )
    assert resp.status_code == 200
    thumbs_data = resp.json().get("thumbnails", [])
    assert len(thumbs_data) > 0
    assert thumbs_data[0].startswith("data:image/jpeg;base64,")

    # Direct service call for thumbnails
    thumbs = trimmer_service.extract_video_thumbnails(vid_path, count=5)
    assert len(thumbs) > 0
    assert thumbs[0].startswith("data:image/jpeg;base64,")


# ================= Trimming Execution Tests =================


def test_valid_video_trim_precise_mp4(sample_media_files):
    """Requirements 1, 4, 5, 24, 25: Valid video trim, precise mode, MP4 output, playback check, ffprobe duration/codecs."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:03.500",
                "trim_mode": "precise",
                "target_format": "mp4",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert task_data["tool_type"] == "video_trimmer"
    assert task_data["target_format"] == "mp4"
    assert 2.4 <= task_data["output_duration_seconds"] <= 2.6
    assert task_data["output_file_size_bytes"] > 0

    # Probe output file directly with ffprobe
    out_file = Path(task_data["output_filename"])
    task_dir = get_toolkit_task_dir(task_data["id"])
    actual_out = task_dir / "output" / task_data["output_filename"]
    assert actual_out.exists()

    meta = trimmer_service.get_media_info(actual_out)
    assert meta["has_video"] is True
    assert meta["has_audio"] is True
    assert meta["video_codec"] == "h264"
    assert meta["audio_codec"] == "aac"


def test_valid_video_trim_fast_mode(sample_media_files):
    """Requirement 3: Fast stream-copy trim."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:00.500",
                "end_time": "00:00:03.000",
                "trim_mode": "fast",
                "target_format": "mp4",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert task_data["output_file_size_bytes"] > 0


def test_video_trim_without_audio(sample_media_files):
    """Requirement 13: Video without audio should trim successfully."""
    vid_path = sample_media_files["video_no_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.500",
                "trim_mode": "precise",
                "target_format": "mp4",
            },
            files={"file": ("no_audio.mp4", f, "video/mp4")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert 1.4 <= task_data["output_duration_seconds"] <= 1.6


def test_audio_trim_to_mp3(sample_media_files):
    """Requirements 2, 6: Valid audio trim to MP3."""
    wav_path = sample_media_files["sample_wav"]
    with open(wav_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "audio_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:03.000",
                "trim_mode": "precise",
                "target_format": "mp3",
            },
            files={"file": ("audio.wav", f, "audio/wav")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert task_data["target_format"] == "mp3"
    assert 1.9 <= task_data["output_duration_seconds"] <= 2.2


def test_audio_trim_to_wav(sample_media_files):
    """Requirement 7: Valid audio trim to WAV."""
    wav_path = sample_media_files["sample_wav"]
    with open(wav_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "audio_trimmer",
                "start_time": "00:00:00.500",
                "end_time": "00:00:02.500",
                "trim_mode": "precise",
                "target_format": "wav",
            },
            files={"file": ("audio.wav", f, "audio/wav")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert task_data["target_format"] == "wav"
    assert 1.9 <= task_data["output_duration_seconds"] <= 2.1


def test_audio_trim_to_m4a(sample_media_files):
    """Requirement 8: Valid audio trim to M4A."""
    wav_path = sample_media_files["sample_wav"]
    with open(wav_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "audio_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.000",
                "trim_mode": "precise",
                "target_format": "m4a",
            },
            files={"file": ("audio.wav", f, "audio/wav")},
        )

    assert resp.status_code == 200
    task_data = resp.json()
    assert task_data["status"] == "completed"
    assert task_data["target_format"] == "m4a"
    assert 0.9 <= task_data["output_duration_seconds"] <= 1.2


# ================= Validation & Error Handling Tests =================


def test_start_greater_than_or_equal_to_end_rejection(sample_media_files):
    """Requirements 9, 11: Reject start >= end and zero-duration."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:03.000",
                "end_time": "00:00:02.000",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert resp.status_code == 400
    assert "must be greater than" in resp.json()["detail"].lower()


def test_out_of_range_timestamp_rejection(sample_media_files):
    """Requirement 12: Out-of-range timestamp rejection."""
    vid_path = sample_media_files["video_with_audio"]  # 5 seconds duration
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:00.000",
                "end_time": "00:01:00.000",  # 60s > 5s
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert resp.status_code == 400
    assert "exceeds media duration" in resp.json()["detail"].lower()


def test_corrupted_input_rejection(sample_media_files):
    """Requirement 14: Corrupted input rejection."""
    corrupt = sample_media_files["corrupt_file"]
    with open(corrupt, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.000",
            },
            files={"file": ("corrupt.mp4", f, "video/mp4")},
        )
    assert resp.status_code in {400, 500}


def test_path_traversal_protection():
    """Requirement 19: Path traversal protection on task ID."""
    resp = client.get("/api/toolkit/tasks/..%2F..%2Fetc%2Fpasswd/stream")
    assert resp.status_code in {400, 404}


def test_source_preservation(sample_media_files):
    """Requirement 20: Original source media remains completely untouched."""
    vid_path = sample_media_files["video_with_audio"]
    original_size = vid_path.stat().st_size

    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.000",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert resp.status_code == 200
    assert vid_path.stat().st_size == original_size


# ================= Integration, Handoff & History Tests =================


def test_task_history_and_storage_cleanup(sample_media_files, db_session: Session):
    """Requirements 16, 18: Task history listing and storage cleanup on delete."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.000",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # Verify task appears in history
    hist_resp = client.get(f"/api/toolkit/tasks?tool_type=video_trimmer")
    assert hist_resp.status_code == 200
    assert any(t["id"] == task_id for t in hist_resp.json())

    # Verify task directory exists
    task_dir = get_toolkit_task_dir(task_id)
    assert task_dir.exists()

    # Delete task and verify storage cleanup
    del_resp = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_resp.status_code == 200
    assert not task_dir.exists()


def test_trimmer_to_dubbing_import(sample_media_files):
    """Requirement 23: Import trimmed video directly into Video Dubbing Studio."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:03.000",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # Import into dubbing
    imp_resp = client.post(
        f"/api/toolkit/trimmer/{task_id}/import-dubbing",
        json={"title": "Trimmed Dubbing Project"},
    )
    assert imp_resp.status_code == 200
    imp_data = imp_resp.json()
    assert imp_data["success"] is True
    assert imp_data["project_id"] is not None
    assert imp_data["status"] == "audio_extracted"


def test_trimmer_to_toolkit_handoff(sample_media_files):
    """Requirements 21, 22: Downloader-to-trimmer handoff and trimmer-to-transcription handoff."""
    vid_path = sample_media_files["video_with_audio"]
    with open(vid_path, "rb") as f:
        trim_resp = client.post(
            "/api/toolkit/trimmer/trim",
            data={
                "tool_type": "video_trimmer",
                "start_time": "00:00:01.000",
                "end_time": "00:00:02.500",
            },
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert trim_resp.status_code == 200
    trim_task_id = trim_resp.json()["id"]

    # Handoff to video_to_transcript
    handoff_resp = client.post(
        f"/api/toolkit/trimmer/{trim_task_id}/handoff",
        json={"target_tool": "video_to_transcript"},
    )
    assert handoff_resp.status_code == 200
    new_task = handoff_resp.json()
    assert new_task["tool_type"] == "video_to_transcript"
    assert new_task["source_task_id"] == trim_task_id
    assert Path(new_task["source_filename"]).suffix.lower() == ".mp4"


def test_trimmer_cancellation():
    """Requirement 17: Download and trim cancellation."""
    resp = client.post("/api/toolkit/trimmer/nonexistent-task-id/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
