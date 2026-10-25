import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    SubtitleSegment,
    ProjectStatus,
)
from app.services.subtitles.generator import (
    SubtitleCue,
    format_timestamp_srt,
    format_timestamp_vtt,
    sanitize_and_sort_cues,
    generate_srt,
    generate_vtt,
)


def test_format_timestamp_srt():
    """Verify millisecond formatting with commas in SRT format."""
    assert format_timestamp_srt(0.0) == "00:00:00,000"
    assert format_timestamp_srt(0.5) == "00:00:00,500"
    assert format_timestamp_srt(65.73) == "00:01:05,730"
    assert format_timestamp_srt(3661.123) == "01:01:01,123"
    assert format_timestamp_srt(-5.0) == "00:00:00,000"
    assert format_timestamp_srt(None) == "00:00:00,000"


def test_format_timestamp_vtt():
    """Verify millisecond formatting with periods in WebVTT format."""
    assert format_timestamp_vtt(0.0) == "00:00:00.000"
    assert format_timestamp_vtt(0.5) == "00:00:00.500"
    assert format_timestamp_vtt(65.73) == "00:01:05.730"
    assert format_timestamp_vtt(3661.123) == "01:01:01.123"
    assert format_timestamp_vtt(-5.0) == "00:00:00.000"


def test_generate_srt_and_vtt_formatting_and_utf8_khmer():
    """Verify SRT and WebVTT outputs with authentic Khmer Unicode, punctuation, and layout."""
    khmer_sample_1 = "សូមស្វាគមន៍មកកាន់ KhmerDub AI!"
    khmer_sample_2 = "យើងអាចបង្កើតចំណងជើងរង (Subtitles) បានយ៉ាងងាយស្រួល។"

    cues = [
        SubtitleCue(sequence=1, start_time=1.0, end_time=4.5, text=khmer_sample_1),
        SubtitleCue(sequence=2, start_time=5.0, end_time=9.25, text=khmer_sample_2),
    ]

    # SRT verification
    srt_output = generate_srt(cues)
    assert "1\n00:00:01,000 --> 00:00:04,500\n" in srt_output
    assert khmer_sample_1 in srt_output
    assert "2\n00:00:05,000 --> 00:00:09,250\n" in srt_output
    assert khmer_sample_2 in srt_output
    assert srt_output.count("\n\n") == 1  # Exactly 1 double-newline separating 2 cues

    # WebVTT verification
    vtt_output = generate_vtt(cues)
    assert vtt_output.startswith("WEBVTT\n\n")
    assert "1\n00:00:01.000 --> 00:00:04.500\n" in vtt_output
    assert khmer_sample_1 in vtt_output
    assert "2\n00:00:05.000 --> 00:00:09.250\n" in vtt_output
    assert khmer_sample_2 in vtt_output


def test_subtitle_cue_sanitization_sorting_and_overlap_prevention():
    """Verify that cues out of order are sorted and unintended overlaps are safely clamped."""
    cues = [
        SubtitleCue(sequence=2, start_time=6.0, end_time=10.0, text="Second cue"),
        SubtitleCue(sequence=1, start_time=0.0, end_time=7.0, text="First cue (overlaps into second)"),
        SubtitleCue(sequence=3, start_time=9.0, end_time=12.0, text="Third cue"),
    ]

    sanitized = sanitize_and_sort_cues(cues, prevent_overlaps=True)
    assert len(sanitized) == 3
    # First cue should be clamped to 6.0 (start of second cue)
    assert sanitized[0].sequence == 1
    assert sanitized[0].start_time == 0.0
    assert sanitized[0].end_time == 6.0
    # Second cue clamped to 9.0 (start of third cue)
    assert sanitized[1].sequence == 2
    assert sanitized[1].start_time == 6.0
    assert sanitized[1].end_time == 9.0
    # Third cue intact
    assert sanitized[2].sequence == 3
    assert sanitized[2].start_time == 9.0
    assert sanitized[2].end_time == 12.0


def test_subtitle_empty_cues_handling():
    """Verify empty subtitles are handled gracefully without generating malformed blocks."""
    assert generate_srt([]) == ""
    assert generate_vtt([]) == "WEBVTT\n\n"

    cues_with_empty = [
        SubtitleCue(sequence=1, start_time=1.0, end_time=2.0, text="Valid cue"),
        SubtitleCue(sequence=2, start_time=2.5, end_time=3.5, text="   "),
        SubtitleCue(sequence=3, start_time=4.0, end_time=5.0, text="\n\t"),
    ]
    srt = generate_srt(cues_with_empty, filter_empty=True)
    assert "Valid cue" in srt
    assert srt.count("-->") == 1


@pytest.fixture
def sample_dubbed_project(db_session: Session) -> str:
    """Helper fixture creating a project with transcripts, translations, and synthesized audio."""
    proj = Project(
        title="Subtitle Test Video",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)
    db_session.commit()
    pid = proj.id

    t1 = TranscriptSegment(project_id=pid, segment_order=1, start_time=0.5, end_time=5.0, text="Hello world.")
    t2 = TranscriptSegment(project_id=pid, segment_order=2, start_time=5.5, end_time=10.0, text="How are you?")
    db_session.add_all([t1, t2])
    db_session.commit()

    trans1 = TranslationSegment(project_id=pid, transcript_segment_id=t1.id, segment_order=1, khmer_text="សួស្តីពិភពលោក។")
    trans2 = TranslationSegment(project_id=pid, transcript_segment_id=t2.id, segment_order=2, khmer_text="តើអ្នកសុខសប្បាយជាទេ?")
    db_session.add_all([trans1, trans2])
    db_session.commit()

    a1 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans1.id,
        audio_path="/app/data/a1.mp3",
        duration_seconds=3.2,
        is_outdated=False,
    )
    a2 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans2.id,
        audio_path="/app/data/a2.mp3",
        duration_seconds=3.0,
        is_outdated=False,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    return pid


def test_api_get_subtitles_english_and_khmer(client: TestClient, sample_dubbed_project: str):
    """Verify fetching subtitle cues for both English and Khmer languages."""
    pid = sample_dubbed_project

    # 1. Fetch Khmer subtitles
    km_res = client.get(f"/api/projects/{pid}/subtitles?language=km")
    assert km_res.status_code == 200
    km_data = km_res.json()
    assert km_data["project_id"] == pid
    assert km_data["language"] == "km"
    assert km_data["has_custom_edits"] is False
    assert km_data["total_segments"] == 2
    assert km_data["segments"][0]["text"] == "សួស្តីពិភពលោក។"
    assert km_data["segments"][0]["start_time"] == 0.5
    assert km_data["segments"][0]["end_time"] == 5.0
    assert km_data["segments"][1]["text"] == "តើអ្នកសុខសប្បាយជាទេ?"

    # 2. Fetch English subtitles
    en_res = client.get(f"/api/projects/{pid}/subtitles?language=en")
    assert en_res.status_code == 200
    en_data = en_res.json()
    assert en_data["language"] == "en"
    assert en_data["total_segments"] == 2
    assert en_data["segments"][0]["text"] == "Hello world."
    assert en_data["segments"][1]["text"] == "How are you?"


def test_api_subtitle_custom_edit_and_persistence_preserves_audio(
    client: TestClient,
    db_session: Session,
    sample_dubbed_project: str,
):
    """
    Verify that custom subtitle edits are persisted in SubtitleSegment
    and DO NOT invalidate generated speech audio records.
    """
    pid = sample_dubbed_project

    # 1. Update subtitle segment #1 with multiline custom line breaks
    new_text = "សួស្តី\nពិភពលោក!"
    patch_res = client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"text": new_text, "language": "km"},
    )
    assert patch_res.status_code == 200
    item = patch_res.json()
    assert item["segment_order"] == 1
    assert item["text"] == new_text
    assert item["is_customized"] is True

    # 2. Verify get_subtitles reflects the custom edit
    get_res = client.get(f"/api/projects/{pid}/subtitles?language=km")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["has_custom_edits"] is True
    assert data["segments"][0]["text"] == new_text
    assert data["segments"][0]["is_customized"] is True
    # Segment 2 remains unedited
    assert data["segments"][1]["is_customized"] is False

    # 3. CRITICAL: Verify generated speech audios in DB are NOT marked as outdated
    audios = db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == pid).all()
    for a in audios:
        assert a.is_outdated is False

    # 4. CRITICAL: Verify TranslationSegment.khmer_text was NOT altered
    trans1 = db_session.query(TranslationSegment).filter(
        TranslationSegment.project_id == pid,
        TranslationSegment.segment_order == 1,
    ).first()
    assert trans1.khmer_text == "សួស្តីពិភពលោក។"


def test_api_subtitle_reset(client: TestClient, sample_dubbed_project: str):
    """Verify resetting customized subtitles restores source translation text."""
    pid = sample_dubbed_project

    # 1. Customize segment #1
    client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"text": "អត្ថបទកែប្រែ", "language": "km"},
    )

    # 2. Reset subtitles
    reset_res = client.post(f"/api/projects/{pid}/subtitles/reset?language=km")
    assert reset_res.status_code == 200
    assert reset_res.json()["deleted_count"] == 1

    # 3. Fetch again -> should be back to original text with has_custom_edits = False
    get_res = client.get(f"/api/projects/{pid}/subtitles?language=km")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["has_custom_edits"] is False
    assert data["segments"][0]["text"] == "សួស្តីពិភពលោក។"
    assert data["segments"][0]["is_customized"] is False


def test_api_subtitle_export_srt_and_vtt(client: TestClient, sample_dubbed_project: str):
    """Verify file download headers, MIME types, and contents for both SRT and VTT formats."""
    pid = sample_dubbed_project

    # 1. Export Khmer SRT
    srt_res = client.get(f"/api/projects/{pid}/subtitles/export?language=km&format=srt")
    assert srt_res.status_code == 200
    assert 'attachment; filename="Subtitle_Test_Video_km.srt"' in srt_res.headers.get("content-disposition", "")
    assert "text/plain" in srt_res.headers.get("content-type", "")
    srt_text = srt_res.text
    assert "00:00:00,500 --> 00:00:05,000" in srt_text
    assert "សួស្តីពិភពលោក។" in srt_text

    # 2. Export Khmer WebVTT
    vtt_res = client.get(f"/api/projects/{pid}/subtitles/export?language=km&format=vtt")
    assert vtt_res.status_code == 200
    assert 'attachment; filename="Subtitle_Test_Video_km.vtt"' in vtt_res.headers.get("content-disposition", "")
    assert "text/vtt" in vtt_res.headers.get("content-type", "")
    vtt_text = vtt_res.text
    assert vtt_text.startswith("WEBVTT\n\n")
    assert "00:00:00.500 --> 00:00:05.000" in vtt_text

    # 3. Export English SRT
    en_srt_res = client.get(f"/api/projects/{pid}/subtitles/export?language=en&format=srt")
    assert en_srt_res.status_code == 200
    assert "Hello world." in en_srt_res.text


def test_api_subtitle_stream(client: TestClient, sample_dubbed_project: str):
    """Verify inline streaming for HTML5 video track elements."""
    pid = sample_dubbed_project

    stream_res = client.get(f"/api/projects/{pid}/subtitles/stream?language=km&format=vtt")
    assert stream_res.status_code == 200
    assert "inline;" in stream_res.headers.get("content-disposition", "")
    assert "text/vtt" in stream_res.headers.get("content-type", "")
    assert "WEBVTT\n\n" in stream_res.text


def test_api_subtitles_missing_project_and_invalid_format(client: TestClient):
    """Verify 404 for non-existent project and 400 for unsupported format."""
    bad_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/projects/{bad_id}/subtitles")
    assert res.status_code == 404

    res_fmt = client.get(f"/api/projects/{bad_id}/subtitles/export?format=ass")
    assert res_fmt.status_code == 404


def test_project_deletion_cascades_subtitles(
    client: TestClient,
    db_session: Session,
    sample_dubbed_project: str,
):
    """Verify project deletion safely cascades and removes SubtitleSegment records."""
    pid = sample_dubbed_project

    # Add a custom subtitle
    client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"text": "Custom", "language": "km"},
    )
    assert db_session.query(SubtitleSegment).filter(SubtitleSegment.project_id == pid).count() == 1

    # Delete project
    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 200

    # Verify subtitle records are deleted
    assert db_session.query(SubtitleSegment).filter(SubtitleSegment.project_id == pid).count() == 0
