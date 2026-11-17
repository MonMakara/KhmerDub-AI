from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.services.transcription.base import TranscriptionSegment, WordTiming
from app.services.transcription.segmentation import (
    segment_transcript,
    SegmentationMode,
)
from app.services.dubbing.scheduler import TimelineScheduler
from app.schemas.project import AudioStatusSummary


def test_segmentation_mode_enum_normalization():
    """Verify that passing SegmentationMode enums directly normalizes correctly
    and does not fall through to the wrong segmentation branch."""
    words = [
        WordTiming(word="Hello", start=0.0, end=0.5, probability=0.9),
        WordTiming(word="world.", start=0.5, end=1.0, probability=0.9),
        WordTiming(word="How", start=1.5, end=2.0, probability=0.9),
        WordTiming(word="are", start=2.0, end=2.3, probability=0.9),
        WordTiming(word="you?", start=2.3, end=2.8, probability=0.9),
    ]
    raw = [
        TranscriptionSegment(
            segment_order=1,
            start_time=0.0,
            end_time=2.8,
            text="Hello world. How are you?",
            words=words,
        )
    ]

    # 1. Mode: SegmentationMode.ORIGINAL must preserve the single raw chunk
    orig_segs = segment_transcript(raw, mode=SegmentationMode.ORIGINAL)
    assert len(orig_segs) == 1
    assert orig_segs[0].text == "Hello world. How are you?"

    # 2. String "original" must also preserve the raw chunk
    orig_str_segs = segment_transcript(raw, mode="original")
    assert len(orig_str_segs) == 1

    # 3. Mode: SegmentationMode.SENTENCE must split on sentence terminator
    sent_segs = segment_transcript(raw, mode=SegmentationMode.SENTENCE)
    assert len(sent_segs) == 2
    assert "Hello world." in sent_segs[0].text
    assert "How are you?" in sent_segs[1].text


def test_phrase_group_flexibility_eliminates_adjacent_sentence_false_conflicts():
    """Verify that conversational phrase groups share timeline flexibility so
    a slightly longer first sentence does not trigger a false conflict when the
    entire group fits comfortably before the next dialogue scene."""
    scheduler = TimelineScheduler(max_tempo=1.25, safety_margin_seconds=0.05)

    # 2 sentences in the same conversational group:
    # Sentence 1: slot 0.0 -> 1.70 (1.70s), but Khmer speech takes 2.10s
    # Sentence 2: slot 2.20 -> 3.90 (1.70s), but Khmer speech takes 1.60s
    # Next scene boundary is at 6.0s (plenty of room!)
    items = [
        {
            "segment_order": 1,
            "segment_id": "seg1",
            "start_time": 0.0,
            "end_time": 1.70,
            "orig_duration": 1.70,
            "raw_duration": 2.10,
            "khmer_text": "ឃ្លាទីមួយ",
            "english_text": "First sentence.",
        },
        {
            "segment_order": 2,
            "segment_id": "seg2",
            "start_time": 2.20,
            "end_time": 3.90,
            "orig_duration": 1.70,
            "raw_duration": 1.60,
            "khmer_text": "ឃ្លាទីពីរ",
            "english_text": "Second sentence.",
        },
    ]

    scheduled_groups = scheduler.schedule_timeline(items, target_duration=6.0, max_tempo=1.25)
    assert len(scheduled_groups) == 1
    g = scheduled_groups[0]

    # The group has sum_raw = 3.70s, avail = 6.0s -> fits naturally at 1.0x!
    assert g.group_status == "natural"
    for p in g.pieces:
        assert p.status == "natural"
        assert p.overflow_seconds == 0.0


def test_outdated_audio_does_not_generate_false_timing_conflicts():
    """Verify that outdated audio (marked is_outdated=True) is flagged as outdated
    and does not report false timing conflict errors while waiting for re-synthesis."""
    scheduler = TimelineScheduler(max_tempo=1.25)

    items = [
        {
            "segment_order": 1,
            "segment_id": "seg1",
            "start_time": 0.0,
            "end_time": 2.0,
            "orig_duration": 2.0,
            "raw_duration": 13.32,  # Stale duration from old voice
            "is_outdated": True,
            "khmer_text": "ឃ្លាថ្មី",
            "english_text": "Updated text.",
        }
    ]

    scheduled_groups = scheduler.schedule_timeline(items, target_duration=5.0)
    assert len(scheduled_groups) == 1
    p = scheduled_groups[0].pieces[0]

    assert p.status == "outdated"
    assert p.overflow_seconds == 0.0


def test_audio_status_summary_model():
    """Verify AudioStatusSummary schema counts correctly."""
    summary = AudioStatusSummary(
        total_dubbing_units=34,
        current=28,
        outdated=4,
        missing=2,
    )
    dumped = summary.model_dump()
    assert dumped["total_dubbing_units"] == 34
    assert dumped["current"] == 28
    assert dumped["outdated"] == 4
    assert dumped["missing"] == 2


def test_transcript_text_update_invalidates_translation_and_audio(client, db_session):
    """Verify that editing transcript text invalidates its linked dubbing unit and audio."""
    proj = Project(
        id="test-edit-inv",
        title="Test Edit Invalidation",
        status=ProjectStatus.VOICE_GENERATED,
        pipeline_version="v2.3",
    )
    db_session.add(proj)

    t_seg = TranscriptSegment(
        id="t-seg-1",
        project_id="test-edit-inv",
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        text="Original English line.",
        dubbing_unit_id="tr-unit-1",
    )
    tr_unit = TranslationSegment(
        id="tr-unit-1",
        project_id="test-edit-inv",
        transcript_segment_id="t-seg-1",
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        source_segment_ids='["t-seg-1"]',
        source_text="Original English line.",
        khmer_text="ឃ្លាដើម",
        is_outdated=False,
    )
    aud = GeneratedAudio(
        id="aud-1",
        project_id="test-edit-inv",
        translation_segment_id="tr-unit-1",
        audio_path="/tmp/fake.wav",
        duration_seconds=2.5,
        is_outdated=False,
    )
    db_session.add_all([t_seg, tr_unit, aud])
    db_session.commit()

    resp = client.patch(
        "/api/projects/test-edit-inv/transcript/t-seg-1",
        json={"text": "Newly edited English line."},
    )
    assert resp.status_code == 200

    db_session.refresh(tr_unit)
    db_session.refresh(aud)
    assert tr_unit.is_outdated is True
    assert tr_unit.source_text == "Newly edited English line."
    assert aud.is_outdated is True


def test_get_export_status_audio_breakdown(client, db_session):
    """Verify that get_export_status reports precise current, outdated, and missing counts."""
    proj = Project(
        id="test-export-breakdown",
        title="Test Export Breakdown",
        status=ProjectStatus.TRANSLATED,
        pipeline_version="v2.3",
    )
    db_session.add(proj)

    u1 = TranslationSegment(
        id="eb-u1",
        project_id="test-export-breakdown",
        segment_order=1,
        khmer_text="ឃ្លា១",
        start_time=0.0,
        end_time=2.0,
        is_outdated=False,
    )
    u2 = TranslationSegment(
        id="eb-u2",
        project_id="test-export-breakdown",
        segment_order=2,
        khmer_text="ឃ្លា២",
        start_time=2.5,
        end_time=4.5,
        is_outdated=False,
    )
    u3 = TranslationSegment(
        id="eb-u3",
        project_id="test-export-breakdown",
        segment_order=3,
        khmer_text="ឃ្លា៣",
        start_time=5.0,
        end_time=7.0,
        is_outdated=False,
    )

    # u1: current audio
    a1 = GeneratedAudio(
        id="eb-a1",
        project_id="test-export-breakdown",
        translation_segment_id="eb-u1",
        audio_path="/tmp/fake1.wav",
        duration_seconds=1.8,
        is_outdated=False,
    )
    # u2: outdated audio
    a2 = GeneratedAudio(
        id="eb-a2",
        project_id="test-export-breakdown",
        translation_segment_id="eb-u2",
        audio_path="/tmp/fake2.wav",
        duration_seconds=2.0,
        is_outdated=True,
    )
    # u3: no audio (missing)

    db_session.add_all([u1, u2, u3, a1, a2])
    db_session.commit()

    resp = client.get("/api/projects/test-export-breakdown/export/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["audio_status"]["total_dubbing_units"] == 3
    assert data["audio_status"]["current"] == 1
    assert data["audio_status"]["outdated"] == 1
    assert data["audio_status"]["missing"] == 1

    assert data["timing_summary"]["status"] == "speech_generation_required"
    assert data["is_export_ready"] is False

