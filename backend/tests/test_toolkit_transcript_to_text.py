"""Unit and integration tests for Phase 13E.5 Transcript to Text Tool."""

import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.toolkit import ToolkitTask, ToolkitTranscriptSegment
from app.services.subtitles.text_extractor import (
    TranscriptTextExtractor,
    format_seconds_to_timecode,
    calculate_word_count,
    detect_language,
)


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
[SPEAKER_01]: Welcome to KhmerDub AI.

2
00:00:03,200 --> 00:00:05,000
This is a powerful platform for audio and video dubbing.

3
00:00:08,000 --> 00:00:10,000
[SPEAKER_02]: After a significant pause, we start a new paragraph.

4
00:00:10,500 --> 00:00:13,000
It supports multiple AI models and voices.
"""

SAMPLE_KHMER_SRT = """1
00:00:01,000 --> 00:00:03,000
សូមស្វាគមន៍មកកាន់ KhmerDub AI។

2
00:00:03,200 --> 00:00:05,500
នេះគឺជាប្រព័ន្ធបកប្រែវីដេអូដោយស្វ័យប្រវត្តិ។

3
00:00:08,000 --> 00:00:11,000
ការបកប្រែមានភាពត្រឹមត្រូវខ្ពស់ និងរហ័ស។
"""


def test_extractor_modes():
    """Verify smart_paragraphs, continuous, line_by_line, and timestamped modes."""
    extractor = TranscriptTextExtractor(default_pause_threshold=1.5)

    # 1. Smart paragraphs
    res_smart = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="smart_paragraphs",
        speaker_handling="strip",
        pause_threshold_seconds=1.5,
    )
    assert len(res_smart.paragraphs) == 2
    assert "Welcome to KhmerDub AI." in res_smart.paragraphs[0].text
    assert "After a significant pause" in res_smart.paragraphs[1].text
    assert "[SPEAKER" not in res_smart.full_text

    # 2. Continuous
    res_cont = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="continuous",
        speaker_handling="strip",
    )
    assert len(res_cont.paragraphs) == 1
    assert "Welcome to KhmerDub AI. This is a powerful platform" in res_cont.full_text
    assert res_cont.paragraphs[0].cue_count == 4

    # 3. Line by line
    res_line = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="line_by_line",
        speaker_handling="strip",
    )
    assert len(res_line.paragraphs) == 4

    # 4. Timestamped
    res_ts = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="timestamped",
        speaker_handling="strip",
    )
    assert len(res_ts.paragraphs) == 4
    assert res_ts.paragraphs[0].text.startswith("[00:01]")


def test_extractor_speaker_handling():
    """Verify keep vs strip speaker labels."""
    extractor = TranscriptTextExtractor()

    # Keep speakers
    res_keep = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="smart_paragraphs",
        speaker_handling="keep",
    )
    assert any("SPEAKER_01:" in p.text for p in res_keep.paragraphs)
    assert any("SPEAKER_02:" in p.text for p in res_keep.paragraphs)

    # Strip speakers
    res_strip = extractor.extract_from_content(
        SAMPLE_SRT,
        paragraph_mode="smart_paragraphs",
        speaker_handling="strip",
    )
    assert not any("SPEAKER" in p.text for p in res_strip.paragraphs)


def test_extractor_khmer_and_formatting():
    """Verify Khmer language detection and word counting."""
    extractor = TranscriptTextExtractor()
    res = extractor.extract_from_content(
        SAMPLE_KHMER_SRT,
        paragraph_mode="smart_paragraphs",
    )
    assert res.detected_language == "km"
    assert res.stats["word_count"] > 0
    assert "សូមស្វាគមន៍មកកាន់ KhmerDub AI" in res.full_text


def test_api_convert_transcript_to_text(client: TestClient):
    """Test POST /api/toolkit/transcript-to-text with raw content."""
    resp = client.post(
        "/api/toolkit/transcript-to-text",
        json={
            "content": SAMPLE_SRT,
            "filename": "meeting.srt",
            "paragraph_mode": "smart_paragraphs",
            "speaker_handling": "strip",
            "target_format": "txt",
            "title": "Board Meeting",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tool_type"] == "transcript_to_text"
    assert data["status"] == "completed"
    assert data["progress_percentage"] == 100
    assert data["output_filename"] == "meeting.txt"

    meta = data["output_media_metadata"]
    assert meta["word_count"] > 0
    assert meta["paragraph_count"] == 2
    assert meta["cue_count"] == 4
    assert "files" in meta
    assert meta["files"]["txt"] == "meeting.txt"
    assert meta["files"]["md"] == "meeting.md"
    assert meta["files"]["json"] == "meeting.json"

    # Verify segments serialized
    assert len(data["segments"]) == 2
    assert "Welcome to KhmerDub AI." in data["full_text"]


def test_api_upload_file_transcript_to_text(client: TestClient):
    """Test POST /api/toolkit/transcript-to-text/file with uploaded file."""
    srt_bytes = SAMPLE_SRT.encode("utf-8")
    files = {
        "file": ("podcast.srt", io.BytesIO(srt_bytes), "application/x-subrip"),
    }
    data = {
        "paragraph_mode": "continuous",
        "speaker_handling": "keep",
        "target_format": "md",
        "title": "Tech Podcast Episode 1",
    }
    resp = client.post("/api/toolkit/transcript-to-text/file", files=files, data=data)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["tool_type"] == "transcript_to_text"
    assert res["target_format"] == "md"
    assert res["output_filename"] == "podcast.md"
    assert res["output_media_metadata"]["paragraph_mode"] == "continuous"
    assert "SPEAKER_01:" in res["full_text"]


def test_api_source_task_transfer(client: TestClient, db_session: Session):
    """Test converting from a previous transcription task via source_task_id."""
    src_task_id = str(uuid.uuid4())
    src_task = ToolkitTask(
        id=src_task_id,
        tool_type="audio_to_transcript",
        source_type="file_upload",
        source_filename="speech.mp3",
        source_file_path="/fake/speech.mp3",
        target_format="txt",
        status="completed",
        progress_percentage=100,
    )
    db_session.add(src_task)

    seg1 = ToolkitTranscriptSegment(
        id=str(uuid.uuid4()),
        task_id=src_task_id,
        segment_order=1,
        start_time=0.0,
        end_time=2.5,
        raw_text="Good morning everyone.",
    )
    seg2 = ToolkitTranscriptSegment(
        id=str(uuid.uuid4()),
        task_id=src_task_id,
        segment_order=2,
        start_time=2.8,
        end_time=5.0,
        raw_text="Today we announce our new AI media tools.",
    )
    db_session.add_all([seg1, seg2])
    db_session.commit()

    resp = client.post(
        "/api/toolkit/transcript-to-text",
        json={
            "source_task_id": src_task_id,
            "paragraph_mode": "smart_paragraphs",
            "target_format": "json",
            "title": "Keynote Announcement",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source_task_id"] == src_task_id
    assert data["output_filename"] == "speech.json"
    assert data["output_media_metadata"]["paragraph_count"] == 1
    assert "Good morning everyone. Today we announce our new AI media tools." in data["full_text"]


def test_export_and_bundle_for_transcript_to_text(client: TestClient):
    """Test exporting individual formats and downloading consolidated bundle ZIP."""
    create_resp = client.post(
        "/api/toolkit/transcript-to-text",
        json={
            "content": SAMPLE_SRT,
            "filename": "interview.srt",
            "paragraph_mode": "smart_paragraphs",
            "target_format": "txt",
            "title": "Interview",
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    # Test export as txt
    export_txt = client.get(f"/api/toolkit/tasks/{task_id}/export/txt")
    assert export_txt.status_code == 200
    assert "Welcome to KhmerDub AI." in export_txt.text

    # Test export as md
    export_md = client.get(f"/api/toolkit/tasks/{task_id}/export/md")
    assert export_md.status_code == 200
    assert "# Interview" in export_md.text

    # Test export as json
    export_json = client.get(f"/api/toolkit/tasks/{task_id}/export/json")
    assert export_json.status_code == 200
    json_data = export_json.json()
    assert "paragraphs" in json_data
    assert len(json_data["paragraphs"]) == 2

    # Test bundle download
    bundle_resp = client.get(f"/api/toolkit/tasks/{task_id}/bundle")
    assert bundle_resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle_resp.content)) as zf:
        namelist = zf.namelist()
        assert "README.txt" in namelist
        assert any(n.startswith("text/") for n in namelist)
