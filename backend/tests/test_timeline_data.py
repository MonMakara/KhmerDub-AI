import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)


def test_timeline_segment_positioning_and_durations(client: TestClient, db_session: Session):
    """Verify that segment timestamps and audio durations for the timeline match expectations."""
    # 1. Create project
    proj = Project(
        title="Timeline Test Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)
    db_session.commit()
    pid = proj.id

    # 2. Add video with duration
    video = Video(
        project_id=pid,
        filename="timeline_sample.mp4",
        file_path="/app/data/uploads/sample.mp4",
        file_size_bytes=1000000,
        duration_seconds=30.0,
    )
    db_session.add(video)

    # 3. Add 3 segments:
    # Seg 1: 0.0s -> 5.0s (next_start: 6.0s => avail: 6.0s, speech: 4.0s => fits natural)
    # Seg 2: 6.0s -> 7.5s (next_start: 8.0s => avail: 2.0s, speech: 5.0s => blocking conflict!)
    # Seg 3: 8.0s -> 11.0s (next_start: end => avail: 22.0s, speech: 3.5s => fits natural)
    t1 = TranscriptSegment(project_id=pid, segment_order=1, start_time=0.0, end_time=5.0, text="First segment")
    t2 = TranscriptSegment(project_id=pid, segment_order=2, start_time=6.0, end_time=7.5, text="Second segment")
    t3 = TranscriptSegment(project_id=pid, segment_order=3, start_time=8.0, end_time=11.0, text="Third segment")
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    trans1 = TranslationSegment(project_id=pid, transcript_segment_id=t1.id, segment_order=1, khmer_text="ផ្នែកទីមួយ")
    trans2 = TranslationSegment(project_id=pid, transcript_segment_id=t2.id, segment_order=2, khmer_text="ផ្នែកទីពីរ")
    trans3 = TranslationSegment(project_id=pid, transcript_segment_id=t3.id, segment_order=3, khmer_text="ផ្នែកទីបី")
    db_session.add_all([trans1, trans2, trans3])
    db_session.commit()

    a1 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans1.id,
        audio_path="/app/data/test_a1.mp3",
        duration_seconds=4.0,
    )
    a2 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans2.id,
        audio_path="/app/data/test_a2.mp3",
        duration_seconds=5.0,
    )
    a3 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans3.id,
        audio_path="/app/data/test_a3.mp3",
        duration_seconds=3.5,
    )
    db_session.add_all([a1, a2, a3])
    db_session.commit()

    # 4. Check generated-audio API returns accurate timeline durations and audio URLs
    audio_res = client.get(f"/api/projects/{pid}/generated-audio")
    assert audio_res.status_code == 200
    audios = audio_res.json()["audios"]
    assert len(audios) == 3
    assert audios[0]["duration_seconds"] == 4.0
    assert audios[0]["audio_url"] == f"/api/projects/{pid}/tts/{trans1.id}/audio"
    assert audios[1]["duration_seconds"] == 5.0
    assert audios[2]["duration_seconds"] == 3.5

    # 5. Check export status detects the blocking timing conflict on Seg 2
    export_res = client.get(f"/api/projects/{pid}/export/status")
    assert export_res.status_code == 200
    conflicts = export_res.json()["timing_conflicts"]
    assert len(conflicts) >= 1
    c2 = next((c for c in conflicts if c["segment_order"] == 2), None)
    assert c2 is not None
    assert c2["overflow_seconds"] > 0
    assert c2["required_tempo"] > 1.25


def test_timeline_outdated_audio_invalidation(client: TestClient, db_session: Session):
    """Verify editing a translation segment marks generated audio as outdated for the timeline."""
    proj = Project(
        title="Outdated Timeline Test",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)
    db_session.commit()

    t_seg = TranscriptSegment(project_id=proj.id, segment_order=1, start_time=1.0, end_time=4.0, text="Initial speech")
    db_session.add(t_seg)
    db_session.commit()

    trans = TranslationSegment(project_id=proj.id, transcript_segment_id=t_seg.id, segment_order=1, khmer_text="ពាក្យដំបូង")
    db_session.add(trans)
    db_session.commit()

    audio = GeneratedAudio(
        project_id=proj.id,
        translation_segment_id=trans.id,
        audio_path="/app/data/test_outdated.mp3",
        duration_seconds=2.8,
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Edit translation text
    edit_res = client.patch(
        f"/api/projects/{proj.id}/translations/{trans.id}",
        json={"khmer_text": "ពាក្យកែប្រែថ្មី"},
    )
    assert edit_res.status_code == 200

    # Verify audio is marked outdated
    db_session.refresh(audio)
    assert audio.is_outdated is True
