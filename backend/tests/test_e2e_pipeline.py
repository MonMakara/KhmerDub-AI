import json
import subprocess
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.synchronizer import TimingConflictError


def create_synthetic_video(output_path: Path, duration_seconds: float) -> Path:
    """Create a test MP4 video with H.264 video and AAC audio of exact duration."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration_seconds:.2f}:size=320x240:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_seconds:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def create_synthetic_audio(output_path: Path, duration_seconds: float, freq: int = 500) -> Path:
    """Create a test WAV audio file of exact duration."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration_seconds:.3f}",
        "-ar", "44100", "-ac", "2",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def probe_media_streams(file_path: Path) -> dict:
    """Run FFprobe and extract codec names and durations."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,duration:format=duration,size",
        "-of", "json",
        str(file_path),
    ]
    res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(res.stdout)
    v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    return {
        "video_codec": v_stream.get("codec_name") if v_stream else None,
        "video_duration": float(v_stream.get("duration", 0.0)) if v_stream else None,
        "audio_codec": a_stream.get("codec_name") if a_stream else None,
        "audio_duration": float(a_stream.get("duration", 0.0)) if a_stream else None,
        "format_duration": float(fmt.get("duration", 0.0)) if fmt else None,
        "file_size": int(fmt.get("size", 0)) if fmt else None,
    }


def test_e2e_case_a_short_video(tmp_path: Path, db_session: Session):
    """Case A: Short video (12 seconds) with single speech segment."""
    video_path = create_synthetic_video(tmp_path / "case_a.mp4", duration_seconds=12.0)
    audio_path = create_synthetic_audio(tmp_path / "speech_a.wav", duration_seconds=2.5)

    project = Project(title="Case A Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="case_a.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=12.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=2.0, end_time=5.0, text="Short speech")
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="ការនិយាយខ្លី")
    db_session.add(tr1)
    db_session.commit()

    ga1 = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(audio_path),
        duration_seconds=2.5,
        is_outdated=False,
    )
    db_session.add(ga1)
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(project.id, db_session)

    assert result.export_result.video_path.exists()
    assert len(result.timing_conflicts) == 0

    probe = probe_media_streams(result.export_result.video_path)
    assert probe["video_codec"] == "h264"
    assert probe["audio_codec"] == "aac"
    assert abs(probe["video_duration"] - 12.0) <= 0.05
    assert abs(probe["audio_duration"] - 12.0) <= 0.05
    assert abs(probe["format_duration"] - 12.0) <= 0.05


def test_e2e_case_b_medium_video(tmp_path: Path, db_session: Session):
    """Case B: Medium video (35 seconds) with multiple spaced segments."""
    video_path = create_synthetic_video(tmp_path / "case_b.mp4", duration_seconds=35.0)
    audio1 = create_synthetic_audio(tmp_path / "speech_b1.wav", duration_seconds=5.0, freq=400)
    audio2 = create_synthetic_audio(tmp_path / "speech_b2.wav", duration_seconds=6.0, freq=600)

    project = Project(title="Case B Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="case_b.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=35.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=3.0, end_time=10.0, text="Section one")
    t2 = TranscriptSegment(project_id=project.id, segment_order=2, start_time=15.0, end_time=25.0, text="Section two")
    db_session.add_all([t1, t2])
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="ផ្នែកទីមួយ")
    tr2 = TranslationSegment(project_id=project.id, transcript_segment_id=t2.id, segment_order=2, khmer_text="ផ្នែកទីពីរ")
    db_session.add_all([tr1, tr2])
    db_session.commit()

    ga1 = GeneratedAudio(project_id=project.id, translation_segment_id=tr1.id, audio_path=str(audio1), duration_seconds=5.0)
    ga2 = GeneratedAudio(project_id=project.id, translation_segment_id=tr2.id, audio_path=str(audio2), duration_seconds=6.0)
    db_session.add_all([ga1, ga2])
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(project.id, db_session)

    assert result.export_result.video_path.exists()
    assert len(result.timing_conflicts) == 0

    probe = probe_media_streams(result.export_result.video_path)
    assert abs(probe["video_duration"] - 35.0) <= 0.05
    assert abs(probe["audio_duration"] - 35.0) <= 0.05
    assert abs(probe["format_duration"] - 35.0) <= 0.05


def test_e2e_case_c_multiple_segments_with_pauses(tmp_path: Path, db_session: Session):
    """Case C: Multiple speech segments with pauses."""
    video_path = create_synthetic_video(tmp_path / "case_c.mp4", duration_seconds=20.0)
    audio1 = create_synthetic_audio(tmp_path / "c1.wav", duration_seconds=2.0, freq=450)
    audio2 = create_synthetic_audio(tmp_path / "c2.wav", duration_seconds=3.0, freq=550)
    audio3 = create_synthetic_audio(tmp_path / "c3.wav", duration_seconds=2.5, freq=650)

    project = Project(title="Case C Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="case_c.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=20.0,
    )
    db_session.add(video)

    # 3 segments with distinct silence gaps: [1.0-4.0], [7.0-11.0], [14.0-18.0]
    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=1.0, end_time=4.0, text="Intro")
    t2 = TranscriptSegment(project_id=project.id, segment_order=2, start_time=7.0, end_time=11.0, text="Body")
    t3 = TranscriptSegment(project_id=project.id, segment_order=3, start_time=14.0, end_time=18.0, text="Conclusion")
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="សេចក្តីផ្តើម")
    tr2 = TranslationSegment(project_id=project.id, transcript_segment_id=t2.id, segment_order=2, khmer_text="តួសេចក្តី")
    tr3 = TranslationSegment(project_id=project.id, transcript_segment_id=t3.id, segment_order=3, khmer_text="សេចក្តីសន្និដ្ឋាន")
    db_session.add_all([tr1, tr2, tr3])
    db_session.commit()

    ga1 = GeneratedAudio(project_id=project.id, translation_segment_id=tr1.id, audio_path=str(audio1), duration_seconds=2.0)
    ga2 = GeneratedAudio(project_id=project.id, translation_segment_id=tr2.id, audio_path=str(audio2), duration_seconds=3.0)
    ga3 = GeneratedAudio(project_id=project.id, translation_segment_id=tr3.id, audio_path=str(audio3), duration_seconds=2.5)
    db_session.add_all([ga1, ga2, ga3])
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(project.id, db_session)

    assert result.export_result.video_path.exists()
    assert len(result.timing_conflicts) == 0

    probe = probe_media_streams(result.export_result.video_path)
    assert abs(probe["video_duration"] - 20.0) <= 0.05
    assert abs(probe["audio_duration"] - 20.0) <= 0.05


def test_e2e_case_d_speech_near_video_end(tmp_path: Path, db_session: Session):
    """Case D: Video with speech starting near the end boundary."""
    video_path = create_synthetic_video(tmp_path / "case_d.mp4", duration_seconds=10.0)
    audio_path = create_synthetic_audio(tmp_path / "speech_d.wav", duration_seconds=1.8)

    project = Project(title="Case D Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="case_d.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=10.0,
    )
    db_session.add(video)

    # Segment at 7.5s - 9.5s (finishes at 9.3s with 1.8s audio, before 10.0s end)
    t = TranscriptSegment(project_id=project.id, segment_order=1, start_time=7.5, end_time=9.5, text="Near the end")
    db_session.add(t)
    db_session.commit()

    tr = TranslationSegment(project_id=project.id, transcript_segment_id=t.id, segment_order=1, khmer_text="ជិតដល់ទីបញ្ចប់")
    db_session.add(tr)
    db_session.commit()

    ga = GeneratedAudio(project_id=project.id, translation_segment_id=tr.id, audio_path=str(audio_path), duration_seconds=1.8)
    db_session.add(ga)
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(project.id, db_session)

    assert result.export_result.video_path.exists()
    assert len(result.timing_conflicts) == 0

    probe = probe_media_streams(result.export_result.video_path)
    assert abs(probe["video_duration"] - 10.0) <= 0.05
    assert abs(probe["audio_duration"] - 10.0) <= 0.05


def test_e2e_case_e_longer_khmer_translation_and_recovery(tmp_path: Path, db_session: Session):
    """Case E: Khmer translation is too long, strictly blocking export; then user corrects text and export succeeds."""
    video_path = create_synthetic_video(tmp_path / "case_e.mp4", duration_seconds=8.0)
    # Speech starting at 5.0s in 8.0s video. Available window = 3.0s.
    # Initial Khmer audio is 4.5s (overflows even at 1.25x tempo: 4.5/1.25 = 3.6s > 3.0s).
    audio_too_long = create_synthetic_audio(tmp_path / "speech_too_long.wav", duration_seconds=4.5)

    project = Project(title="Case E Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="case_e.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=8.0,
    )
    db_session.add(video)

    t = TranscriptSegment(project_id=project.id, segment_order=1, start_time=5.0, end_time=6.5, text="A long English phrase")
    db_session.add(t)
    db_session.commit()

    tr = TranslationSegment(project_id=project.id, transcript_segment_id=t.id, segment_order=1, khmer_text="ឃ្លាវែងណាស់ដែលនិយាយមិនទាន់")
    db_session.add(tr)
    db_session.commit()

    ga = GeneratedAudio(project_id=project.id, translation_segment_id=tr.id, audio_path=str(audio_too_long), duration_seconds=4.5)
    db_session.add(ga)
    db_session.commit()

    pipeline = DubbingPipeline()

    # 1. First attempt: Blocked by TimingConflictError without creating corrupt MP4
    with pytest.raises(TimingConflictError) as exc_info:
        pipeline.run(project.id, db_session)

    assert len(exc_info.value.conflicts) == 1
    conflict = exc_info.value.conflicts[0]
    # Safe leading silence reduces the physical shortage, but does not erase it.
    assert conflict.overflow_seconds > 0.05
    assert "Shorten the Khmer translation" in conflict.suggested_action
    assert video.exported_video_path is None

    # 2. User recovery: Shorten translation, regenerate audio to fit window
    audio_shortened = create_synthetic_audio(tmp_path / "speech_shortened.wav", duration_seconds=2.2)
    tr.khmer_text = "ឃ្លាខ្លីល្មម"
    ga.audio_path = str(audio_shortened)
    ga.duration_seconds = 2.2
    ga.is_outdated = False
    db_session.commit()

    # 3. Second attempt: Successfully exports
    result = pipeline.run(project.id, db_session)
    assert result.export_result.video_path.exists()
    assert len(result.timing_conflicts) == 0

    probe = probe_media_streams(result.export_result.video_path)
    assert abs(probe["video_duration"] - 8.0) <= 0.05
    assert abs(probe["audio_duration"] - 8.0) <= 0.05
