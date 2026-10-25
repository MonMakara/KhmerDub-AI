"""Unit and integration tests for Phase 13E.5 Translation Studio & Connected Workflows."""

import io
import json
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.toolkit import (
    ToolkitTask,
    ToolkitTranscriptSegment,
    ToolkitTTSSegment,
    ToolkitTranslationSegment,
)
from app.services.translation.base import TranslationProvider


class MockNLLBProvider(TranslationProvider):
    """Mock translation provider for reproducible, deterministic unit testing."""

    def translate(
        self,
        texts: list[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "standard",
    ) -> list[str]:
        results = []
        for t in texts:
            if "hello" in t.lower():
                results.append("សួស្តី")
            elif "world" in t.lower():
                results.append("ពិភពលោក")
            elif source_lang == "en" and target_lang == "km":
                results.append(f"បកប្រែ: {t}")
            elif source_lang == "km" and target_lang == "en":
                results.append(f"Translated: {t}")
            else:
                results.append(t)
        return results


@pytest.fixture(autouse=True)
def mock_translation_provider():
    """Ensure get_translation_provider returns MockNLLBProvider by default in tests."""
    with patch(
        "app.api.endpoints.toolkit.get_translation_provider",
        return_value=MockNLLBProvider(),
    ):
        yield


def test_get_translation_languages(client: TestClient):
    """Verify supported language pairs endpoint returns verified pairs."""
    resp = client.get("/api/toolkit/translation/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    pairs = [(p["source_lang"], p["target_lang"]) for p in data]
    assert ("en", "km") in pairs
    assert ("km", "en") in pairs


def test_get_translation_providers(client: TestClient):
    """Verify list of translation providers returns NLLB, Gemini, OpenAI, Claude, etc."""
    resp = client.get("/api/toolkit/translation/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [p["id"] for p in data]
    assert "nllb" in ids
    assert "gemini" in ids


def test_translate_text_standalone(client: TestClient, db_session: Session):
    """Verify standalone plain text translation into Khmer."""
    payload = {
        "text": "Hello world.\nWelcome to KhmerDub AI.",
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-text", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["tool_type"] == "text_translation"
    assert data["status"] == "completed"
    assert data["progress_percentage"] == 100
    assert "translation_segments" in data
    assert len(data["translation_segments"]) > 0

    task_id = data["id"]
    # Verify records in database
    task = db_session.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
    assert task is not None
    assert len(task.translation_segments) > 0

    # Verify disk files
    output_file = Path(task.output_file_path)
    assert output_file.exists()
    assert output_file.stat().st_size > 0
    content = output_file.read_text(encoding="utf-8")
    assert len(content.strip()) > 0


def test_translate_transcript_cues_preserving_timestamps(client: TestClient, db_session: Session):
    """Verify transcript translation preserves timestamps and checks overflow risks."""
    cues = [
        {"segment_order": 1, "text": "Hello", "start_time": 0.0, "end_time": 2.0},
        {
            "segment_order": 2,
            "text": "This is a super long sentence that will require many characters when translated into Khmer language.",
            "start_time": 2.0,
            "end_time": 2.5,  # Very short window (0.5s) to trigger overflow risk
        },
    ]
    payload = {
        "segments": cues,
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-transcript", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["tool_type"] == "transcript_translation"
    segs = data["translation_segments"]
    assert len(segs) == 2

    # Check timestamps preserved
    assert segs[0]["start_time"] == 0.0
    assert segs[0]["end_time"] == 2.0
    assert segs[1]["start_time"] == 2.0
    assert segs[1]["end_time"] == 2.5

    # Segment 2 duration is 0.5s, but translated text will take >0.5s -> is_overflow_risk = True
    assert segs[1]["is_overflow_risk"] is True


def test_update_translation_segment_and_flag_outdated(client: TestClient, db_session: Session):
    """Verify editing a translation segment updates text, regenerates files, and flags downstream tasks."""
    # 1. Create a translation task
    payload = {
        "text": "Hello world.",
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-text", json=payload)
    assert resp.status_code == 200
    trans_task_data = resp.json()
    trans_task_id = trans_task_data["id"]
    seg_id = trans_task_data["translation_segments"][0]["id"]

    # 2. Create a child TTS task linked to this translation
    tts_payload = {
        "text": "សួស្តី",
        "provider": "gtts",
        "voice": "default",
        "language": "km",
        "source_task_id": trans_task_id,
    }
    with patch("app.services.tts.google.GoogleTTSProvider.synthesize") as mock_synth:
        def fake_synth(text, output_path, **kwargs):
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "1.0", "-c:a", "libmp3lame", str(output_path)
            ], check=True, capture_output=True)
        mock_synth.side_effect = fake_synth

        tts_resp = client.post("/api/toolkit/tts/generate", json=tts_payload)
        assert tts_resp.status_code == 200
        tts_data = tts_resp.json()
        tts_task_id = tts_data["id"]
        assert tts_data["source_task_id"] == trans_task_id
        assert tts_data["is_outdated"] is False

    # 3. Edit the translation segment in the parent task
    edit_resp = client.put(
        f"/api/toolkit/translation/tasks/{trans_task_id}/segments/{seg_id}",
        json={"text": "ជំរាបសួរលោកអ្នក"},
    )
    assert edit_resp.status_code == 200
    updated_seg = edit_resp.json()
    assert updated_seg["text"] == "ជំរាបសួរលោកអ្នក"
    assert updated_seg["is_edited"] is True

    # 4. Check that child task was flagged as is_outdated
    child_task = db_session.query(ToolkitTask).filter(ToolkitTask.id == tts_task_id).first()
    assert child_task is not None
    assert child_task.is_outdated is True


def test_retry_translation_segment(client: TestClient, db_session: Session):
    """Verify single segment re-translation."""
    payload = {
        "text": "Hello world.",
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-text", json=payload)
    assert resp.status_code == 200
    trans_task = resp.json()
    trans_task_id = trans_task["id"]
    seg_id = trans_task["translation_segments"][0]["id"]

    # Retry the segment
    retry_resp = client.post(
        f"/api/toolkit/translation/tasks/{trans_task_id}/segments/{seg_id}/retry"
    )
    assert retry_resp.status_code == 200
    retried_seg = retry_resp.json()
    assert retried_seg["status"] == "completed"
    assert retried_seg["is_edited"] is False


def test_subtitle_conversion(client: TestClient):
    """Verify one-click conversion between SRT and WebVTT."""
    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,500\nសួស្តីបងប្អូនទាំងអស់គ្នា\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nសូមស្វាគមន៍\n"
    )

    # Convert SRT -> VTT
    resp = client.post(
        "/api/toolkit/subtitle/convert",
        json={
            "content": srt_content,
            "source_format": "srt",
            "target_format": "vtt",
            "filename": "demo.srt",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_format"] == "vtt"
    assert "WEBVTT" in data["content"]
    assert "00:00:01.000 --> 00:00:03.500" in data["content"]
    assert "សួស្តីបងប្អូនទាំងអស់គ្នា" in data["content"]

    # Convert VTT -> SRT
    vtt_content = data["content"]
    resp2 = client.post(
        "/api/toolkit/subtitle/convert",
        json={
            "content": vtt_content,
            "source_format": "vtt",
            "target_format": "srt",
            "filename": "demo.vtt",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["target_format"] == "srt"
    assert "00:00:01,000 --> 00:00:03,500" in data2["content"]
    assert "សួស្តីបងប្អូនទាំងអស់គ្នា" in data2["content"]


def test_cyclic_provenance_prevention(client: TestClient, db_session: Session):
    """Verify cyclic task lineage dependencies are rejected."""
    t1 = ToolkitTask(
        id=str(uuid.uuid4()),
        tool_type="text_translation",
        source_type="direct_text",
        source_filename="test1.txt",
        source_file_path="/tmp/test1.txt",
        target_format="txt",
        status="completed",
    )
    t2 = ToolkitTask(
        id=str(uuid.uuid4()),
        tool_type="text_to_speech",
        source_type="direct_text",
        source_task_id=t1.id,
        source_filename="test2.txt",
        source_file_path="/tmp/test2.txt",
        target_format="mp3",
        status="completed",
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    from app.api.endpoints.toolkit import validate_task_provenance
    from fastapi import HTTPException

    # t1 setting source to t2 creates cycle: t2 -> t1 -> t2
    with pytest.raises(HTTPException) as exc_info:
        validate_task_provenance(source_task_id=t2.id, current_task_id=t1.id, db=db_session)
    assert exc_info.value.status_code == 400


def test_task_bundle_zip_download(client: TestClient, db_session: Session):
    """Verify consolidated ZIP archive generation and safe path layout."""
    payload = {
        "text": "Hello world.",
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-text", json=payload)
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # Request ZIP bundle
    bundle_resp = client.get(f"/api/toolkit/tasks/{task_id}/bundle")
    assert bundle_resp.status_code == 200
    assert bundle_resp.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    zip_bytes = io.BytesIO(bundle_resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert "README.txt" in namelist
        # Verify no path traversal
        for name in namelist:
            assert ".." not in name
            assert not name.startswith("/")


def test_translation_task_cascade_deletion(client: TestClient, db_session: Session):
    """Verify deleting a translation task cascades to its segments and workspace files."""
    payload = {
        "text": "Hello world.",
        "source_lang": "en",
        "target_lang": "km",
        "provider": "nllb",
    }
    resp = client.post("/api/toolkit/translation/translate-text", json=payload)
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # Confirm segments exist
    segs = db_session.query(ToolkitTranslationSegment).filter(ToolkitTranslationSegment.task_id == task_id).all()
    assert len(segs) > 0

    # Delete task
    del_resp = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_resp.status_code == 200

    # Verify task and segments are removed from database
    task_after = db_session.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
    assert task_after is None
    segs_after = db_session.query(ToolkitTranslationSegment).filter(ToolkitTranslationSegment.task_id == task_id).all()
    assert len(segs_after) == 0
