import uuid
import zipfile
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.storage import (
    sanitize_toolkit_task_id,
    get_toolkit_task_output_dir,
    delete_toolkit_task_storage,
)
from app.database.session import SessionLocal
from app.models.toolkit import (
    ToolkitTask,
    ToolkitTranscriptSegment,
    ToolkitTranslationSegment,
)
from app.models.voice import VoiceProfile, VoiceConsent
from app.services.subtitles.parser import parse_transcript_content, TranscriptParseError
from app.api.endpoints.toolkit import (
    split_tts_text,
    _split_oversized_grapheme_string,
    build_task_bundle_zip,
)
from app.services.tts.registry import is_valid_voice_combination


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Section 5: Khmer Unicode and Language Accuracy Tests
# -----------------------------------------------------------------------------

def test_khmer_unicode_grapheme_cluster_preservation():
    """Verify that text segmentation preserves Khmer Unicode grapheme clusters."""
    # Khmer text with complex diacritics, Coeng subscript consonants, numbers, and punctuation
    khmer_text = (
        "សួស្តីបងប្អូនទាំងអស់គ្នា! ថ្ងៃទី១២ ខែតុលា ឆ្នាំ២០២៦។ "
        "KhmerDub AI គឺជាប្រព័ន្ធស្វ័យប្រវត្តិកម្មទំនើបសម្រាប់ការបកប្រែ "
        "និងបញ្ចូលសំឡេងភាសាខ្មែរប្រកបដោយគុណភាពខ្ពស់បំផុត។ "
        "សូមអរគុណយ៉ាងជ្រាលជ្រៅសម្រាប់ការគាំទ្រ!"
    )
    chunks = split_tts_text(khmer_text, language="km", max_chars=80)
    assert len(chunks) >= 2

    # Verify no chunk starts with a combining mark or ends right on a Coeng subscript joiner (\u17D2)
    for c in chunks:
        # Check first character is not combining
        import unicodedata
        assert unicodedata.combining(c[0]) == 0, f"Chunk starts with combining character: {c[0]}"
        # Check last character is not Coeng \u17D2
        assert not c.endswith('\u17d2'), "Chunk ends with unresolved Coeng joiner"

    # Empty text handling
    assert split_tts_text("", language="km") == []
    assert split_tts_text("   ", language="km") == []


def test_oversized_unbroken_string_grapheme_split():
    """Verify unusually long unbroken strings split safely without breaking combining marks."""
    # Create an unbroken string of Khmer syllables with combining marks
    base_syllable = "ខ្ញុំ"  # \u1781\u17d2\u1789\u17bb\u17c6
    long_unbroken = base_syllable * 30  # 150 characters unbroken

    splits = _split_oversized_grapheme_string(long_unbroken, max_chars=40)
    assert len(splits) >= 3

    import unicodedata
    for s in splits:
        assert len(s) <= 45
        assert unicodedata.combining(s[0]) == 0
        assert not s.endswith('\u17d2')


# -----------------------------------------------------------------------------
# Section 6: Voice Cloning Selection & Normalization Tests
# -----------------------------------------------------------------------------

def test_voice_cloning_identifier_normalization(db_session: Session):
    """Verify voice cloning combination validates both raw UUID and 'custom:<uuid>' prefix."""
    profile_id = str(uuid.uuid4())
    consent_id = str(uuid.uuid4())

    consent = VoiceConsent(
        id=consent_id,
        speaker_name="QA Speaker",
        authorized_by="QA Tester",
        consent_statement="Full authorization granted.",
        signature_hash="qa_test_hash_123",
        is_authorized=True,
    )
    db_session.add(consent)
    db_session.commit()

    profile = VoiceProfile(
        id=profile_id,
        name="QAVoice",
        consent_id=consent_id,
        gender="female",
        language="km",
        reference_audio_path="/app/data/voice_profiles/test/reference.wav",
        reference_audio_duration=12.5,
        reference_audio_sample_rate=48000,
        is_active=True,
    )
    db_session.add(profile)
    db_session.commit()

    try:
        # Raw UUID validation
        assert is_valid_voice_combination("voxcpm", profile_id, db=db_session) is True
        # Prefixed 'custom:<uuid>' validation
        assert is_valid_voice_combination("voxcpm", f"custom:{profile_id}", db=db_session) is True
        # Prefixed 'voxcpm:<uuid>' validation
        assert is_valid_voice_combination("voxcpm", f"voxcpm:{profile_id}", db=db_session) is True

        # Non-existent voice profile rejection
        assert is_valid_voice_combination("voxcpm", "non_existent_voice_id", db=db_session) is False

    finally:
        db_session.delete(profile)
        db_session.delete(consent)
        db_session.commit()


# -----------------------------------------------------------------------------
# Section 7: Timed Audio Correctness & Validation Tests
# -----------------------------------------------------------------------------

def test_parser_rejects_negative_timestamps():
    """Verify that negative timestamps in transcript parsing are strictly rejected."""
    malformed_srt = """1
-00:00:02,000 --> 00:00:04,000
Invalid negative timing.
"""
    with pytest.raises(TranscriptParseError) as exc:
        parse_transcript_content(malformed_srt, filename="test.srt")
    assert "Negative timestamp" in str(exc.value)


def test_parser_rejects_end_less_than_or_equal_to_start():
    """Verify that end times <= start times in transcript parsing are strictly rejected."""
    malformed_vtt = """WEBVTT

00:05.000 --> 00:03.000
Inverted interval.
"""
    with pytest.raises(TranscriptParseError) as exc:
        parse_transcript_content(malformed_vtt, filename="test.vtt")
    assert "must exceed start time" in str(exc.value)


def test_timed_mode_rejects_invalid_timestamps_endpoint(client: TestClient):
    """Verify POST /api/toolkit/transcript-to-audio/generate endpoint rejects invalid timestamps."""
    # Negative timestamp
    resp_neg = client.post(
        "/api/toolkit/transcript-to-audio/generate",
        json={
            "mode": "timed",
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "segments": [
                {"segment_order": 1, "text": "ជំរាបសួរ", "start_time": -1.5, "end_time": 2.0}
            ],
        },
    )
    assert resp_neg.status_code == 400
    assert "Negative timestamps are rejected" in resp_neg.json()["detail"]

    # End <= start
    resp_inverted = client.post(
        "/api/toolkit/transcript-to-audio/generate",
        json={
            "mode": "timed",
            "provider": "edge",
            "voice": "km-KH-PisethNeural",
            "language": "km",
            "segments": [
                {"segment_order": 1, "text": "ជំរាបសួរ", "start_time": 5.0, "end_time": 3.0}
            ],
        },
    )
    assert resp_inverted.status_code == 400
    assert "End time must exceed start time" in resp_inverted.json()["detail"]


# -----------------------------------------------------------------------------
# Section 8: Task Lineage, Multi-Level Outdated Propagation & Deletion Tests
# -----------------------------------------------------------------------------

def test_source_task_deletion_preserves_derived_tasks(client: TestClient, db_session: Session):
    """Verify that deleting a source task detaches and preserves all derived tasks."""
    source_id = str(uuid.uuid4())
    derived_id = str(uuid.uuid4())

    source_task = ToolkitTask(
        id=source_id,
        tool_type="audio_to_transcript",
        source_type="upload",
        source_filename="interview.mp3",
        source_file_path="/app/data/toolkit/interview.mp3",
        status="completed",
        target_format="txt",
    )
    db_session.add(source_task)
    db_session.commit()

    derived_task = ToolkitTask(
        id=derived_id,
        tool_type="text_translation",
        source_type="direct_text",
        source_task_id=source_id,
        is_outdated=False,
        source_filename="interview_translated.txt",
        source_file_path="/app/data/toolkit/interview_translated.txt",
        status="completed",
        target_format="txt",
    )
    db_session.add(derived_task)
    db_session.commit()

    try:
        # Delete source task via DELETE endpoint
        resp = client.delete(f"/api/toolkit/tasks/{source_id}")
        assert resp.status_code == 200

        # Verify source task record was removed
        deleted_source = db_session.query(ToolkitTask).filter(ToolkitTask.id == source_id).first()
        assert deleted_source is None

        # Verify derived task STILL EXISTS with decoupled lineage and outdated flag
        db_session.expire_all()
        persisted_derived = db_session.query(ToolkitTask).filter(ToolkitTask.id == derived_id).first()
        assert persisted_derived is not None
        assert persisted_derived.source_task_id is None
        assert persisted_derived.is_outdated is True

    finally:
        # Cleanup
        db_session.query(ToolkitTask).filter(ToolkitTask.id.in_([source_id, derived_id])).delete()
        db_session.commit()


def test_multi_level_lineage_outdated_propagation(client: TestClient, db_session: Session):
    """Verify editing a source transcript flags downstream tasks across multiple lineage levels."""
    src_id = str(uuid.uuid4())
    trans_id = str(uuid.uuid4())
    audio_id = str(uuid.uuid4())

    # Task A: Transcription
    task_a = ToolkitTask(
        id=src_id,
        tool_type="audio_to_transcript",
        source_type="upload",
        source_filename="talk.mp3",
        source_file_path="/app/data/toolkit/talk.mp3",
        status="completed",
        target_format="srt",
    )
    db_session.add(task_a)
    db_session.commit()

    seg_a = ToolkitTranscriptSegment(
        id=str(uuid.uuid4()),
        task_id=src_id,
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        raw_text="Good morning everyone.",
        edited_text=None,
    )
    db_session.add(seg_a)
    db_session.commit()

    # Task B: Translation derived from Task A
    task_b = ToolkitTask(
        id=trans_id,
        tool_type="transcript_translation",
        source_type="transcript_input",
        source_task_id=src_id,
        is_outdated=False,
        source_filename="talk_km.srt",
        source_file_path="/app/data/toolkit/talk_km.srt",
        status="completed",
        target_format="srt",
    )
    db_session.add(task_b)
    db_session.commit()

    # Task C: Audio narration derived from Task B
    task_c = ToolkitTask(
        id=audio_id,
        tool_type="transcript_to_audio",
        source_type="transcript_input",
        source_task_id=trans_id,
        is_outdated=False,
        source_filename="talk_km_narration.mp3",
        source_file_path="/app/data/toolkit/talk_km_narration.mp3",
        status="completed",
        target_format="mp3",
    )
    db_session.add(task_c)
    db_session.commit()

    try:
        # Edit segment in Task A
        edit_resp = client.put(
            f"/api/toolkit/tasks/{src_id}/segments/{seg_a.id}",
            json={"text": "Hello and good morning everyone."},
        )
        assert edit_resp.status_code == 200

        # Verify Task B is marked outdated
        db_session.expire_all()
        refreshed_b = db_session.query(ToolkitTask).filter(ToolkitTask.id == trans_id).first()
        assert refreshed_b.is_outdated is True

        # Now edit translation in Task B
        trans_seg = ToolkitTranslationSegment(
            id=str(uuid.uuid4()),
            task_id=trans_id,
            segment_order=1,
            start_time=0.0,
            end_time=3.0,
            source_text="Hello and good morning everyone.",
            translated_text="សួស្តី និងអរុណសួស្តីបងប្អូនទាំងអស់គ្នា។",
            status="completed",
        )
        db_session.add(trans_seg)
        db_session.commit()

        edit_trans_resp = client.put(
            f"/api/toolkit/translation/tasks/{trans_id}/segments/{trans_seg.id}",
            json={"text": "សួស្តីបងប្អូនទាំងអស់គ្នា។"},
        )
        assert edit_trans_resp.status_code == 200

        # Verify Task C is marked outdated
        db_session.expire_all()
        refreshed_c = db_session.query(ToolkitTask).filter(ToolkitTask.id == audio_id).first()
        assert refreshed_c.is_outdated is True

    finally:
        db_session.query(ToolkitTranslationSegment).filter(ToolkitTranslationSegment.task_id == trans_id).delete()
        db_session.query(ToolkitTranscriptSegment).filter(ToolkitTranscriptSegment.task_id == src_id).delete()
        db_session.query(ToolkitTask).filter(ToolkitTask.id.in_([src_id, trans_id, audio_id])).delete()
        db_session.commit()


# -----------------------------------------------------------------------------
# Section 9 & 13: Security & ZIP Bundle Integrity Tests
# -----------------------------------------------------------------------------

def test_path_traversal_sanitization():
    """Verify that task ID sanitization rejects path traversal attacks."""
    with pytest.raises(Exception):
        sanitize_toolkit_task_id("../../etc/passwd")

    with pytest.raises(Exception):
        sanitize_toolkit_task_id("task/../secret")

    # Safe valid UUID
    valid_uuid = str(uuid.uuid4())
    assert sanitize_toolkit_task_id(valid_uuid) == valid_uuid


def test_bundle_zip_contains_no_reference_recordings(db_session: Session):
    """Verify that task bundle archives only include task outputs and never voice profile references."""
    task_id = str(uuid.uuid4())
    task = ToolkitTask(
        id=task_id,
        tool_type="transcript_translation",
        source_type="transcript_input",
        source_filename="speech.srt",
        source_file_path="/app/data/toolkit/speech.srt",
        status="completed",
        target_format="srt",
    )
    db_session.add(task)
    db_session.commit()

    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "speech_translated.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nសួស្តី\n", encoding="utf-8")

    try:
        zip_path = build_task_bundle_zip(task, db_session)
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path, "r") as zf:
            file_names = zf.namelist()
            # Must contain README and translated output
            assert "README.txt" in file_names
            assert any("speech_translated.srt" in f for f in file_names)
            # Must NOT contain any voice profile reference audio or secrets
            assert not any("reference" in f.lower() for f in file_names)
            assert not any(".env" in f or "secret" in f.lower() for f in file_names)
    finally:
        delete_toolkit_task_storage(task_id)
        db_session.delete(task)
        db_session.commit()
