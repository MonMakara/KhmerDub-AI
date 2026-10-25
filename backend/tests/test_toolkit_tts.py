"""
KhmerDub AI — Phase 13E.3: Standalone Text-to-Speech Studio Integration Tests
Tests voice listing, language filtering, preview synthesis, multi-sentence segmentation,
narration assembly with configurable pause duration, segment regeneration, export (MP3/WAV),
and cascade deletion.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.endpoints.toolkit import assemble_tts_narration, split_tts_text
from app.core.storage import (
    get_toolkit_task_dir,
    get_toolkit_task_output_dir,
)
from app.database.session import SessionLocal
from app.main import app
from app.models.toolkit import ToolkitTask, ToolkitTTSSegment
from app.services.tts.base import TTSAudioResult

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_toolkit_tts_voices_listing():
    """Verify listing all TTS voices and filtering by language."""
    # 1. All voices
    resp = client.get("/api/toolkit/tts/voices")
    assert resp.status_code == 200
    all_voices = resp.json()
    assert len(all_voices) >= 5
    providers = {v["provider"] for v in all_voices}
    assert "gtts" in providers
    assert "edge" in providers

    # 2. Filter language = km
    resp_km = client.get("/api/toolkit/tts/voices?language=km")
    assert resp_km.status_code == 200
    km_voices = resp_km.json()
    assert len(km_voices) >= 3
    for v in km_voices:
        assert v.get("language") == "km"

    # 3. Filter language = en
    resp_en = client.get("/api/toolkit/tts/voices?language=en")
    assert resp_en.status_code == 200
    en_voices = resp_en.json()
    assert len(en_voices) >= 2
    for v in en_voices:
        assert v.get("language") == "en"


def test_split_tts_text_khmer_and_english():
    """Verify text splitter cleanly segments Khmer sentences and English punctuation."""
    # Khmer with Khan (។) and Bariyoosan (៕)
    khmer_sample = "សួស្តីបងប្អូនទាំងអស់គ្នា។ ថ្ងៃនេះយើងនឹងសិក្សាអំពី AI dubbing។ តើអ្នកទាំងអស់គ្នាសប្បាយចិត្តទេ? បាទ ខ្ញុំសប្បាយចិត្តណាស់៕"
    segments = split_tts_text(khmer_sample, language="km")
    assert len(segments) == 4
    assert segments[0] == "សួស្តីបងប្អូនទាំងអស់គ្នា។"
    assert segments[1] == "ថ្ងៃនេះយើងនឹងសិក្សាអំពី AI dubbing។"
    assert segments[2] == "តើអ្នកទាំងអស់គ្នាសប្បាយចិត្តទេ?"
    assert segments[3] == "បាទ ខ្ញុំសប្បាយចិត្តណាស់៕"

    # English with mixed punctuation
    english_sample = "Hello world! This is KhmerDub AI. Standalone speech synthesis is working, right? Yes, absolutely."
    en_segs = split_tts_text(english_sample, language="en")
    assert len(en_segs) == 4
    assert en_segs[0] == "Hello world!"
    assert en_segs[1] == "This is KhmerDub AI."
    assert en_segs[2] == "Standalone speech synthesis is working, right?"
    assert en_segs[3] == "Yes, absolutely."

    # Empty text
    assert split_tts_text("") == []
    assert split_tts_text("   \n\n  ") == []


def test_tts_preview_endpoint():
    """Verify generating a short voice preview."""
    payload = {
        "text": "សួស្តីបងប្អូនទាំងអស់គ្នា",
        "provider": "edge",
        "voice": "km-KH-PisethNeural",
        "language": "km",
    }
    resp = client.post("/api/toolkit/tts/preview", json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/")
    assert len(resp.content) > 1000


def test_tts_preview_invalid_voice_rejected():
    """Verify unsupported voice combinations return 400 Bad Request."""
    payload = {
        "text": "សួស្តី",
        "provider": "edge",
        "voice": "non_existent_voice",
        "language": "km",
    }
    resp = client.post("/api/toolkit/tts/preview", json=payload)
    assert resp.status_code == 400
    assert "not supported" in resp.json()["detail"].lower()


def test_tts_generate_and_narration_assembly(db_session: Session):
    """Verify full end-to-end multi-segment TTS generation and narration assembly."""
    sample_text = "សួស្តីបងប្អូនទាំងអស់គ្នា។ ថ្ងៃនេះយើងសាកល្បងមុខងារថ្មី។"
    payload = {
        "text": sample_text,
        "provider": "edge",
        "voice": "km-KH-PisethNeural",
        "language": "km",
        "target_format": "mp3",
        "pause_duration_seconds": 0.4,
    }

    resp = client.post("/api/toolkit/tts/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    task_id = data["id"]
    assert data["tool_type"] == "text_to_speech"
    assert data["status"] == "completed"
    assert data["progress_percentage"] == 100
    assert data["output_filename"] == "narration.mp3"
    assert data["output_duration_seconds"] > 2.0
    assert data["output_file_size_bytes"] > 0

    # Verify segments in response and DB
    segments = data["tts_segments"]
    assert len(segments) == 2
    assert segments[0]["segment_order"] == 1
    assert segments[0]["status"] == "completed"
    assert segments[0]["duration_seconds"] > 0
    assert segments[1]["segment_order"] == 2
    assert segments[1]["status"] == "completed"

    # Verify workspace files
    out_dir = get_toolkit_task_output_dir(task_id)
    assert (out_dir / "narration.mp3").exists()
    assert (out_dir / "narration.wav").exists()
    assert (out_dir / "segment_001.mp3").exists()
    assert (out_dir / "segment_002.mp3").exists()

    # Verify stream endpoint
    stream_resp = client.get(f"/api/toolkit/tasks/{task_id}/stream")
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"].startswith("audio/")

    # Clean up test task
    del_resp = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_resp.status_code == 200


def test_tts_segment_regeneration(db_session: Session):
    """Verify individual segment regeneration re-synthesizes audio and rebuilds narration."""
    # First generate a task
    sample_text = "ប្រយោគទីមួយ។ ប្រយោគទីពីរ។"
    resp = client.post(
        "/api/toolkit/tts/generate",
        json={
            "text": sample_text,
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "target_format": "mp3",
            "pause_duration_seconds": 0.4,
        },
    )
    assert resp.status_code == 200
    task_data = resp.json()
    task_id = task_data["id"]
    seg_2 = task_data["tts_segments"][1]
    seg_2_id = seg_2["id"]
    initial_dur = task_data["output_duration_seconds"]

    # Regenerate segment 2 with expanded text
    new_text = "ប្រយោគទីពីរត្រូវបានកែសម្រួលកាន់តែវែងជាងមុន។"
    regen_resp = client.post(
        f"/api/toolkit/tts/tasks/{task_id}/segments/{seg_2_id}/regenerate",
        json={"text": new_text},
    )
    assert regen_resp.status_code == 200
    updated_data = regen_resp.json()

    updated_seg_2 = updated_data["tts_segments"][1]
    assert updated_seg_2["text"] == new_text
    assert updated_seg_2["duration_seconds"] > 0
    # The updated narration duration should have changed
    assert updated_data["output_duration_seconds"] != initial_dur

    # Clean up
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_tts_segment_streaming_and_downloading():
    """Verify streaming and downloading individual segment audio."""
    sample_text = "សួស្តីពិភពលោក។"
    resp = client.post(
        "/api/toolkit/tts/generate",
        json={
            "text": sample_text,
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "target_format": "mp3",
            "pause_duration_seconds": 0.4,
        },
    )
    assert resp.status_code == 200
    task_data = resp.json()
    task_id = task_data["id"]
    seg_id = task_data["tts_segments"][0]["id"]

    # 1. Stream
    stream_resp = client.get(f"/api/toolkit/tts/tasks/{task_id}/segments/{seg_id}/stream")
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"].startswith("audio/")
    assert "inline" in stream_resp.headers.get("content-disposition", "")

    # 2. Download
    dl_resp = client.get(f"/api/toolkit/tts/tasks/{task_id}/segments/{seg_id}/download")
    assert dl_resp.status_code == 200
    assert "attachment" in dl_resp.headers.get("content-disposition", "")

    # Clean up
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_tts_export_formats():
    """Verify exporting narration in both MP3 and WAV formats."""
    sample_text = "សួស្តីបងប្អូនទាំងអស់គ្នា។"
    resp = client.post(
        "/api/toolkit/tts/generate",
        json={
            "text": sample_text,
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "target_format": "mp3",
            "pause_duration_seconds": 0.4,
        },
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # 1. Export MP3
    mp3_resp = client.get(f"/api/toolkit/tts/tasks/{task_id}/export?format=mp3")
    assert mp3_resp.status_code == 200
    assert len(mp3_resp.content) > 0
    assert "audio/mpeg" in mp3_resp.headers.get("content-type", "")

    # 2. Export WAV
    wav_resp = client.get(f"/api/toolkit/tts/tasks/{task_id}/export?format=wav")
    assert wav_resp.status_code == 200
    assert len(wav_resp.content) > 0
    assert "audio/wav" in wav_resp.headers.get("content-type", "")

    # Clean up
    client.delete(f"/api/toolkit/tasks/{task_id}")


def test_tts_task_cascade_deletion(db_session: Session):
    """Verify deleting a TTS task removes all TTS segments in DB and wipes storage."""
    resp = client.post(
        "/api/toolkit/tts/generate",
        json={
            "text": "ប្រយោគទីមួយ។ ប្រយោគទីពីរ។",
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "target_format": "mp3",
        },
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    # Verify segments exist in DB
    segs = db_session.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.task_id == task_id).all()
    assert len(segs) == 2

    # Delete task
    del_resp = client.delete(f"/api/toolkit/tasks/{task_id}")
    assert del_resp.status_code == 200

    # Verify segments in DB are gone
    segs_after = db_session.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.task_id == task_id).all()
    assert len(segs_after) == 0

    # Verify workspace directory is deleted
    assert not get_toolkit_task_dir(task_id).exists()


def test_tts_generate_voxcpm_custom_voice(db_session: Session):
    """Verify generating speech using an authorized VoxCPM2 custom cloned voice."""
    voices_resp = client.get("/api/toolkit/tts/voices")
    assert voices_resp.status_code == 200
    custom_voices = [v for v in voices_resp.json() if v.get("is_custom") and v.get("is_available")]
    if not custom_voices:
        pytest.skip("No online authorized VoxCPM2 custom voices registered in database.")

    chosen_voice = custom_voices[0]
    resp = client.post(
        "/api/toolkit/tts/generate",
        json={
            "text": "សួស្តី នេះជាសំឡេងក្លូន VoxCPM2។",
            "provider": "voxcpm",
            "voice": chosen_voice["voice"],
            "language": "km",
            "target_format": "mp3",
            "pause_duration_seconds": 0.4,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["output_filename"] == "narration.mp3"
    assert data["output_duration_seconds"] > 0
    assert len(data["tts_segments"]) >= 1
    assert data["tts_segments"][0]["status"] == "completed"

    # Clean up
    client.delete(f"/api/toolkit/tasks/{data['id']}")
