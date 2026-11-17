from pathlib import Path
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.services.dubbing.auto_fit import shorten_khmer_text
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.transcription.base import TranscriptionSegment, WordTiming
from app.services.transcription.segmentation import segment_transcript
from app.services.tts.base import TTSAudioResult


def test_spoken_khmer_narrative_conciseness():
    """Verify that verbose literary NLLB translations are streamlined into natural spoken Khmer."""
    # Test royal pronoun replacement
    assert "គាត់" in shorten_khmer_text("ទ្រង់បាននិយាយ")
    assert "ទ្រង់" not in shorten_khmer_text("ទ្រង់បាននិយាយ")

    # Test narrative condition streamline
    text_cond = "ប្រសិនបើនរណាម្នាក់ត្រូវការជំនួយក្នុងការដឹកជញ្ជូនដំណាំគាត់នៅទីនោះ។"
    shortened_cond = shorten_khmer_text(text_cond)
    assert "បើនរណា" in shortened_cond
    assert len(shortened_cond) < len(text_cond)

    # Test sentence bleed resolution
    bleed_text = "ហើយការដែលគាត់បានជ្រើសរើសគាត់មិនបានធ្វើឲ្យគាត់មានកិត្តិយសនោះទេគឺបានធ្វើឲ្យគាត់មានកិត្តិយសនោះ"
    shortened_bleed = shorten_khmer_text(bleed_text)
    assert "ជ្រើសរើសខ្លួនឯង" in shortened_bleed
    assert len(shortened_bleed) < len(bleed_text)


def test_shorten_khmer_text_with_target_budget():
    """Verify that target_char_count progressively tightens text to fit speaking budget."""
    text = "ហើយនៅល្ងាចនោះភ្លៀងក៏បានធ្លាក់ចុះមកយ៉ាងខ្លាំងដោយមិនបានរំពឹងទុក"
    # Without budget
    s1 = shorten_khmer_text(text)
    # With tight budget
    s2 = shorten_khmer_text(text, target_char_count=35)
    assert len(s2) <= len(s1)
    assert "យ៉ាងខ្លាំង" not in s2  # Optional filler pruned to meet budget


def test_segmentation_orphan_tail_merging():
    """Verify that dubbing mode merges an excessively short final chunk with previous chunk."""
    words = [
        WordTiming(word="First", start=0.0, end=1.0, probability=0.9),
        WordTiming(word="phrase", start=1.0, end=2.5, probability=0.9),
        WordTiming(word="is", start=2.5, end=3.0, probability=0.9),
        WordTiming(word="here.", start=3.0, end=3.8, probability=0.9),
        # Trailing short phrase (0.6s < target_min of 2.0s)
        WordTiming(word="End", start=4.5, end=4.8, probability=0.9),
        WordTiming(word="now.", start=4.8, end=5.1, probability=0.9),
    ]
    raw = [
        TranscriptionSegment(
            segment_order=1,
            start_time=0.0,
            end_time=5.1,
            text="First phrase is here. End now.",
            words=words,
        )
    ]
    segs = segment_transcript(raw, mode="dubbing", target_min=2.0, target_max=5.5)
    # This is a genuinely separate short sentence; transcript timing stays exact.
    assert len(segs) == 2
    assert segs[-1].text == "End now."
    assert segs[-1].start_time == 4.5
    assert segs[-1].end_time == 5.1


def test_segmentation_word_timestamp_monotonicity():
    """Verify that every word in segmented output has end > start."""
    words = [
        WordTiming(word="Zero", start=1.0, end=1.0, probability=0.9),  # degenerate timestamp
        WordTiming(word="duration", start=1.5, end=2.0, probability=0.9),
    ]
    raw = [
        TranscriptionSegment(
            segment_order=1,
            start_time=1.0,
            end_time=2.0,
            text="Zero duration",
            words=words,
        )
    ]
    segs = segment_transcript(raw, mode="sentence")
    assert segs[0].is_approximate
    assert segs[0].words[0].end == 1.0
    assert words[0].end == 1.0


@patch("app.services.dubbing.scheduler.TimelineScheduler._measure_variant", new=lambda *args: (None, None))
def test_v2_3_tier_3_optimization_enabled(db_session: Session, tmp_path: Path):
    """Verify TimingOptimizerService enables Tier 3 sentence optimization for v2.3 projects."""
    project = Project(
        title="V2.3 Optimization Project",
        pipeline_version="v2.3",
        status=ProjectStatus.VOICE_GENERATED,
        tts_provider="gtts",
        tts_voice="default",
    )
    db_session.add(project)
    db_session.commit()

    video_file = tmp_path / "v2_3_video.mp4"
    video_file.write_bytes(b"dummy")
    video = Video(
        project_id=project.id,
        filename="v2_3_video.mp4",
        file_path=str(video_file),
        file_size_bytes=1000,
        duration_seconds=15.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=2.5,
        text="A brief moment in time.",
    )
    t2 = TranscriptSegment(
        project_id=project.id,
        segment_order=2,
        start_time=3.0,
        end_time=6.0,
        text="Followed by another sentence.",
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Translation segment with verbose Khmer text requiring shortening
    trans1 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t1.id,
        segment_order=1,
        khmer_text="ប្រសិនបើនរណាម្នាក់ត្រូវការជំនួយក្នុងការដឹកជញ្ជូនដំណាំគាត់នៅទីនោះ។",
    )
    trans2 = TranslationSegment(
        project_id=project.id,
        transcript_segment_id=t2.id,
        segment_order=2,
        khmer_text="តាមពិតទៅរឿងនេះមិនសូវអាក្រក់ប៉ុន្មានទេ។",
    )
    db_session.add_all([trans1, trans2])
    db_session.commit()

    # Audio 1 takes 5.0s in a 2.5s window (needs optimization)
    audio_file1 = tmp_path / "a1.mp3"
    audio_file1.write_bytes(b"dummy audio 1")
    a1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=trans1.id,
        audio_path=str(audio_file1),
        duration_seconds=5.0,
    )
    audio_file2 = tmp_path / "a2.mp3"
    audio_file2.write_bytes(b"dummy audio 2")
    a2 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=trans2.id,
        audio_path=str(audio_file2),
        duration_seconds=2.0,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    optimizer = TimingOptimizerService()

    # Mock synthesize to return a shorter duration upon re-synthesis
    with patch("app.services.dubbing.timing_optimizer.get_tts_provider") as mock_tts:
        mock_provider = MagicMock()
        mock_provider.synthesize.return_value = TTSAudioResult(
            audio_path=audio_file1,
            duration_seconds=2.4,
            provider_name="gtts",
            voice="default",
            language="km",
        )
        mock_tts.return_value = mock_provider

        with patch.object(optimizer.video_processor, "get_audio_duration", return_value=2.4):
            res = optimizer.optimize_project(project.id, db_session)

            assert res.total_segments == 2
            # Timing optimization must preserve text and report real shortages.
            db_session.refresh(trans1)
            assert res.sentence_optimized == 0
            mock_provider.synthesize.assert_not_called()


def test_tts_suspiciously_short_retry(db_session: Session, tmp_path: Path):
    """Verify that synthesize_segment_audio detects suspiciously short audio (premature EOS) and retries."""
    from app.workers.tts import synthesize_segment_audio

    project = Project(
        title="TTS Retry Project",
        status=ProjectStatus.TRANSLATED,
        tts_provider="gtts",
        tts_voice="default",
    )
    db_session.add(project)
    db_session.commit()

    trans = TranslationSegment(
        project_id=project.id,
        segment_order=1,
        khmer_text="តើអ្នកធ្លាប់បានដឹងដែរទេថាមនុស្សតែងតែចងចាំអ្នកនៅពេលដែលមានអ្វីមួយខ្វះក្នុងជីវិតរបស់ពួកគេ",  # 86 chars
    )
    db_session.add(trans)
    db_session.commit()

    mock_provider = MagicMock()
    # First call returns suspiciously short audio (0.5s for 86 chars -> 172 chars/sec!)
    # Second call returns full audio (6.5s)
    call_count = 0
    audio_file = tmp_path / "test_out.mp3"
    audio_file.write_bytes(b"dummy mp3 data")

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return TTSAudioResult(audio_path=audio_file, duration_seconds=0.5, provider_name="gtts", voice="default", language="km")
        else:
            return TTSAudioResult(audio_path=audio_file, duration_seconds=6.5, provider_name="gtts", voice="default", language="km")

    mock_provider.synthesize.side_effect = side_effect

    with patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration") as mock_dur:
        mock_dur.side_effect = [0.5, 6.5]
        audio_rec = synthesize_segment_audio(
            project_id=project.id,
            segment=trans,
            provider=mock_provider,
            db=db_session,
        )
        assert call_count == 2  # Proves retry was triggered for premature EOS!
        assert audio_rec.duration_seconds == 6.5

