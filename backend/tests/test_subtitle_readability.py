import pytest
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    ProjectStatus,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    SubtitleSegment,
)
from app.services.subtitles.splitter import SubtitleSplitter
from app.services.subtitles.service import SubtitleService


@pytest.fixture
def sample_dubbed_project(db_session: Session) -> str:
    """Helper fixture creating a project with transcripts, translations, and synthesized audio."""
    proj = Project(
        title="Readability Test Video",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)
    db_session.commit()
    pid = proj.id

    t1 = TranscriptSegment(project_id=pid, segment_order=1, start_time=0.5, end_time=12.5, text="Welcome, everyone. Today, I want you to stop whatever you're doing.")
    t2 = TranscriptSegment(project_id=pid, segment_order=2, start_time=12.5, end_time=29.5, text="Am I really living or am I just existing? Everyone wants to travel the world.")
    db_session.add_all([t1, t2])
    db_session.commit()

    trans1 = TranslationSegment(project_id=pid, transcript_segment_id=t1.id, segment_order=1, khmer_text="សូមស្វាគមន៍អ្នកទាំងអស់គ្នា។ ថ្ងៃនេះខ្ញុំចង់ឱ្យអ្នកឈប់ធ្វើអ្វីដែលអ្នកកំពុងធ្វើទាំងអស់។")
    trans2 = TranslationSegment(project_id=pid, transcript_segment_id=t2.id, segment_order=2, khmer_text="តើខ្ញុំពិតជាកំពុងរស់នៅមែនឬគ្រាន់តែកំពុងមានវត្តមានទេ? មនុស្សគ្រប់គ្នាចង់ធ្វើដំណើរជុំវិញពិភពលោក។")
    db_session.add_all([trans1, trans2])
    db_session.commit()

    a1 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans1.id,
        audio_path="/app/data/a1.mp3",
        duration_seconds=11.5,
        provider="edge_tts",
        voice="km-KH-PisethNeural",
        is_outdated=False,
    )
    a2 = GeneratedAudio(
        project_id=pid,
        translation_segment_id=trans2.id,
        audio_path="/app/data/a2.mp3",
        duration_seconds=16.0,
        provider="edge_tts",
        voice="km-KH-PisethNeural",
        is_outdated=False,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    return pid


def test_splitter_khmer_long_paragraphs_and_unicode_preservation():
    """Verify long Khmer sentences split along natural sentence, clause, and conjunction boundaries."""
    # Realistic multi-sentence Khmer text with coengs, vowels, and punctuation
    text = (
        "សូមស្វាគមន៍អ្នកទាំងអស់គ្នា។ "
        "ថ្ងៃនេះខ្ញុំចង់ឱ្យអ្នកឈប់ធ្វើអ្វីដែលអ្នកកំពុងធ្វើទាំងអស់។ "
        "អង្គុយចុះបិទភ្នែកបន្តិចដកដង្ហើមឱ្យជ្រៅហើយសួរខ្លួនឯងនូវសំណួរសាមញ្ញមួយនេះ។"
    )

    chunks = SubtitleSplitter.split_text_khmer(text, max_chars=75)
    assert len(chunks) >= 3

    # Every chunk must be within readable threshold
    for c in chunks:
        assert len(c) <= 75
        assert len(c.strip()) > 0
        # Ensure no dangling COENG sign at the beginning or end of chunk
        assert not c.startswith("\u17D2")
        assert not c.endswith("\u17D2")

    # Verify orthographic cluster safety function
    assert SubtitleSplitter.is_safe_khmer_split_index("សូមស្វាគមន៍", 0) is True
    assert SubtitleSplitter.is_safe_khmer_split_index("សូមស្វាគមន៍", 4) is False  # Before coeng
    assert SubtitleSplitter.is_safe_khmer_split_index("សូមស្វាគមន៍", 5) is False  # After coeng, before subscript


def test_splitter_english_splitting_and_phrase_boundaries():
    """Verify long English sentences split at punctuation, conjunctions, and word boundaries."""
    text = (
        "Welcome, everyone. Today, I want you to stop whatever you're doing. "
        "Sit down, close your eyes for a moment, take a deep breath, and ask yourself this simple question."
    )
    chunks = SubtitleSplitter.split_text_english(text, max_chars=70)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 70


def test_estimate_split_timings_proportional_and_valid():
    """Verify proportional timing allocation preserves boundaries and prevents overlaps."""
    chunks = ["Part one here.", "Part two is significantly longer than part one.", "Part three."]
    start = 5.0
    end = 20.0
    timings = SubtitleSplitter.estimate_split_timings(chunks, start, end)

    assert len(timings) == 3
    assert timings[0][0] == 5.0
    assert timings[-1][1] == 20.0

    # Ensure strictly consecutive and non-overlapping
    for i in range(len(timings)):
        c_start, c_end = timings[i]
        assert c_start < c_end
        if i > 0:
            assert abs(c_start - timings[i - 1][1]) < 0.01


def test_calculate_readability_metrics():
    """Verify readability metrics (CPS, line count, character count, duration warnings)."""
    # High CPS warning
    metrics_fast = SubtitleSplitter.calculate_readability(
        text="This is a very fast reading caption that has way too many words for two seconds.",
        start_time=0.0,
        end_time=2.0,
        language="en",
    )
    assert metrics_fast["has_warnings"] is True
    assert any("High reading speed" in w for w in metrics_fast["warnings"])

    # Normal CPS
    metrics_ok = SubtitleSplitter.calculate_readability(
        text="សូមស្វាគមន៍អ្នកទាំងអស់គ្នា។",
        start_time=0.0,
        end_time=3.0,
        language="km",
    )
    assert metrics_ok["has_warnings"] is False


def test_api_auto_split_subtitles_endpoint(client: TestClient, sample_dubbed_project: str, db_session: Session):
    """Verify POST /api/projects/{id}/subtitles/auto-split splits long cues and persists estimated timings."""
    pid = sample_dubbed_project

    # Replace segment 1 with a realistic long Khmer paragraph
    t1 = db_session.query(TranslationSegment).filter(TranslationSegment.project_id == pid, TranslationSegment.segment_order == 1).first()
    t1.khmer_text = (
        "សូមស្វាគមន៍អ្នកទាំងអស់គ្នា។ "
        "ថ្ងៃនេះខ្ញុំចង់ឱ្យអ្នកឈប់ធ្វើអ្វីដែលអ្នកកំពុងធ្វើទាំងអស់។ "
        "អង្គុយចុះបិទភ្នែកបន្តិចដកដង្ហើមឱ្យជ្រៅហើយសួរខ្លួនឯងនូវសំណួរសាមញ្ញមួយនេះ។"
    )
    db_session.commit()

    res = client.post(
        f"/api/projects/{pid}/subtitles/auto-split",
        json={"language": "km", "max_chars": 75, "max_duration": 6.0},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_segments"] >= 3

    # Check timing confidence on split segments
    split_cues = [s for s in data["segments"] if s["timing_confidence"] == "estimated"]
    assert len(split_cues) >= 2


def test_api_manual_split_and_merge_cues(client: TestClient, sample_dubbed_project: str):
    """Verify manual splitting and merging of subtitle cues."""
    pid = sample_dubbed_project

    # Initial state: 2 cues
    initial_res = client.get(f"/api/projects/{pid}/subtitles?language=km")
    initial_count = initial_res.json()["total_segments"]

    # 1. Split cue 1 at 50%
    split_res = client.post(
        f"/api/projects/{pid}/subtitles/1/split",
        json={"language": "km", "split_ratio": 0.5},
    )
    assert split_res.status_code == 200
    after_split = split_res.json()
    assert after_split["total_segments"] == initial_count + 1

    # Check that cue 1 and cue 2 are non-overlapping and consecutive
    c1 = after_split["segments"][0]
    c2 = after_split["segments"][1]
    assert c1["segment_order"] == 1
    assert c2["segment_order"] == 2
    assert c1["end_time"] == c2["start_time"]
    assert c1["timing_confidence"] == "estimated"

    # 2. Merge cue 1 and cue 2
    merge_res = client.post(
        f"/api/projects/{pid}/subtitles/1/merge",
        json={"language": "km"},
    )
    assert merge_res.status_code == 200
    after_merge = merge_res.json()
    assert after_merge["total_segments"] == initial_count
    assert after_merge["segments"][0]["timing_confidence"] == "manual"


def test_api_timing_adjustments_and_validation(client: TestClient, sample_dubbed_project: str):
    """Verify adjusting cue start and end times with boundary and overlap validation."""
    pid = sample_dubbed_project

    # Invalid: negative start time
    bad_res1 = client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"language": "km", "start_time": -1.0},
    )
    assert bad_res1.status_code == 400
    assert "negative" in bad_res1.json()["detail"].lower()

    # Invalid: start_time >= end_time
    bad_res2 = client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"language": "km", "start_time": 5.0, "end_time": 4.0},
    )
    assert bad_res2.status_code == 400
    assert "greater than start time" in bad_res2.json()["detail"].lower()

    # Valid: adjust start_time within valid bounds
    valid_res = client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"language": "km", "start_time": 0.5, "end_time": 2.5},
    )
    assert valid_res.status_code == 200
    cue1 = valid_res.json()
    assert cue1["start_time"] == 0.5
    assert cue1["end_time"] == 2.5
    assert cue1["timing_confidence"] == "manual"


def test_source_translation_change_detection_and_keep_edits(
    client: TestClient, sample_dubbed_project: str, db_session: Session
):
    """Verify source translation changes trigger is_source_outdated warning, and keep_edits clears it."""
    pid = sample_dubbed_project

    # 1. User customizes subtitle cue 1
    client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"language": "km", "text": "ចំណងជើងរងផ្ទាល់ខ្លួន"},
    )

    # Subtitle is customized, not yet outdated
    sub_res1 = client.get(f"/api/projects/{pid}/subtitles?language=km")
    cue1 = sub_res1.json()["segments"][0]
    assert cue1["is_customized"] is True
    assert cue1["is_source_outdated"] is False

    # 2. Source Translation text changes (e.g. from translation editor or AI improve)
    trans1 = db_session.query(TranslationSegment).filter(
        TranslationSegment.project_id == pid, TranslationSegment.segment_order == 1
    ).first()
    trans1.khmer_text = "អត្ថបទបកប្រែថ្មីទាំងស្រុងពីប្រព័ន្ធ"
    db_session.commit()

    # 3. Subtitle should now be detected as outdated!
    sub_res2 = client.get(f"/api/projects/{pid}/subtitles?language=km")
    cue1_outdated = sub_res2.json()["segments"][0]
    assert cue1_outdated["is_source_outdated"] is True
    # Custom text was PRESERVED, not overwritten!
    assert cue1_outdated["text"] == "ចំណងជើងរងផ្ទាល់ខ្លួន"

    # 4. User chooses to keep their edits
    keep_res = client.post(
        f"/api/projects/{pid}/subtitles/1/keep",
        json={"language": "km"},
    )
    assert keep_res.status_code == 200
    cue1_kept = keep_res.json()["segments"][0]
    assert cue1_kept["is_source_outdated"] is False
    assert cue1_kept["text"] == "ចំណងជើងរងផ្ទាល់ខ្លួន"


def test_subtitle_edits_do_not_invalidate_audio_generation(
    client: TestClient, sample_dubbed_project: str, db_session: Session
):
    """Verify subtitle splitting, editing, and merging do NOT invalidate generated TTS audio."""
    pid = sample_dubbed_project

    # Confirm initial audio is not outdated
    audio = db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == pid).first()
    assert audio.is_outdated is False

    # Split cue
    client.post(f"/api/projects/{pid}/subtitles/1/split", json={"language": "km"})
    db_session.refresh(audio)
    assert audio.is_outdated is False

    # Edit subtitle text
    client.patch(
        f"/api/projects/{pid}/subtitles/1",
        json={"language": "km", "text": "អក្សររត់ពិសេស"},
    )
    db_session.refresh(audio)
    assert audio.is_outdated is False

    # Auto split
    client.post(f"/api/projects/{pid}/subtitles/auto-split", json={"language": "km"})
    db_session.refresh(audio)
    assert audio.is_outdated is False


def test_export_subtitles_reflects_split_segmentation(client: TestClient, sample_dubbed_project: str):
    """Verify exported SRT and WebVTT reflect split cue timings and segmentation."""
    pid = sample_dubbed_project

    # Auto split long cues
    client.post(f"/api/projects/{pid}/subtitles/auto-split", json={"language": "km"})

    # Export SRT
    srt_res = client.get(f"/api/projects/{pid}/subtitles/export?language=km&format=srt")
    assert srt_res.status_code == 200
    srt_text = srt_res.content.decode("utf-8")
    assert "-->" in srt_text
    assert "1\n" in srt_text

    # Export WebVTT
    vtt_res = client.get(f"/api/projects/{pid}/subtitles/export?language=km&format=vtt")
    assert vtt_res.status_code == 200
    vtt_text = vtt_res.content.decode("utf-8")
    assert vtt_text.startswith("WEBVTT")
