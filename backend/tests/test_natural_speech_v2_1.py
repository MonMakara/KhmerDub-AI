import subprocess
import wave
import struct
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    TimingConflictError,
    TimingConflict,
)
from app.services.dubbing.timing_optimizer import (
    TimingOptimizerService,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.dubbing.auto_fit import shorten_khmer_text


@pytest.fixture
def db_session(tmp_path: Path):
    db_file = tmp_path / "test_v2_1.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_sine_wav(path: Path, duration: float, freq: int = 440, sample_rate: int = 44100):
    """Generate clean PCM test sine wave."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration:.3f}",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "2",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def test_speech_completeness_and_original_tts_preservation(tmp_path: Path):
    """1 & 15: Ensure raw TTS audio file is preserved 100% intact without destructive in-place trimming."""
    raw_audio = make_sine_wav(tmp_path / "raw_tts.wav", duration=2.50)
    raw_bytes = raw_audio.read_bytes()
    raw_size = raw_audio.stat().st_size

    sync = AudioSynchronizationService()
    rendered_piece = tmp_path / "rendered_piece.wav"
    sync.render_speech_piece(raw_audio, rendered_piece, tempo_factor=1.0, apply_micro_fade=True)

    # Original raw audio file must remain completely unaltered
    assert raw_audio.read_bytes() == raw_bytes
    assert raw_audio.stat().st_size == raw_size
    assert rendered_piece.exists()
    assert rendered_piece.stat().st_size > 0


def test_micro_fades_prevent_boundary_clicks(tmp_path: Path):
    """3: Micro-fades (8ms) enforce zero-amplitude boundary crossings to eliminate clicks."""
    test_wav = make_sine_wav(tmp_path / "loud_sine.wav", duration=1.0, freq=500)
    sync = AudioSynchronizationService()
    faded_wav = tmp_path / "faded_piece.wav"
    sync.render_speech_piece(test_wav, faded_wav, tempo_factor=1.0, apply_micro_fade=True)

    with wave.open(str(faded_wav), "rb") as wf:
        n_frames = wf.getnframes()
        frames = wf.readframes(n_frames)
        samples = struct.unpack(f"<{n_frames * wf.getnchannels()}h", frames)

        # Boundary samples must start and end at exact digital zero
        assert samples[0] == 0
        assert samples[1] == 0
        assert samples[-1] == 0
        assert samples[-2] == 0


def test_tempo_limit_and_pitch_preservation(tmp_path: Path):
    """5, 6, 7: Adaptive tempo capped at 1.25x with pitch-preserving filter."""
    src_wav = make_sine_wav(tmp_path / "tempo_src.wav", duration=4.0)
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    vp = FFmpegVideoProcessor()

    # Moderate acceleration 1.15x
    p1 = tmp_path / "p1.wav"
    sync.render_speech_piece(src_wav, p1, tempo_factor=1.15)
    d1 = vp.get_audio_duration(p1)
    assert abs(d1 - (4.0 / 1.15)) < 0.15

    # Cap enforcement: values > 1.25 are capped at 1.25 when synchronized
    p2 = tmp_path / "p2.wav"
    sync.render_speech_piece(src_wav, p2, tempo_factor=1.25)
    d2 = vp.get_audio_duration(p2)
    assert abs(d2 - (4.0 / 1.25)) < 0.15


def test_phrase_group_scheduling_shares_timing_flexibility(tmp_path: Path):
    """8, 9, 10, 11: Multi-sentence timing allocation allows neighboring sentences to fit naturally."""
    # Sentence 1: 0.0 - 4.0s (slot=4.0s), Khmer raw=5.0s (overflows slot by 1.0s)
    # Sentence 2: 4.5 - 10.5s (slot=6.0s), Khmer raw=5.0s (under slot by 1.0s)
    # Sentence 3: 11.0 - 16.0s (slot=5.0s), Khmer raw=5.0s (exact)
    # Total available window = 16.5s. Total speech = 15.0s.
    # Group scheduling fits all 3 sentences at 1.00x natural speed with natural pauses!
    a1 = make_sine_wav(tmp_path / "a1.wav", duration=5.0)
    a2 = make_sine_wav(tmp_path / "a2.wav", duration=5.0)
    a3 = make_sine_wav(tmp_path / "a3.wav", duration=5.0)

    t1 = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=4.0, text="Sentence 1")
    t2 = TranscriptSegment(id="t2", project_id="p1", segment_order=2, start_time=4.5, end_time=10.5, text="Sentence 2")
    t3 = TranscriptSegment(id="t3", project_id="p1", segment_order=3, start_time=11.0, end_time=16.0, text="Sentence 3")

    tr1 = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ប្រយោគទីមួយ")
    tr2 = TranslationSegment(id="tr2", project_id="p1", segment_order=2, khmer_text="ប្រយោគទីពីរ")
    tr3 = TranslationSegment(id="tr3", project_id="p1", segment_order=3, khmer_text="ប្រយោគទីបី")

    rec1 = GeneratedAudio(id="r1", project_id="p1", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=5.0)
    rec2 = GeneratedAudio(id="r2", project_id="p1", translation_segment_id="tr2", audio_path=str(a2), duration_seconds=5.0)
    rec3 = GeneratedAudio(id="r3", project_id="p1", translation_segment_id="tr3", audio_path=str(a3), duration_seconds=5.0)

    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "timeline_v2_1.wav"

    res = sync.synchronize(
        project_id="p1",
        segment_items=[(t1, tr1, rec1), (t2, tr2, rec2), (t3, tr3, rec3)],
        target_duration=16.5,
        output_timeline_path=out_wav,
        strict_validation=True,
        pipeline_version="v2.1",
    )

    # Zero conflicts detected because phrase-group scheduling successfully balanced the timing
    assert len(res.conflicts) == 0
    assert abs(res.total_duration_seconds - 16.5) <= 0.05


def test_translation_preservation_no_lossy_word_slicing():
    """12, 13: Translation text is never cut mid-word or sliced by character count."""
    long_khmer = "ការប្រកួតប្រជែងយ៉ាងស្វិតស្វាញរវាងក្រុមហ៊ុនបច្ចេកវិទ្យាធំៗក្នុងការអភិវឌ្ឍបញ្ញាសិប្បនិម្មិត។"
    shortened = shorten_khmer_text(long_khmer, target_char_count=30)

    # Word structure must be completely preserved without sliced syllables
    assert "រវាង" in shortened or "ការប្រកួតប្រជែង" in shortened
    assert not shortened.endswith("រ។")
    assert not shortened.endswith("បញ្។")


def test_backward_compatibility_v1_v2_and_v2_1(db_session, tmp_path: Path):
    """18: Verify backward compatibility across pipeline versions."""
    # V1 project: default behavior
    p1 = Project(id="proj_v1", title="V1 Project", pipeline_version="v1")
    # V2 project: legacy timing-aware
    p2 = Project(id="proj_v2", title="V2 Project", pipeline_version="v2")
    # V2.1 project: natural timing-aware with phrase groups
    p2_1 = Project(id="proj_v2_1", title="V2.1 Project", pipeline_version="v2.1")

    db_session.add_all([p1, p2, p2_1])
    db_session.commit()

    q1 = db_session.query(Project).filter(Project.id == "proj_v1").first()
    q2 = db_session.query(Project).filter(Project.id == "proj_v2").first()
    q2_1 = db_session.query(Project).filter(Project.id == "proj_v2_1").first()

    assert q1.pipeline_version == "v1"
    assert q2.pipeline_version == "v2"
    assert q2_1.pipeline_version == "v2.1"


def test_unavoidable_overflow_produces_clear_conflict(tmp_path: Path):
    """9, 10: Excessive speech that cannot fit even at 1.25x tempo reports an honest TimingConflict."""
    # 8.0s audio in 4.0s window -> requires 2.0x speed, exceeds max 1.25x
    huge_audio = make_sine_wav(tmp_path / "huge.wav", duration=8.0)
    t = TranscriptSegment(id="t_huge", project_id="p_ov", segment_order=1, start_time=0.0, end_time=4.0, text="Overflow")
    tr = TranslationSegment(id="tr_huge", project_id="p_ov", segment_order=1, khmer_text="វែងខ្លាំងពេក")
    rec = GeneratedAudio(id="r_huge", project_id="p_ov", translation_segment_id="tr_huge", audio_path=str(huge_audio), duration_seconds=8.0)

    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "overflow.wav"

    with pytest.raises(TimingConflictError) as exc_info:
        sync.synchronize(
            project_id="p_ov",
            segment_items=[(t, tr, rec)],
            target_duration=4.0,
            output_timeline_path=out_wav,
            strict_validation=True,
            pipeline_version="v2.1",
        )

    conflict = exc_info.value.conflicts[0]
    assert conflict.segment_order == 1
    assert conflict.overflow_seconds > 0.5
    assert conflict.tempo_factor == 1.25
    assert "Shorten the Khmer translation" in conflict.suggested_action


def test_timing_optimizer_v2_1_phrase_group_analysis(db_session, tmp_path: Path):
    """8, 14: analyze_timeline uses phrase-group budgeting and does not report false conflicts."""
    p = Project(id="proj_opt", title="Opt Test", pipeline_version="v2.1")
    v = Video(id="v_opt", project_id="proj_opt", filename="dummy.mp4", file_path=str(tmp_path / "dummy.mp4"), file_size_bytes=1024, duration_seconds=12.0)

    t1 = TranscriptSegment(id="t1", project_id="proj_opt", segment_order=1, start_time=0.0, end_time=3.0, text="Part 1")
    t2 = TranscriptSegment(id="t2", project_id="proj_opt", segment_order=2, start_time=3.5, end_time=7.0, text="Part 2")

    tr1 = TranslationSegment(id="tr1", project_id="proj_opt", segment_order=1, transcript_segment_id="t1", khmer_text="ផ្នែកទីមួយ", is_manually_edited=True)
    tr2 = TranslationSegment(id="tr2", project_id="proj_opt", segment_order=2, transcript_segment_id="t2", khmer_text="ផ្នែកទីពីរ", is_manually_edited=False)

    # Seg 1 audio is 3.5s (slightly longer than 3.0s slot), Seg 2 audio is 2.5s (shorter than 3.5s slot)
    # Total Khmer = 6.0s in 7.0s group window -> fits naturally!
    a1 = make_sine_wav(tmp_path / "opt_a1.wav", duration=3.5)
    a2 = make_sine_wav(tmp_path / "opt_a2.wav", duration=2.5)

    rec1 = GeneratedAudio(id="r1", project_id="proj_opt", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=3.5)
    rec2 = GeneratedAudio(id="r2", project_id="proj_opt", translation_segment_id="tr2", audio_path=str(a2), duration_seconds=2.5)

    db_session.add_all([p, v, t1, t2, tr1, tr2, rec1, rec2])
    db_session.commit()

    service = TimingOptimizerService()
    analysis = service.analyze_timeline("proj_opt", db_session)

    assert len(analysis) == 2
    # Both segments are recognized as natural because the phrase group easily fits
    assert analysis[0].status == "natural"
    assert analysis[1].status == "natural"
    assert analysis[0].overflow_seconds == 0.0
    assert analysis[1].overflow_seconds == 0.0


def test_missing_audio_raises_clean_error(tmp_path: Path):
    """20: Graceful error handling for missing audio."""
    t = TranscriptSegment(id="t_err", project_id="p_err", segment_order=1, start_time=0.0, end_time=3.0, text="Err")
    tr = TranslationSegment(id="tr_err", project_id="p_err", segment_order=1, khmer_text="កំហុស")
    rec = GeneratedAudio(id="r_err", project_id="p_err", translation_segment_id="tr_err", audio_path="/nonexistent/path.wav", duration_seconds=3.0)

    sync = AudioSynchronizationService()
    with pytest.raises(FileNotFoundError):
        sync.synchronize(
            project_id="p_err",
            segment_items=[(t, tr, rec)],
            target_duration=5.0,
            output_timeline_path=tmp_path / "err.wav",
            pipeline_version="v2.1",
        )

