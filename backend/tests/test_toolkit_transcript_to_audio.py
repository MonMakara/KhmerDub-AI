"""
KhmerDub AI — Phase 13E.4: Transcript-to-Audio Studio Integration Tests
Tests SRT/VTT/plain text parsing, completed task transcript import,
speech generation in Narration Mode and Timed Mode, timing conflict detection,
segment inline editing & regeneration, per-segment voice override, and cascade deletion.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.storage import (
    get_toolkit_task_dir,
    get_toolkit_task_output_dir,
)
from app.database.session import SessionLocal
from app.main import app
from app.models.toolkit import ToolkitTask, ToolkitTranscriptSegment, ToolkitTTSSegment
from app.services.subtitles.parser import parse_transcript_content, TranscriptParseError
from app.services.tts.base import TTSAudioResult

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_parse_transcript_srt_and_vtt():
    """Verify SRT and WebVTT parsing preserves timestamps, Khmer Unicode, and segment order."""
    srt_sample = """1
00:00:01,000 --> 00:00:04,500
សួស្តីបងប្អូនទាំងអស់គ្នា។

2
00:00:05,200 --> 00:00:08,700
សូមស្វាគមន៍មកកាន់ KhmerDub AI។
"""
    parsed_srt = parse_transcript_content(srt_sample, filename="sample.srt")
    assert parsed_srt.format == "srt"
    assert parsed_srt.has_timestamps is True
    assert len(parsed_srt.segments) == 2
    assert parsed_srt.segments[0].segment_order == 1
    assert parsed_srt.segments[0].start_time == 1.0
    assert parsed_srt.segments[0].end_time == 4.5
    assert parsed_srt.segments[0].text == "សួស្តីបងប្អូនទាំងអស់គ្នា។"
    assert parsed_srt.segments[1].start_time == 5.2
    assert parsed_srt.segments[1].end_time == 8.7

    # WebVTT with cues and tags
    vtt_sample = """WEBVTT - Title

00:01.000 --> 00:03.500
<b>Welcome</b> to KhmerDub AI.

00:04.000 --> 00:06.000
Natural Khmer narration.
"""
    parsed_vtt = parse_transcript_content(vtt_sample, filename="sample.vtt")
    assert parsed_vtt.format == "vtt"
    assert parsed_vtt.has_timestamps is True
    assert len(parsed_vtt.segments) == 2
    assert parsed_vtt.segments[0].text == "Welcome to KhmerDub AI."
    assert parsed_vtt.segments[0].start_time == 1.0
    assert parsed_vtt.segments[0].end_time == 3.5


def test_parse_transcript_plain_text():
    """Verify plain text without timestamps defaults to Narration Mode."""
    plain_sample = """សួស្តីបងប្អូនទាំងអស់គ្នា។
សូមស្វាគមន៍មកកាន់ KhmerDub AI។
ការបម្លែងអត្ថបទទៅជាសំឡេងនិយាយធម្មជាតិ។"""
    parsed = parse_transcript_content(plain_sample, filename="notes.txt")
    assert parsed.format == "text"
    assert parsed.has_timestamps is False
    assert len(parsed.segments) == 3
    assert parsed.segments[0].start_time is None
    assert parsed.segments[0].end_time is None
    assert "Narration Mode" in parsed.warnings[0]


def test_parse_transcript_endpoint():
    """Verify POST /api/toolkit/transcript-to-audio/parse endpoint."""
    resp = client.post(
        "/api/toolkit/transcript-to-audio/parse",
        json={
            "content": "1\n00:00:01,000 --> 00:00:03,500\nជំរាបសួរ។",
            "filename": "hello.srt",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "srt"
    assert data["has_timestamps"] is True
    assert len(data["segments"]) == 1
    assert data["segments"][0]["text"] == "ជំរាបសួរ។"

    # Malformed empty content
    resp_empty = client.post(
        "/api/toolkit/transcript-to-audio/parse",
        json={"content": "   ", "filename": "empty.srt"},
    )
    assert resp_empty.status_code == 400


def test_import_transcript_from_completed_task(db_session: Session):
    """Verify importing transcript segments from an existing Phase 13E.2 task without Whisper re-run."""
    source_task_id = str(uuid.uuid4())
    task = ToolkitTask(
        id=source_task_id,
        tool_type="video_to_transcript",
        source_type="upload",
        source_filename="speech_sample.mp4",
        source_file_path="/tmp/fake_speech.mp4",
        target_format="srt",
        status="completed",
        progress_percentage=100,
        output_duration_seconds=12.5,
    )
    db_session.add(task)

    seg1 = ToolkitTranscriptSegment(
        id=str(uuid.uuid4()),
        task_id=source_task_id,
        segment_order=1,
        start_time=0.5,
        end_time=3.2,
        raw_text="សួស្តីបងប្អូន។",
        edited_text="សួស្តីបងប្អូនទាំងអស់គ្នា។",
    )
    seg2 = ToolkitTranscriptSegment(
        id=str(uuid.uuid4()),
        task_id=source_task_id,
        segment_order=2,
        start_time=4.0,
        end_time=7.5,
        raw_text="សូមស្វាគមន៍មកកាន់ប្រព័ន្ធ។",
    )
    db_session.add(seg1)
    db_session.add(seg2)
    db_session.commit()

    resp = client.post(f"/api/toolkit/transcript-to-audio/import/{source_task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "imported"
    assert data["source_task_id"] == source_task_id
    assert len(data["segments"]) == 2
    # seg1 edited text is prioritized over raw text
    assert data["segments"][0]["text"] == "សួស្តីបងប្អូនទាំងអស់គ្នា។"
    assert data["segments"][0]["start_time"] == 0.5
    assert data["segments"][1]["text"] == "សូមស្វាគមន៍មកកាន់ប្រព័ន្ធ។"
    assert data["segments"][1]["end_time"] == 7.5

    # Cleanup
    db_session.delete(task)
    db_session.commit()


def _mock_dummy_synthesize(text, output_path, language="km", voice="default"):
    """Helper to generate a valid minimal silent PCM WAV for TTS test mocks."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1.2",
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return TTSAudioResult(
        audio_path=Path(output_path),
        duration_seconds=1.2,
        provider_name="gtts",
        voice=voice,
        language=language,
    )


def test_generate_transcript_to_audio_narration_mode(db_session: Session):
    """Verify converting transcript into natural continuous speech narration."""
    created_task_id = None
    with patch("app.services.tts.google.GoogleTTSProvider.synthesize", side_effect=_mock_dummy_synthesize):
        req_payload = {
            "segments": [
                {
                    "segment_order": 1,
                    "text": "សួស្តីបងប្អូនទាំងអស់គ្នា។",
                    "start_time": 1.0,
                    "end_time": 3.5,
                },
                {
                    "segment_order": 2,
                    "text": "សូមស្វាគមន៍មកកាន់ KhmerDub AI។",
                    "start_time": 4.0,
                    "end_time": 7.0,
                },
            ],
            "mode": "narration",
            "provider": "gtts",
            "voice": "default",
            "language": "km",
            "target_format": "mp3",
            "pause_duration_seconds": 0.3,
            "filename": "my_narration.srt",
        }
        resp = client.post("/api/toolkit/transcript-to-audio/generate", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        created_task_id = data["id"]

        assert data["tool_type"] == "transcript_to_audio"
        assert data["status"] == "completed"
        assert data["progress_percentage"] == 100
        assert data["output_duration_seconds"] > 2.0
        assert data["output_filename"].endswith(".mp3")
        assert len(data["tts_segments"]) == 2
        assert data["tts_segments"][0]["status"] == "completed"
        assert data["output_media_metadata"]["mode"] == "narration"

    # Export test
    resp_exp = client.get(f"/api/toolkit/tts/tasks/{created_task_id}/export?format=wav")
    assert resp_exp.status_code == 200
    assert resp_exp.headers["content-type"] == "audio/wav"

    # Cleanup
    if created_task_id:
        del_resp = client.delete(f"/api/toolkit/tasks/{created_task_id}")
        assert del_resp.status_code == 200


def test_generate_transcript_to_audio_timed_mode(db_session: Session):
    """Verify converting transcript into aligned timed speech matching timestamps."""
    created_task_id = None
    with patch("app.services.tts.google.GoogleTTSProvider.synthesize", side_effect=_mock_dummy_synthesize):
        req_payload = {
            "segments": [
                {
                    "segment_order": 1,
                    "text": "ជំរាបសួរ។",
                    "start_time": 1.0,
                    "end_time": 3.0,
                },
                {
                    "segment_order": 2,
                    "text": "អរគុណច្រើន។",
                    "start_time": 5.0,
                    "end_time": 7.0,
                },
            ],
            "mode": "timed",
            "provider": "gtts",
            "voice": "default",
            "language": "km",
            "target_format": "wav",
            "filename": "timed_subtitles.srt",
        }
        resp = client.post("/api/toolkit/transcript-to-audio/generate", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        created_task_id = data["id"]

        assert data["tool_type"] == "transcript_to_audio"
        assert data["status"] == "completed"
        assert data["output_media_metadata"]["mode"] == "timed"
        # Since end_time of last cue is 7.0s, total duration must cover timeline
        assert data["output_duration_seconds"] >= 6.0

    # Cleanup
    if created_task_id:
        client.delete(f"/api/toolkit/tasks/{created_task_id}")


def test_generate_timed_mode_rejects_missing_timestamps():
    """Verify Timed Mode fails with clear 400 error when timestamps are missing."""
    req_payload = {
        "segments": [
            {
                "segment_order": 1,
                "text": "គ្មានពេលវេលា។",
                "start_time": None,
                "end_time": None,
            }
        ],
        "mode": "timed",
        "provider": "gtts",
        "voice": "default",
    }
    resp = client.post("/api/toolkit/transcript-to-audio/generate", json=req_payload)
    assert resp.status_code == 400
    assert "Timed Mode requires timestamps" in resp.json()["detail"]


def _mock_long_synthesize(text, output_path, language="km", voice="default"):
    """Helper to generate a long 4.0s silent WAV for overflow conflict testing."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "4.0",
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return TTSAudioResult(
        audio_path=Path(output_path),
        duration_seconds=4.0,
        provider_name="gtts",
        voice=voice,
        language=language,
    )


def test_timing_conflict_detection_in_timed_mode():
    """Verify that speech exceeding available duration even at 1.25x tempo is preserved and reports conflicts."""
    created_task_id = None
    with patch("app.services.tts.google.GoogleTTSProvider.synthesize", side_effect=_mock_long_synthesize):
        req_payload = {
            "segments": [
                {
                    "segment_order": 1,
                    # Slot is only 1.5s (1.0 -> 2.5), but audio will be 4.0s!
                    "text": "ប្រយោគវែងពេកមិនអាចដាក់ក្នុងចន្លោះពេលខ្លីបានទេ។",
                    "start_time": 1.0,
                    "end_time": 2.5,
                },
                {
                    "segment_order": 2,
                    "text": "ប្រយោគបន្ទាប់។",
                    "start_time": 2.6,
                    "end_time": 4.0,
                },
            ],
            "mode": "timed",
            "provider": "gtts",
            "voice": "default",
            "language": "km",
            "target_format": "mp3",
        }
        resp = client.post("/api/toolkit/transcript-to-audio/generate", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        created_task_id = data["id"]

        conflicts = data["output_media_metadata"].get("conflicts", [])
        assert len(conflicts) >= 1
        conflict = conflicts[0]
        assert conflict["segment_order"] == 1
        assert conflict["overflow_seconds"] > 0
        assert conflict["tempo_factor"] == 1.25
        assert "Shorten Segment #1" in conflict["suggested_action"]

    if created_task_id:
        client.delete(f"/api/toolkit/tasks/{created_task_id}")


def test_segment_update_regeneration_and_deletion(db_session: Session):
    """Verify editing segment, regenerating audio, and deleting segment re-stitches timeline."""
    created_task_id = None
    with patch("app.services.tts.google.GoogleTTSProvider.synthesize", side_effect=_mock_dummy_synthesize):
        # 1. Create task with 3 segments
        req_payload = {
            "segments": [
                {"segment_order": 1, "text": "ប្រយោគមួយ។", "start_time": 0.0, "end_time": 2.0},
                {"segment_order": 2, "text": "ប្រយោគពីរ។", "start_time": 2.5, "end_time": 4.5},
                {"segment_order": 3, "text": "ប្រយោគបី។", "start_time": 5.0, "end_time": 7.0},
            ],
            "mode": "narration",
            "provider": "gtts",
            "voice": "default",
            "language": "km",
        }
        create_resp = client.post("/api/toolkit/transcript-to-audio/generate", json=req_payload)
        assert create_resp.status_code == 200
        task_data = create_resp.json()
        created_task_id = task_data["id"]
        seg2_id = task_data["tts_segments"][1]["id"]

        # 2. Update segment #2 text
        put_resp = client.put(
            f"/api/toolkit/transcript-to-audio/tasks/{created_task_id}/segments/{seg2_id}",
            json={"text": "ប្រយោគពីរដែលបានកែសម្រួលរួច។"},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["tts_segments"][1]["text"] == "ប្រយោគពីរដែលបានកែសម្រួលរួច។"

        # 3. Regenerate segment #2
        regen_resp = client.post(
            f"/api/toolkit/transcript-to-audio/tasks/{created_task_id}/segments/{seg2_id}/regenerate",
            json={"text": "ប្រយោគពីរដែលបានកែសម្រួលរួចជាស្ថាពរ។"},
        )
        assert regen_resp.status_code == 200
        assert regen_resp.json()["tts_segments"][1]["text"] == "ប្រយោគពីរដែលបានកែសម្រួលរួចជាស្ថាពរ។"
        assert regen_resp.json()["output_duration_seconds"] > 0

        # 4. Delete segment #2 and verify resequencing
        del_seg_resp = client.delete(
            f"/api/toolkit/transcript-to-audio/tasks/{created_task_id}/segments/{seg2_id}"
        )
        assert del_seg_resp.status_code == 200
        remaining_segs = del_seg_resp.json()["tts_segments"]
        assert len(remaining_segs) == 2
        assert remaining_segs[0]["segment_order"] == 1
        assert remaining_segs[1]["segment_order"] == 2
        assert remaining_segs[1]["text"] == "ប្រយោគបី។"

    # Cleanup
    if created_task_id:
        client.delete(f"/api/toolkit/tasks/{created_task_id}")
