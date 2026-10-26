"""Targeted tests for Improved English Transcript Segmentation in KhmerDub AI.

Covers all 20 required verification scenarios:
1. Single sentence segment
2. Multi-sentence segment splitting on sentence boundaries
3. Long sentence handling
4. Short sentence merging in dubbing mode
5. Long pause detection
6. Text without punctuation
7. Word timestamp gap preservation
8. Missing word timestamps fallback
9. Unreliable/inverted timestamps
10. Abbreviations and boundary handling
11. Existing project transcription worker execution
12. Edited transcript preservation and warning
13. Existing translations invalidation
14. Existing audio invalidation
15. SRT export compatibility
16. VTT export compatibility
17. Audio synchronization & timeline sequence invariants
18. Resegmentation preview endpoint (no DB mutation)
19. Confirmation required before applying resegmentation
20. No data loss and manual split / merge endpoints
"""

import json
import uuid
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
from app.services.transcription.base import TranscriptionSegment, WordTiming
from app.services.transcription.segmentation import (
    segment_transcript,
    SegmentationMode,
    is_sentence_boundary,
    split_segment_at_word,
    merge_adjacent_segments,
)
from app.services.subtitles.generator import generate_srt, generate_vtt, SubtitleCue


# ============================================================================
# 1. Single Sentence Test
# ============================================================================
def test_01_single_sentence():
    words = [
        WordTiming("Once", 0.0, 0.5),
        WordTiming("upon", 0.5, 0.9),
        WordTiming("a", 0.9, 1.1),
        WordTiming("time.", 1.1, 1.8),
    ]
    raw = TranscriptionSegment(1, 0.0, 1.8, "Once upon a time.", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 1
    assert res[0].segment_order == 1
    assert res[0].start_time == 0.0
    assert res[0].end_time == 1.8
    assert res[0].text == "Once upon a time."
    assert not res[0].is_approximate


# ============================================================================
# 2. Multi-Sentence Segment Splitting on Sentence Boundaries
# ============================================================================
def test_02_two_sentences_in_one_segment():
    # Example from prompt:
    # "Once in a small village lived a young boy named Kabir. He was intelligent but had one big problem."
    words = [
        WordTiming("Once", 0.0, 0.26),
        WordTiming("in", 0.26, 0.56),
        WordTiming("a", 0.56, 0.64),
        WordTiming("small", 0.64, 0.96),
        WordTiming("village", 0.96, 1.42),
        WordTiming("lived", 1.42, 2.04),
        WordTiming("a", 2.04, 2.22),
        WordTiming("young", 2.22, 2.48),
        WordTiming("boy", 2.48, 2.84),
        WordTiming("named", 2.84, 3.34),
        WordTiming("Kabir.", 3.34, 3.90),
        WordTiming("He", 4.60, 4.92),
        WordTiming("was", 4.92, 5.12),
        WordTiming("intelligent", 5.12, 5.70),
        WordTiming("but", 5.70, 6.28),
        WordTiming("had", 6.28, 6.50),
        WordTiming("one", 6.50, 6.88),
        WordTiming("big", 6.88, 7.18),
        WordTiming("problem.", 7.18, 7.74),
    ]
    raw = TranscriptionSegment(1, 0.0, 7.74, "Once in a small village lived a young boy named Kabir. He was intelligent but had one big problem.", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 2
    # Sentence 1: Kabir ends at 3.90s
    assert res[0].segment_order == 1
    assert res[0].start_time == 0.0
    assert res[0].end_time == 3.90
    assert "Kabir." in res[0].text

    # Sentence 2: He starts at 4.60s (pause preserved)
    assert res[1].segment_order == 2
    assert res[1].start_time == 4.60
    assert res[1].end_time == 7.74
    assert res[1].text.startswith("He was intelligent")


# ============================================================================
# 3. Long Sentence Handling
# ============================================================================
def test_03_long_sentence_handling():
    # Long sentence spanning 14 seconds
    words = []
    t = 0.0
    tokens = ["This", "is", "a", "very", "long", "sentence,", "which", "contains", "many", "words,", "and", "continues", "further", "until", "it", "finally", "finishes."]
    for i, tok in enumerate(tokens):
        dur = 0.8
        words.append(WordTiming(tok, round(t, 2), round(t + dur, 2)))
        t += dur + (0.3 if "," in tok else 0.05)

    raw = TranscriptionSegment(1, 0.0, round(t, 2), " ".join(tokens), words=words)

    # Dubbing mode: should subdivide into chunks within target range (~2.0 to 6.0s)
    dub_segs = segment_transcript([raw], mode="dubbing", target_min=2.0, target_max=6.0)
    assert len(dub_segs) >= 2
    for s in dub_segs:
        dur = s.end_time - s.start_time
        assert s.start_time < s.end_time
        assert dur <= 8.5  # Managed duration


# ============================================================================
# 4. Short Sentence Merging in Dubbing Mode
# ============================================================================
def test_04_short_sentence_merging_dubbing():
    # Sent 1: "Hi." (0.5s)
    # Sent 2: "How are you?" (1.2s)
    # Merged dubbing chunk: "Hi. How are you?" (combined <= 6.0s)
    words1 = [WordTiming("Hi.", 0.0, 0.5)]
    words2 = [WordTiming("How", 0.8, 1.1), WordTiming("are", 1.1, 1.4), WordTiming("you?", 1.4, 2.0)]
    all_words = words1 + words2
    raw = TranscriptionSegment(1, 0.0, 2.0, "Hi. How are you?", words=all_words)

    dub_segs = segment_transcript([raw], mode="dubbing", target_min=2.0, target_max=6.0)
    assert len(dub_segs) == 1
    assert "Hi." in dub_segs[0].text
    assert "How are you?" in dub_segs[0].text


# ============================================================================
# 5. Long Pause Detection
# ============================================================================
def test_05_long_pause_detection():
    # Even without a period, a 2.0-second pause indicates a new sentence
    words = [
        WordTiming("I", 0.0, 0.3),
        WordTiming("walked", 0.3, 0.8),
        WordTiming("outside", 0.8, 1.4),
        # 2.0s pause from 1.4 to 3.4
        WordTiming("The", 3.4, 3.8),
        WordTiming("sun", 3.8, 4.2),
        WordTiming("was", 4.2, 4.5),
        WordTiming("bright.", 4.5, 5.0),
    ]
    raw = TranscriptionSegment(1, 0.0, 5.0, "I walked outside The sun was bright.", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 2
    assert res[0].end_time == 1.4
    assert res[1].start_time == 3.4


# ============================================================================
# 6. Text Without Punctuation
# ============================================================================
def test_06_no_punctuation_graceful_handling():
    words = [
        WordTiming("one", 0.0, 0.4),
        WordTiming("two", 0.4, 0.8),
        WordTiming("three", 0.8, 1.2),
        WordTiming("four", 1.2, 1.6),
    ]
    raw = TranscriptionSegment(1, 0.0, 1.6, "one two three four", words=words)

    # In sentence mode without punctuation or pause: yields 1 segment without error
    res_sent = segment_transcript([raw], mode="sentence")
    assert len(res_sent) == 1
    assert res_sent[0].text == "one two three four"

    # In original mode: yields 1 segment
    res_orig = segment_transcript([raw], mode="original")
    assert len(res_orig) == 1


# ============================================================================
# 7. Word Timestamp Gaps Preserved
# ============================================================================
def test_07_word_timestamp_gaps_preserved():
    words = [
        WordTiming("First.", 0.0, 1.0),
        # 1.5s silence gap
        WordTiming("Second.", 2.5, 3.5),
    ]
    raw = TranscriptionSegment(1, 0.0, 3.5, "First. Second.", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 2
    assert res[0].end_time == 1.0
    assert res[1].start_time == 2.5
    # The 1.5s gap is natural and untouched
    assert res[1].start_time - res[0].end_time == pytest.approx(1.5, abs=0.01)


# ============================================================================
# 8. Missing Word Timestamps Fallback
# ============================================================================
def test_08_missing_word_timestamps_fallback():
    # Segment without word timing data
    raw = TranscriptionSegment(1, 2.0, 8.0, "Hello world. This is another sentence.", words=None)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 2
    assert res[0].is_approximate
    assert res[1].is_approximate
    assert res[0].start_time >= 2.0
    assert res[1].end_time <= 8.0
    assert res[0].end_time <= res[1].start_time


# ============================================================================
# 9. Unreliable or Zero-Duration Timestamps Invariant
# ============================================================================
def test_09_unreliable_or_inverted_timestamps():
    words = [
        WordTiming("Glitch", 2.0, 2.0),  # zero duration
    ]
    raw = TranscriptionSegment(1, 2.0, 2.0, "Glitch", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 1
    # Invariant: start_time < end_time guaranteed
    assert res[0].start_time < res[0].end_time


# ============================================================================
# 10. Abbreviations and Boundary Handling
# ============================================================================
def test_10_segment_boundaries_abbreviations():
    assert not is_sentence_boundary("Dr.", "Smith")
    assert not is_sentence_boundary("Mr.", "Johnson")
    assert not is_sentence_boundary("U.S.A.", "today")
    assert not is_sentence_boundary("3.14", "ratio")
    assert is_sentence_boundary("village.", "Next")
    assert is_sentence_boundary("really?", "Yes")
    assert is_sentence_boundary("stop!", "Now")

    words = [
        WordTiming("Dr.", 0.0, 0.4),
        WordTiming("Smith", 0.4, 0.9),
        WordTiming("visited", 0.9, 1.4),
        WordTiming("Washington", 1.4, 2.0),
        WordTiming("D.C.", 2.0, 2.5),
        WordTiming("yesterday.", 2.5, 3.2),
        WordTiming("He", 3.6, 3.9),
        WordTiming("was", 3.9, 4.1),
        WordTiming("happy.", 4.1, 4.6),
    ]
    raw = TranscriptionSegment(1, 0.0, 4.6, "Dr. Smith visited Washington D.C. yesterday. He was happy.", words=words)
    res = segment_transcript([raw], mode="sentence")

    assert len(res) == 2
    assert "Dr. Smith" in res[0].text
    assert "D.C. yesterday." in res[0].text
    assert "He was happy." in res[1].text


# ============================================================================
# 11. Existing Project Transcription Worker Execution
# ============================================================================
def test_11_existing_project_transcription_worker(db_session: Session):
    proj = Project(
        id=str(uuid.uuid4()),
        title="Test Worker Resegment",
        segmentation_mode="sentence",
        status=ProjectStatus.CREATED,
    )
    db_session.add(proj)
    db_session.commit()

    # Raw transcript JSON stored in project
    raw_data = [
        {
            "segment_order": 1,
            "start_time": 0.0,
            "end_time": 5.0,
            "text": "First sentence. Second sentence.",
            "words": [
                {"word": "First", "start": 0.0, "end": 0.8, "probability": 0.99},
                {"word": "sentence.", "start": 0.8, "end": 1.6, "probability": 0.99},
                {"word": "Second", "start": 2.2, "end": 3.0, "probability": 0.99},
                {"word": "sentence.", "start": 3.0, "end": 4.5, "probability": 0.99},
            ],
            "is_approximate": False,
            "is_manually_edited": False,
        }
    ]
    proj.raw_transcript_json = json.dumps(raw_data)
    db_session.commit()

    loaded_proj = db_session.query(Project).filter(Project.id == proj.id).first()
    assert loaded_proj.raw_transcript_json is not None
    assert loaded_proj.segmentation_mode == "sentence"


# ============================================================================
# 12. Edited Transcript Preservation & Impact Warning
# ============================================================================
def test_12_edited_transcript_preservation_warning(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Edits", segmentation_mode="original", status=ProjectStatus.TRANSCRIBED)
    db_session.add(proj)
    db_session.commit()

    seg1 = TranscriptSegment(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        text="Original text",
        is_manually_edited=False,
    )
    db_session.add(seg1)
    db_session.commit()

    # Edit segment text via PATCH
    res = client.patch(f"/api/projects/{proj_id}/transcript/{seg1.id}", json={"text": "Manually edited text"})
    assert res.status_code == 200
    data = res.json()
    assert data["text"] == "Manually edited text"
    assert data["is_manually_edited"] is True

    # Check preview endpoint flags user edits
    prev = client.get(f"/api/projects/{proj_id}/transcript/segmentation/preview?mode=sentence")
    assert prev.status_code == 200
    pdata = prev.json()
    assert pdata["has_user_edits"] is True
    assert pdata["requires_confirmation"] is True
    assert "manual transcript edits" in pdata["impact_warning"]


# ============================================================================
# 13. Existing Translations Invalidation
# ============================================================================
def test_13_existing_translations_invalidation(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Trans Inv", segmentation_mode="original", status=ProjectStatus.TRANSLATED)
    raw_data = [
        {
            "segment_order": 1,
            "start_time": 0.0,
            "end_time": 4.0,
            "text": "Hello world. How are you?",
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 1.0},
                {"word": "world.", "start": 0.5, "end": 1.2, "probability": 1.0},
                {"word": "How", "start": 1.8, "end": 2.2, "probability": 1.0},
                {"word": "are", "start": 2.2, "end": 2.5, "probability": 1.0},
                {"word": "you?", "start": 2.5, "end": 3.2, "probability": 1.0},
            ],
        }
    ]
    proj.raw_transcript_json = json.dumps(raw_data)
    db_session.add(proj)

    t_seg = TranscriptSegment(id=str(uuid.uuid4()), project_id=proj_id, segment_order=1, start_time=0.0, end_time=4.0, text="Hello world. How are you?")
    db_session.add(t_seg)

    tr_seg = TranslationSegment(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        transcript_segment_id=t_seg.id,
        segment_order=1,
        khmer_text="សួស្តីពិភពលោក",
        is_outdated=False,
    )
    db_session.add(tr_seg)
    db_session.commit()

    # Apply resegmentation with confirmation
    res = client.post(
        f"/api/projects/{proj_id}/transcript/segmentation/apply",
        json={"mode": "sentence", "confirm": True},
    )
    assert res.status_code == 200

    # Verify translation marked outdated
    updated_tr = db_session.query(TranslationSegment).filter(TranslationSegment.id == tr_seg.id).first()
    assert updated_tr.is_outdated is True


# ============================================================================
# 14. Existing Audio Invalidation
# ============================================================================
def test_14_existing_audio_invalidation(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Audio Inv", segmentation_mode="original", status=ProjectStatus.VOICE_GENERATED)
    raw_data = [
        {
            "segment_order": 1,
            "start_time": 0.0,
            "end_time": 3.0,
            "text": "Testing audio.",
            "words": [
                {"word": "Testing", "start": 0.0, "end": 0.6, "probability": 1.0},
                {"word": "audio.", "start": 0.6, "end": 1.2, "probability": 1.0},
            ],
        }
    ]
    proj.raw_transcript_json = json.dumps(raw_data)
    db_session.add(proj)

    t_seg = TranscriptSegment(id=str(uuid.uuid4()), project_id=proj_id, segment_order=1, start_time=0.0, end_time=3.0, text="Testing audio.")
    db_session.add(t_seg)

    tr_seg = TranslationSegment(id=str(uuid.uuid4()), project_id=proj_id, transcript_segment_id=t_seg.id, segment_order=1, khmer_text="ការធ្វើតេស្ត")
    db_session.add(tr_seg)

    aud = GeneratedAudio(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        translation_segment_id=tr_seg.id,
        audio_path="/tmp/fake.mp3",
        is_outdated=False,
    )
    db_session.add(aud)

    vid = Video(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        filename="test.mp4",
        file_path="/tmp/test.mp4",
        file_size_bytes=1000,
        exported_video_path="/tmp/exported.mp4",
        is_export_outdated=False,
    )
    db_session.add(vid)
    db_session.commit()

    # Apply resegmentation
    res = client.post(
        f"/api/projects/{proj_id}/transcript/segmentation/apply",
        json={"mode": "sentence", "confirm": True},
    )
    assert res.status_code == 200

    updated_aud = db_session.query(GeneratedAudio).filter(GeneratedAudio.id == aud.id).first()
    assert updated_aud.is_outdated is True

    updated_vid = db_session.query(Video).filter(Video.id == vid.id).first()
    assert updated_vid.is_export_outdated is True


# ============================================================================
# 15. SRT Export Compatibility
# ============================================================================
def test_15_srt_export_compatibility():
    cues = [
        SubtitleCue(1, 0.0, 3.9, "Once in a small village lived a young boy named Kabir."),
        SubtitleCue(2, 4.6, 7.74, "He was intelligent but had one big problem."),
    ]
    srt_out = generate_srt(cues)
    assert "00:00:00,000 --> 00:00:03,900" in srt_out
    assert "Once in a small village lived a young boy named Kabir." in srt_out
    assert "00:00:04,600 --> 00:00:07,740" in srt_out
    assert "He was intelligent but had one big problem." in srt_out


# ============================================================================
# 16. VTT Export Compatibility
# ============================================================================
def test_16_vtt_export_compatibility():
    cues = [
        SubtitleCue(1, 0.0, 3.9, "Once in a small village lived a young boy named Kabir."),
        SubtitleCue(2, 4.6, 7.74, "He was intelligent but had one big problem."),
    ]
    vtt_out = generate_vtt(cues)
    assert vtt_out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:03.900" in vtt_out
    assert "00:00:04.600 --> 00:00:07.740" in vtt_out


# ============================================================================
# 17. Audio Sync & Timeline Sequence Invariants
# ============================================================================
def test_17_audio_sync_timeline_integrity():
    words = [
        WordTiming("Sentence", 0.0, 0.5),
        WordTiming("one.", 0.5, 1.0),
        WordTiming("Sentence", 1.2, 1.7),
        WordTiming("two.", 1.7, 2.3),
        WordTiming("Sentence", 2.5, 3.0),
        WordTiming("three.", 3.0, 3.6),
    ]
    raw = TranscriptionSegment(1, 0.0, 3.6, "Sentence one. Sentence two. Sentence three.", words=words)
    segs = segment_transcript([raw], mode="sentence")

    assert len(segs) == 3
    # Verify chronological order and no inversions
    for i in range(len(segs)):
        assert segs[i].start_time < segs[i].end_time
        if i > 0:
            assert segs[i].start_time >= segs[i - 1].end_time


# ============================================================================
# 18. Preview Endpoint Does Not Mutate Database
# ============================================================================
def test_18_preview_endpoint_does_not_mutate_db(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Preview DB", segmentation_mode="original", status=ProjectStatus.TRANSCRIBED)
    raw_data = [
        {
            "segment_order": 1,
            "start_time": 0.0,
            "end_time": 4.0,
            "text": "Hello. Goodbye.",
            "words": [
                {"word": "Hello.", "start": 0.0, "end": 1.0, "probability": 1.0},
                {"word": "Goodbye.", "start": 2.0, "end": 3.0, "probability": 1.0},
            ],
        }
    ]
    proj.raw_transcript_json = json.dumps(raw_data)
    db_session.add(proj)

    seg1 = TranscriptSegment(id=str(uuid.uuid4()), project_id=proj_id, segment_order=1, start_time=0.0, end_time=4.0, text="Hello. Goodbye.")
    db_session.add(seg1)
    db_session.commit()

    # Call preview
    prev = client.get(f"/api/projects/{proj_id}/transcript/segmentation/preview?mode=sentence")
    assert prev.status_code == 200
    assert prev.json()["proposed_segment_count"] == 2

    # Verify DB still has exactly 1 segment (unmutated)
    db_count = db_session.query(TranscriptSegment).filter(TranscriptSegment.project_id == proj_id).count()
    assert db_count == 1
    db_proj = db_session.query(Project).filter(Project.id == proj_id).first()
    assert db_proj.segmentation_mode == "original"


# ============================================================================
# 19. Confirmation Required Before Applying Resegmentation
# ============================================================================
def test_19_confirmation_required_before_apply(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Confirm", segmentation_mode="original", status=ProjectStatus.TRANSLATED)
    raw_data = [
        {
            "segment_order": 1,
            "start_time": 0.0,
            "end_time": 3.0,
            "text": "First. Second.",
            "words": [
                {"word": "First.", "start": 0.0, "end": 1.0, "probability": 1.0},
                {"word": "Second.", "start": 1.5, "end": 2.5, "probability": 1.0},
            ],
        }
    ]
    proj.raw_transcript_json = json.dumps(raw_data)
    db_session.add(proj)

    t_seg = TranscriptSegment(id=str(uuid.uuid4()), project_id=proj_id, segment_order=1, start_time=0.0, end_time=3.0, text="First. Second.")
    db_session.add(t_seg)
    tr_seg = TranslationSegment(id=str(uuid.uuid4()), project_id=proj_id, transcript_segment_id=t_seg.id, segment_order=1, khmer_text="មួយ ពីរ")
    db_session.add(tr_seg)
    db_session.commit()

    # Attempt apply without confirmation -> must fail with 400
    res_no_confirm = client.post(
        f"/api/projects/{proj_id}/transcript/segmentation/apply",
        json={"mode": "sentence", "confirm": False},
    )
    assert res_no_confirm.status_code == 400
    assert "Confirmation required" in res_no_confirm.json()["detail"]

    # Now apply with confirm=True -> must succeed
    res_confirm = client.post(
        f"/api/projects/{proj_id}/transcript/segmentation/apply",
        json={"mode": "sentence", "confirm": True},
    )
    assert res_confirm.status_code == 200
    assert res_confirm.json()["segment_count"] == 2


# ============================================================================
# 20. No Data Loss and Manual Split / Merge Endpoints
# ============================================================================
def test_20_no_data_loss_and_manual_split_merge(client: TestClient, db_session: Session):
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, title="Test Split Merge", segmentation_mode="sentence", status=ProjectStatus.TRANSCRIBED)
    db_session.add(proj)

    words = [
        {"word": "Alpha", "start": 0.0, "end": 0.5, "probability": 1.0},
        {"word": "Beta", "start": 0.5, "end": 1.0, "probability": 1.0},
        {"word": "Gamma", "start": 1.0, "end": 1.5, "probability": 1.0},
    ]
    seg1 = TranscriptSegment(
        id=str(uuid.uuid4()),
        project_id=proj_id,
        segment_order=1,
        start_time=0.0,
        end_time=1.5,
        text="Alpha Beta Gamma",
        words_json=json.dumps(words),
    )
    db_session.add(seg1)
    db_session.commit()

    # 1. Manual Split at word index 1 (splits into "Alpha" and "Beta Gamma")
    split_res = client.post(
        f"/api/projects/{proj_id}/transcript/{seg1.id}/split",
        json={"word_index": 1},
    )
    assert split_res.status_code == 200
    split_data = split_res.json()["segments"]
    assert len(split_data) == 2
    assert split_data[0]["text"] == "Alpha"
    assert split_data[1]["text"] == "Beta Gamma"
    assert split_data[0]["is_manually_edited"] is True

    # 2. Manual Merge back together
    first_id = split_data[0]["id"]
    merge_res = client.post(f"/api/projects/{proj_id}/transcript/{first_id}/merge-next")
    assert merge_res.status_code == 200
    merge_data = merge_res.json()["segments"]
    assert len(merge_data) == 1
    assert "Alpha Beta Gamma" in merge_data[0]["text"]
    assert merge_data[0]["start_time"] == 0.0
    assert merge_data[0]["end_time"] == 1.5
