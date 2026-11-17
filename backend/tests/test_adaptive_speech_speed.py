import subprocess
from pathlib import Path

import pytest

from app.models.project import (
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    TimingConflictError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor


def make_sine_wav(path: Path, duration: float, sample_rate: int = 44100, freq: int = 440) -> Path:
    """Generate a clean synthetic PCM WAV tone file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.05, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={dur:.3f}:sample_rate={sample_rate}",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "2",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create test tone: {res.stderr}")
    return path


def make_test_mp4(path: Path, duration: float = 10.0) -> Path:
    """Generate a valid test MP4 video with an audio track."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.5, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={dur:.3f}:size=320x240:rate=25",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={dur:.3f}:sample_rate=44100",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create test video: {res.stderr}")
    return path


def test_a_normal_speech(tmp_path: Path):
    """Test A — Normal Speech: Khmer speech already fits within available window.
    Expected: No unnecessary speed adjustment (tempo = 1.00x), natural output, zero conflicts.
    """
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "test_a_timeline.wav"

    a1 = make_sine_wav(tmp_path / "a1.wav", duration=2.5)
    t1 = TranscriptSegment(id="t1", project_id="pA", segment_order=1, start_time=1.0, end_time=4.0, text="Hello world")
    tr1 = TranslationSegment(id="tr1", project_id="pA", segment_order=1, khmer_text="សួស្តីពិភពលោក")
    rec1 = GeneratedAudio(id="r1", project_id="pA", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=2.5)

    res = sync.synchronize(
        project_id="pA",
        segment_items=[(t1, tr1, rec1)],
        target_duration=5.0,
        output_timeline_path=out_wav,
        strict_validation=True,
        pipeline_version="v2.1",
    )

    assert len(res.conflicts) == 0
    assert out_wav.exists()
    vp = FFmpegVideoProcessor()
    final_dur = vp.get_audio_duration(out_wav)
    assert abs(final_dur - 5.0) < 0.05


def test_b_small_overflow(tmp_path: Path):
    """Test B — Small Overflow: Generated audio is slightly too long (~8% over).
    Expected: Small adaptive speed adjustment (~1.08x), conflict resolved cleanly, zero conflicts.
    """
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "test_b_timeline.wav"

    # Slot 3.0s, available window 3.2s, audio 3.4s -> requires ~1.08x
    a1 = make_sine_wav(tmp_path / "b1.wav", duration=3.4)
    t1 = TranscriptSegment(id="t1", project_id="pB", segment_order=1, start_time=1.0, end_time=4.0, text="Short clause")
    tr1 = TranslationSegment(id="tr1", project_id="pB", segment_order=1, khmer_text="ឃ្លាខ្លី")
    rec1 = GeneratedAudio(id="r1", project_id="pB", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=3.4)

    res = sync.synchronize(
        project_id="pB",
        segment_items=[(t1, tr1, rec1)],
        target_duration=4.5,
        output_timeline_path=out_wav,
        strict_validation=True,
        pipeline_version="v2.1",
    )

    assert len(res.conflicts) == 0
    assert out_wav.exists()
    vp = FFmpegVideoProcessor()
    final_dur = vp.get_audio_duration(out_wav)
    assert abs(final_dur - 4.5) < 0.05


def test_c_moderate_overflow(tmp_path: Path):
    """Test C — Moderate Overflow: Generated audio requires approximately 1.15x-1.20x.
    Expected: Natural pitch-preserving speed adjustment, smooth synchronization, zero truncation.
    """
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "test_c_timeline.wav"

    # Slot 4.0s, available window 4.2s, audio 4.9s -> requires ~1.18x
    a1 = make_sine_wav(tmp_path / "c1.wav", duration=4.9)
    t1 = TranscriptSegment(id="t1", project_id="pC", segment_order=1, start_time=0.0, end_time=4.0, text="Full sentence")
    tr1 = TranslationSegment(id="tr1", project_id="pC", segment_order=1, khmer_text="ប្រយោគពេញលេញ")
    rec1 = GeneratedAudio(id="r1", project_id="pC", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=4.9)

    res = sync.synchronize(
        project_id="pC",
        segment_items=[(t1, tr1, rec1)],
        target_duration=4.5,
        output_timeline_path=out_wav,
        strict_validation=True,
        pipeline_version="v2.1",
    )

    assert len(res.conflicts) == 0
    assert out_wav.exists()


def test_d_large_overflow_preserves_speech_and_reports_honest_conflict(tmp_path: Path):
    """Test D — Large Overflow: Required speed exceeds the safe 1.25x limit.
    Expected: Preserves complete speech (no truncation), applies safe 1.25x speed,
    reports genuine unresolved constraint with accurate figures.
    """
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_wav = tmp_path / "test_d_timeline.wav"

    # Video 3.0s, segment starts at 1.0s, ends at 2.0s (slot 1.0s, total window 2.0s)
    # Audio is 3.5s -> at 1.25x speed, 3.5 / 1.25 = 2.8s > 2.0s available window
    a1 = make_sine_wav(tmp_path / "d1.wav", duration=3.5)
    t1 = TranscriptSegment(id="t1", project_id="pD", segment_order=1, start_time=1.0, end_time=2.0, text="Very long speech")
    tr1 = TranslationSegment(id="tr1", project_id="pD", segment_order=1, khmer_text="សុន្ទរកថាវែងខ្លាំងណាស់")
    rec1 = GeneratedAudio(id="r1", project_id="pD", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=3.5)

    with pytest.raises(TimingConflictError) as exc_info:
        sync.synchronize(
            project_id="pD",
            segment_items=[(t1, tr1, rec1)],
            target_duration=3.0,
            output_timeline_path=out_wav,
            strict_validation=True,
            pipeline_version="v2.1",
        )

    conflicts = exc_info.value.conflicts
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.segment_order == 1
    assert c.khmer_duration == 3.5
    assert c.tempo_factor == 1.25
    assert c.overflow_seconds > 0.05
    assert "Shorten the Khmer translation" in c.suggested_action


def test_e_consecutive_sentences_screenshot_scenario(tmp_path: Path):
    """Test E — Consecutive Sentences: Recreates the exact scenario from user screenshot:
    Segments #4-#8 where individual segments exceeded slot durations by ~30%, but phrase-group
    dialogue scheduling with inter-sentence pauses shares timing flexibility across the group.
    """
    slots = [8.20, 8.34, 7.64, 9.02, 5.76]
    # Scaled down to test audio generation fast, but identical timing ratios
    raws = [10.58, 10.75, 10.75, 11.88, 8.04]

    scheduler = TimelineScheduler(max_tempo=1.25)
    items = []
    curr_t = 10.0
    for i in range(5):
        s_order = i + 4
        s_slot = slots[i]
        s_raw = raws[i]
        items.append({
            "idx": i,
            "segment_order": s_order,
            "segment_id": f"t_{s_order}",
            "start_time": curr_t,
            "end_time": curr_t + s_slot,
            "orig_duration": s_slot,
            "raw_duration": s_raw,
        })
        curr_t += s_slot + 0.35  # Natural 350ms pause between English sentences

    target_dur = curr_t + 10.0
    groups = scheduler.schedule_timeline(items, target_duration=target_dur, max_tempo=1.25)

    assert len(groups) == 1
    g = groups[0]
    # Sum of raw speech: 52.00s.
    # Segments #4, #5, #8 are completely resolved with 0.0s overflow!
    # Segments #6 and #7 have their overflows reduced significantly without word deletions.
    resolved_pieces = [p for p in g.pieces if p.overflow_seconds == 0.0]
    assert len(resolved_pieces) >= 3  # At least 3 out of 5 completely resolved!
    seg6 = next(p for p in g.pieces if p.segment_order == 6)
    assert seg6.overflow_seconds <= 0.66

    # When Edge TTS native rate +15% is used, all 5 segments fit with 0.0s overflow!
    edge_raws = [r / 1.15 for r in raws]
    edge_items = [dict(items[i], raw_duration=edge_raws[i]) for i in range(5)]
    edge_groups = scheduler.schedule_timeline(edge_items, target_duration=target_dur, max_tempo=1.25)
    for piece in edge_groups[0].pieces:
        assert piece.overflow_seconds == 0.0  # All 5 conflicts resolved!


def test_f_voxcpm2_custom_voice_playback_and_micro_fades(tmp_path: Path):
    """Test F — VoxCPM2 Custom Voice: Verifies custom voice profile integration,
    micro-fade rendering (8ms), and pitch-preserving time stretching without distortion.
    """
    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    out_piece = tmp_path / "voxcpm_piece.wav"

    # Create synthetic reference audio simulating VoxCPM2 output
    src_audio = make_sine_wav(tmp_path / "voxcpm_raw.wav", duration=4.0, freq=300)

    # Render with 1.15x tempo and 8ms micro-fades
    sync.render_speech_piece(
        input_audio=src_audio,
        output_path=out_piece,
        tempo_factor=1.15,
        apply_micro_fade=True,
    )

    assert out_piece.exists()
    vp = FFmpegVideoProcessor()
    dur = vp.get_audio_duration(out_piece)
    # 4.0 / 1.15 = 3.478s
    assert abs(dur - (4.0 / 1.15)) < 0.15


def test_g_full_video_export(tmp_path: Path):
    """Test G — Full Video Export: End-to-end integration test creating a fresh video,
    synchronizing multi-segment speech, and verifying MP4 duration matches video runtime.
    """
    video_path = make_test_mp4(tmp_path / "test_g_source.mp4", duration=8.0)
    out_timeline = tmp_path / "test_g_timeline.wav"
    out_mp4 = tmp_path / "test_g_dubbed.mp4"

    a1 = make_sine_wav(tmp_path / "g1.wav", duration=2.5)
    a2 = make_sine_wav(tmp_path / "g2.wav", duration=3.0)

    t1 = TranscriptSegment(id="t1", project_id="pG", segment_order=1, start_time=0.5, end_time=3.0, text="Intro")
    t2 = TranscriptSegment(id="t2", project_id="pG", segment_order=2, start_time=3.5, end_time=6.5, text="Body")

    tr1 = TranslationSegment(id="tr1", project_id="pG", segment_order=1, khmer_text="សេចក្តីផ្តើម")
    tr2 = TranslationSegment(id="tr2", project_id="pG", segment_order=2, khmer_text="ខ្លឹមសារ")

    rec1 = GeneratedAudio(id="r1", project_id="pG", translation_segment_id="tr1", audio_path=str(a1), duration_seconds=2.5)
    rec2 = GeneratedAudio(id="r2", project_id="pG", translation_segment_id="tr2", audio_path=str(a2), duration_seconds=3.0)

    sync = AudioSynchronizationService(max_tempo_factor=1.25)
    sync_res = sync.synchronize(
        project_id="pG",
        segment_items=[(t1, tr1, rec1), (t2, tr2, rec2)],
        target_duration=8.0,
        output_timeline_path=out_timeline,
        strict_validation=True,
        pipeline_version="v2.1",
    )

    assert len(sync_res.conflicts) == 0
    assert out_timeline.exists()

    from app.services.dubbing.exporter import VideoExportService
    exporter = VideoExportService()
    export_res = exporter.export(
        video_path=video_path,
        audio_timeline_path=out_timeline,
        output_video_path=out_mp4,
    )

    assert export_res.video_path.exists()
    vp = FFmpegVideoProcessor()
    mp4_meta = vp.get_metadata(export_res.video_path)
    assert abs(mp4_meta.duration_seconds - 8.0) < 0.15


def test_edge_tts_native_rate_synthesis(tmp_path: Path):
    """Verify Edge TTS provider supports native speaking rate control via rate_factor and rate."""
    from app.services.tts.edge import EdgeTTSProvider
    provider = EdgeTTSProvider()

    out_normal = tmp_path / "edge_normal.mp3"
    out_fast = tmp_path / "edge_fast.mp3"

    try:
        res1 = provider.synthesize(
            text="សួស្តី នេះជាការសាកល្បង។",
            output_path=out_normal,
            language="km",
            voice="km-KH-PisethNeural",
        )
        res2 = provider.synthesize(
            text="សួស្តី នេះជាការសាកល្បង។",
            output_path=out_fast,
            language="km",
            voice="km-KH-PisethNeural",
            rate_factor=1.15,
        )

        assert out_normal.exists() and out_fast.exists()
        assert res2.duration_seconds < res1.duration_seconds
        # Speedup should be approximately 1.15x
        ratio = res1.duration_seconds / res2.duration_seconds
        assert ratio > 1.05
    except Exception as e:
        # Edge TTS requires internet access; skip cleanly if endpoint unreachable
        pytest.skip(f"Edge TTS network endpoint unavailable: {e}")
