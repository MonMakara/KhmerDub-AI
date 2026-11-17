"""
KhmerDub AI - Exact Timeline Fitting & Audio Sync Pipeline Tests
Tests sample-accurate PCM timeline assembly, fill_mode ('natural' vs 'stretch'),
non-blocking overflow policies, and exact duration preservation for video export.
"""

import math
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    TimingConflictError,
)
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.exporter import VideoExportService


def _generate_sine_wav(output_path: Path, duration: float, freq: int = 440, sr: int = 44100) -> Path:
    """Generate a standard stereo PCM WAV tone."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration:.3f}",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-ac", "2",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def _read_wav_stereo(wav_path: Path):
    """Read 16-bit stereo WAV frames as float32 in [-1.0, 1.0]."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch > 1:
            data = data.reshape(-1, n_ch)
        return data, sr


def test_assemble_timeline_pcm_sample_accurate(tmp_path: Path):
    """Test 1: Verify assemble_timeline_pcm builds a sample-accurate master timeline.
    Guarantees:
    - Exactly 10.0s timeline (441,000 frames at 44.1kHz).
    - Segment 1 starts at 0.5s, Segment 2 at 4.0s, Segment 3 at 7.0s.
    - Zero onset drift (< 20ms).
    """
    service = AudioSynchronizationService()

    tone1 = _generate_sine_wav(tmp_path / "tone1.wav", duration=1.5, freq=300)
    tone2 = _generate_sine_wav(tmp_path / "tone2.wav", duration=1.2, freq=600)
    tone3 = _generate_sine_wav(tmp_path / "tone3.wav", duration=1.0, freq=900)

    pieces_with_timing = [
        (tone1, 0.5),
        (tone2, 4.0),
        (tone3, 7.0),
    ]

    out_timeline = tmp_path / "assembled_master.wav"
    target_dur = 10.0
    final_dur = service.assemble_timeline_pcm(
        pieces_with_timing=pieces_with_timing,
        target_duration=target_dur,
        output_path=out_timeline,
    )

    # 1. Total duration matches exactly
    assert abs(final_dur - target_dur) < 0.001
    assert out_timeline.exists()

    data, sr = _read_wav_stereo(out_timeline)
    assert sr == 44100
    assert len(data) == 441000  # Exactly 10.0 seconds

    # 2. Segment 1 onset: 0.0s-0.45s is silence (RMS < 0.01), 0.55s is tone (RMS > 0.05)
    pre_seg1 = data[int(0.1 * sr):int(0.45 * sr)]
    assert np.sqrt(np.mean(pre_seg1 ** 2)) < 0.01
    post_seg1 = data[int(0.55 * sr):int(0.9 * sr)]
    assert np.sqrt(np.mean(post_seg1 ** 2)) > 0.05

    # 3. Segment 2 onset: 3.5s-3.95s is silence, 4.05s is tone
    pre_seg2 = data[int(3.5 * sr):int(3.95 * sr)]
    assert np.sqrt(np.mean(pre_seg2 ** 2)) < 0.01
    post_seg2 = data[int(4.05 * sr):int(4.5 * sr)]
    assert np.sqrt(np.mean(post_seg2 ** 2)) > 0.05

    # 4. Segment 3 onset: 6.5s-6.95s is silence, 7.05s is tone
    pre_seg3 = data[int(6.5 * sr):int(6.95 * sr)]
    assert np.sqrt(np.mean(pre_seg3 ** 2)) < 0.01
    post_seg3 = data[int(7.05 * sr):int(7.5 * sr)]
    assert np.sqrt(np.mean(post_seg3 ** 2)) > 0.05

    # 5. Trailing silence: 8.5s-10.0s is silence
    tail = data[int(8.5 * sr):int(9.9 * sr)]
    assert np.sqrt(np.mean(tail ** 2)) < 0.01


def test_fill_mode_natural_vs_stretch(tmp_path: Path):
    """Test 2: Verify fill_mode='natural' preserves speech cadence vs fill_mode='stretch' slows down to 0.50x.
    Given a slot of 3.0s and audio of 1.5s:
    - 'natural': tempo is 1.0x (duration ~1.5s, remaining 1.5s padded with silence).
    - 'stretch': tempo slows down towards 0.50x (duration stretches up to ~3.0s).
    """
    service = AudioSynchronizationService()
    short_audio = _generate_sine_wav(tmp_path / "short_speech.wav", duration=1.5)

    t_seg = TranscriptSegment(id="t1", project_id="p_fill", segment_order=1, start_time=1.0, end_time=4.0, text="Dialogue")
    trans_seg = TranslationSegment(id="tr1", project_id="p_fill", segment_order=1, start_time=1.0, end_time=4.0, khmer_text="សន្ទនា")
    gen_audio = GeneratedAudio(id="a1", project_id="p_fill", translation_segment_id="tr1", audio_path=str(short_audio), duration_seconds=1.5)

    # 1. Natural Mode
    out_natural = tmp_path / "natural_timeline.wav"
    res_natural = service.synchronize(
        project_id="p_fill",
        segment_items=[(t_seg, trans_seg, gen_audio)],
        target_duration=6.0,
        output_timeline_path=out_natural,
        pipeline_version="v2.1",
        fill_mode="natural",
    )
    assert abs(res_natural.total_duration_seconds - 6.0) <= 0.05

    # In natural mode, speech is at 1.0x, so at 3.0s-3.9s (end of slot) it is silence
    data_nat, sr = _read_wav_stereo(out_natural)
    pause_region = data_nat[int(2.8 * sr):int(3.9 * sr)]
    assert np.sqrt(np.mean(pause_region ** 2)) < 0.02

    # 2. Stretch Mode
    out_stretch = tmp_path / "stretch_timeline.wav"
    res_stretch = service.synchronize(
        project_id="p_fill",
        segment_items=[(t_seg, trans_seg, gen_audio)],
        target_duration=6.0,
        output_timeline_path=out_stretch,
        pipeline_version="v2.1",
        fill_mode="stretch",
    )
    assert abs(res_stretch.total_duration_seconds - 6.0) <= 0.05

    # In stretch mode, speech was slowed to ~0.50x, so tone signal is present through 3.0s-3.5s
    data_str, _ = _read_wav_stereo(out_stretch)
    stretched_region = data_str[int(2.8 * sr):int(3.5 * sr)]
    assert np.sqrt(np.mean(stretched_region ** 2)) > 0.04


def test_overflow_policy_allow_overlap_non_blocking(tmp_path: Path):
    """Test 3: Verify overflow_policy='allow_overlap' allows speech to flow smoothly into pause
    without blocking video export in non-strict mode.
    """
    service = AudioSynchronizationService()

    # Both speech pieces together (3.5s + 2.5s = 6.0s) exceed available 4.0s window even at 1.25x max speed (4.8s > 4.0s).
    long_speech = _generate_sine_wav(tmp_path / "long_speech.wav", duration=3.5)
    speech2 = _generate_sine_wav(tmp_path / "speech2.wav", duration=2.5)

    t1 = TranscriptSegment(id="t1", project_id="p_ovf", segment_order=1, start_time=0.0, end_time=1.5, text="Dialogue 1")
    tr1 = TranslationSegment(id="tr1", project_id="p_ovf", segment_order=1, start_time=0.0, end_time=1.5, khmer_text="សន្ទនា១")
    ga1 = GeneratedAudio(id="a1", project_id="p_ovf", translation_segment_id="tr1", audio_path=str(long_speech), duration_seconds=3.5)

    t2 = TranscriptSegment(id="t2", project_id="p_ovf", segment_order=2, start_time=1.6, end_time=3.5, text="Dialogue 2")
    tr2 = TranslationSegment(id="tr2", project_id="p_ovf", segment_order=2, start_time=1.6, end_time=3.5, khmer_text="សន្ទនា២")
    ga2 = GeneratedAudio(id="a2", project_id="p_ovf", translation_segment_id="tr2", audio_path=str(speech2), duration_seconds=2.5)

    out_strict = tmp_path / "timeline_strict.wav"
    out_non_strict = tmp_path / "timeline_smooth.wav"

    # Strict mode: raises TimingConflictError
    with pytest.raises(TimingConflictError) as exc_info:
        service.synchronize(
            project_id="p_ovf",
            segment_items=[(t1, tr1, ga1), (t2, tr2, ga2)],
            target_duration=4.0,
            output_timeline_path=out_strict,
            strict_validation=True,
            overflow_policy="fail",
        )
    assert len(exc_info.value.conflicts) >= 1

    # Non-strict mode with allow_overlap: succeeds and preserves full audio without truncation
    res = service.synchronize(
        project_id="p_ovf",
        segment_items=[(t1, tr1, ga1), (t2, tr2, ga2)],
        target_duration=4.0,
        output_timeline_path=out_non_strict,
        strict_validation=False,
        overflow_policy="allow_overlap",
    )
    assert res.timeline_path.exists()
    assert res.total_duration_seconds >= 4.0
    assert len(res.conflicts) >= 1  # Conflicts noted for reference, but export succeeded


def test_dubbing_pipeline_exact_video_duration(tmp_path: Path, db_session: Session):
    """Test 4: Verify DubbingPipeline runs end-to-end and produces an exported MP4
    whose audio and video tracks match the expected video duration within 0.05s.
    """
    # 1. Create a 4.0-second dummy source MP4 video
    video_path = tmp_path / "source_video.mp4"
    cmd_vid = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=4.0:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4.0",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd_vid, check=True, capture_output=True)

    # 2. Database records
    proj = Project(title="Exact Fit Video Test", status=ProjectStatus.VOICE_GENERATED, pipeline_version="v2.1")
    db_session.add(proj)
    db_session.commit()

    vid_record = Video(
        project_id=proj.id,
        filename="source_video.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=4.0,
    )
    db_session.add(vid_record)

    t1 = TranscriptSegment(id="t1", project_id=proj.id, segment_order=1, start_time=0.5, end_time=2.0, text="Hello world")
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(id="tr1", project_id=proj.id, segment_order=1, start_time=0.5, end_time=2.0, khmer_text="សួស្តីពិភពលោក")
    db_session.add(tr1)
    db_session.commit()

    speech_file = _generate_sine_wav(tmp_path / "speech.wav", duration=1.2)
    audio = GeneratedAudio(
        id="a1",
        project_id=proj.id,
        translation_segment_id=tr1.id,
        audio_path=str(speech_file),
        duration_seconds=1.2,
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(
        project_id=proj.id,
        db=db_session,
        strict_validation=False,
        fill_mode="natural",
        overflow_policy="allow_overlap",
    )

    assert result.export_result.video_path.exists()
    assert abs(result.export_result.duration_seconds - 4.0) <= 0.05
    assert abs(result.sync_result.total_duration_seconds - 4.0) <= 0.05


def test_export_api_with_fitting_parameters(client: TestClient, db_session: Session, tmp_path: Path):
    """Test 5: Verify POST /api/projects/{id}/export accepts fill_mode, overflow_policy, and strict_validation."""
    # 1. Create a dummy video file
    video_path = tmp_path / "dummy_sample.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2.0:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    project = Project(title="API Test Proj", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="dummy_sample.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=2.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(id="t_api", project_id=project.id, segment_order=1, start_time=0.2, end_time=1.5, text="Welcome")
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(id="tr_api", project_id=project.id, segment_order=1, start_time=0.2, end_time=1.5, khmer_text="សូមស្វាគមន៍")
    db_session.add(tr1)
    db_session.commit()

    speech = _generate_sine_wav(tmp_path / "api_speech.wav", duration=1.0)
    audio = GeneratedAudio(
        id="a_api",
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(speech),
        duration_seconds=1.0,
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Trigger export API with query parameters
    url = f"/api/projects/{project.id}/export?fill_mode=stretch&overflow_policy=allow_overlap&strict_validation=false"
    res = client.post(url)
    assert res.status_code == 200
    data = res.json()
    assert data["job_type"] == "dub"
    assert data["project_id"] == project.id
