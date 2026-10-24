import json
import subprocess
from pathlib import Path
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
    TimingConflict,
    TimingConflictError,
)
from app.services.dubbing.exporter import VideoExportService
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.video.exceptions import VideoProcessingError
from app.workers.dubbing import process_dubbing


@pytest.fixture
def test_audio_file(tmp_path: Path) -> Path:
    """Generate a tiny 1-second 1000Hz sine wave MP3 file using FFmpeg."""
    audio_path = tmp_path / "test_tone.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1.0",
        "-c:a", "libmp3lame", "-b:a", "64k",
        str(audio_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path


@pytest.fixture
def test_video_file(tmp_path: Path) -> Path:
    """Generate a tiny 3-second MP4 video with a test audio track using FFmpeg."""
    video_path = tmp_path / "test_sample.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3.0:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


def test_generate_silence(tmp_path: Path):
    service = AudioSynchronizationService()
    silence_path = tmp_path / "silence.wav"
    service.generate_silence(1.5, silence_path)

    assert silence_path.exists()
    dur = service.video_processor.get_audio_duration(silence_path)
    assert 1.4 <= dur <= 1.6


def test_adjust_tempo(test_audio_file: Path, tmp_path: Path):
    service = AudioSynchronizationService()
    adjusted_path = tmp_path / "adjusted.wav"
    # 1.0s audio adjusted with 1.25x tempo should become ~0.8s
    service.adjust_tempo(test_audio_file, adjusted_path, tempo_factor=1.25)

    assert adjusted_path.exists()
    dur = service.video_processor.get_audio_duration(adjusted_path)
    assert 0.7 <= dur <= 0.9


def test_audio_synchronization_engine(test_audio_file: Path, tmp_path: Path):
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "output_timeline.wav"

    t1 = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=1.0, end_time=2.0, text="Hello")
    tr1 = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="សួស្តី")
    a1 = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    t2 = TranscriptSegment(id="t2", project_id="p1", segment_order=2, start_time=3.0, end_time=4.0, text="World")
    tr2 = TranslationSegment(id="tr2", project_id="p1", segment_order=2, khmer_text="ពិភពលោក")
    a2 = GeneratedAudio(id="a2", project_id="p1", translation_segment_id="tr2", audio_path=str(test_audio_file), duration_seconds=1.0)

    items = [(t1, tr1, a1), (t2, tr2, a2)]
    result = service.synchronize(
        project_id="p1",
        segment_items=items,
        target_duration=5.0,
        output_timeline_path=timeline_path,
    )

    assert result.timeline_path.exists()
    assert 4.8 <= result.total_duration_seconds <= 5.2
    assert len(result.conflicts) == 0
    assert result.segments_count == 2


def test_timing_conflict_detection(tmp_path: Path):
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "timeline_conflict.wav"

    # Create a 3.0 second audio file
    long_audio = tmp_path / "long_tone.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=800:duration=3.0",
        "-c:a", "libmp3lame",
        str(long_audio),
    ], check=True, capture_output=True)

    # Available window is only 1.0s (start 0.0, next segment starts at 1.0)
    t1 = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=1.0, text="Sentence 1")
    tr1 = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ប្រយោគមួយ")
    a1 = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(long_audio), duration_seconds=3.0)

    t2 = TranscriptSegment(id="t2", project_id="p1", segment_order=2, start_time=1.0, end_time=2.0, text="Sentence 2")
    tr2 = TranslationSegment(id="tr2", project_id="p1", segment_order=2, khmer_text="ប្រយោគពីរ")
    a2 = GeneratedAudio(id="a2", project_id="p1", translation_segment_id="tr2", audio_path=str(long_audio), duration_seconds=1.0)

    items = [(t1, tr1, a1), (t2, tr2, a2)]

    # 1. In default strict mode, TimingConflictError is raised
    with pytest.raises(TimingConflictError) as exc_info:
        service.synchronize(
            project_id="p1",
            segment_items=items,
            target_duration=3.0,
            output_timeline_path=timeline_path,
        )
    assert len(exc_info.value.conflicts) > 0
    c_strict = exc_info.value.conflicts[0]
    assert c_strict.segment_order == 1
    assert c_strict.required_tempo > 1.25
    assert c_strict.max_tempo_factor == 1.25
    assert c_strict.overflow_seconds > 0.5
    assert "Shorten the Khmer translation" in c_strict.suggested_action

    # 2. In non-strict mode, returns SynchronizationResult with conflicts populated
    result = service.synchronize(
        project_id="p1",
        segment_items=items,
        target_duration=3.0,
        output_timeline_path=timeline_path,
        strict_validation=False,
    )

    assert len(result.conflicts) > 0
    c = result.conflicts[0]
    assert c.segment_order == 1
    assert c.tempo_factor == 1.25
    assert c.overflow_seconds > 0.5
    assert "exceeds available window" in c.message


def test_video_export_service(test_video_file: Path, tmp_path: Path):
    exporter = VideoExportService()

    # Generate a 3-second timeline WAV
    timeline_path = tmp_path / "test_timeline.wav"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=600:duration=3.0",
        "-ar", "44100", "-ac", "2",
        str(timeline_path),
    ], check=True, capture_output=True)

    output_mp4 = tmp_path / "dubbed_final.mp4"
    res = exporter.export(
        video_path=test_video_file,
        audio_timeline_path=timeline_path,
        output_video_path=output_mp4,
    )

    assert res.video_path.exists()
    assert res.file_size_bytes > 0
    assert 2.8 <= res.duration_seconds <= 3.2
    assert res.audio_codec == "aac"
    assert res.video_codec in ("h264", "libx264")


def test_dubbing_pipeline_validations(db_session: Session, tmp_path: Path):
    pipeline = DubbingPipeline()

    # 1. Nonexistent project
    with pytest.raises(ValueError, match="Project not found"):
        pipeline.run("nonexistent_id", db_session)

    # 2. Project with missing video
    proj = Project(title="No Video Proj")
    db_session.add(proj)
    db_session.commit()
    with pytest.raises(FileNotFoundError, match="Original video file is missing"):
        pipeline.run(proj.id, db_session)

    # 3. Project with missing translations
    fake_vid = tmp_path / "fake.mp4"
    fake_vid.write_bytes(b"content")
    video = Video(project_id=proj.id, filename="fake.mp4", file_path=str(fake_vid), file_size_bytes=10, duration_seconds=5.0)
    db_session.add(video)
    db_session.commit()
    with pytest.raises(ValueError, match="No translation segments found"):
        pipeline.run(proj.id, db_session)

    # 4. Outdated audio segment
    t_seg = TranscriptSegment(project_id=proj.id, segment_order=1, start_time=0.0, end_time=2.0, text="Test")
    tr_seg = TranslationSegment(project_id=proj.id, segment_order=1, khmer_text="តេស្ត", transcript_segment=t_seg)
    audio = GeneratedAudio(project_id=proj.id, translation_segment=tr_seg, audio_path="fake.mp3", is_outdated=True)
    db_session.add_all([t_seg, tr_seg, audio])
    db_session.commit()

    with pytest.raises(ValueError, match="is outdated"):
        pipeline.run(proj.id, db_session)


def test_export_api_endpoints(client: TestClient, db_session: Session, test_video_file: Path, test_audio_file: Path, tmp_path: Path):
    # Test 404 for nonexistent project
    res_404 = client.post("/api/projects/unknown_id/export")
    assert res_404.status_code == 404

    # Setup valid project
    project = Project(title="Export Test Proj", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="test_sample.mp4",
        file_path=str(test_video_file),
        file_size_bytes=test_video_file.stat().st_size,
        duration_seconds=3.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=0.5, end_time=2.0, text="Welcome")
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="សូមស្វាគមន៍")
    db_session.add(tr1)
    db_session.commit()

    audio = GeneratedAudio(
        project_id=project.id,
        translation_segment_id=tr1.id,
        audio_path=str(test_audio_file),
        duration_seconds=1.0,
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Trigger export API
    export_res = client.post(f"/api/projects/{project.id}/export")
    assert export_res.status_code == 200
    job_data = export_res.json()
    assert job_data["job_type"] == "dub"

    # Status check API
    status_res = client.get(f"/api/projects/{project.id}/export/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["project_id"] == project.id
    assert status_data["is_export_ready"] is False

    # Simulate completed export file
    output_mp4 = tmp_path / f"dubbed_{project.id}.mp4"
    output_mp4.write_bytes(b"DUBBED_VIDEO_BYTES")
    video.exported_video_path = str(output_mp4)
    video.is_export_outdated = False
    project.status = ProjectStatus.COMPLETED
    db_session.commit()

    # Status check after completion
    status_res_after = client.get(f"/api/projects/{project.id}/export/status")
    assert status_res_after.status_code == 200
    status_data_after = status_res_after.json()
    assert status_data_after["is_export_ready"] is True
    assert status_data_after["is_export_outdated"] is False
    assert status_data_after["video_url"] == f"/api/projects/{project.id}/export/video"
    assert status_data_after["download_url"] == f"/api/projects/{project.id}/export/download"

    # Video stream endpoint
    stream_res = client.get(f"/api/projects/{project.id}/export/video")
    assert stream_res.status_code == 200
    assert "video/mp4" in stream_res.headers.get("content-type", "")
    assert stream_res.content == b"DUBBED_VIDEO_BYTES"

    # Video download endpoint
    download_res = client.get(f"/api/projects/{project.id}/export/download")
    assert download_res.status_code == 200
    assert "video/mp4" in download_res.headers.get("content-type", "")
    assert "attachment" in download_res.headers.get("content-disposition", "")


def test_export_invalidation_on_edits(client: TestClient, db_session: Session, test_video_file: Path, tmp_path: Path):
    project = Project(title="Invalidation Proj", status=ProjectStatus.COMPLETED)
    db_session.add(project)
    db_session.commit()

    dummy_export = tmp_path / "dubbed_sample.mp4"
    dummy_export.write_bytes(b"sample mp4")
    video = Video(
        project_id=project.id,
        filename="test_sample.mp4",
        file_path=str(test_video_file),
        file_size_bytes=100,
        exported_video_path=str(dummy_export),
        is_export_outdated=False,
    )
    db_session.add(video)

    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=0.0, end_time=1.0, text="Initial text")
    db_session.add(t1)
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="អត្ថបទដើម")
    db_session.add(tr1)
    db_session.commit()

    # 1. Update transcript -> video is_export_outdated should become True
    patch_t = client.patch(f"/api/projects/{project.id}/transcript/{t1.id}", json={"text": "Modified text"})
    assert patch_t.status_code == 200
    db_session.refresh(video)
    assert video.is_export_outdated is True

    # Reset
    video.is_export_outdated = False
    db_session.commit()

    # 2. Update translation -> video is_export_outdated should become True
    patch_tr = client.patch(f"/api/projects/{project.id}/translations/{tr1.id}", json={"khmer_text": "អត្ថបទថ្មី"})
    assert patch_tr.status_code == 200
    db_session.refresh(video)
    assert video.is_export_outdated is True


def test_real_end_to_end_dubbing_workflow(test_video_file: Path, test_audio_file: Path, db_session: Session):
    """Full end-to-end integration test creating synchronized timeline and exporting dubbed MP4."""
    project = Project(title="E2E Dubbing Project", status=ProjectStatus.VOICE_GENERATED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="test_sample.mp4",
        file_path=str(test_video_file),
        file_size_bytes=test_video_file.stat().st_size,
        duration_seconds=3.0,
    )
    db_session.add(video)

    t1 = TranscriptSegment(project_id=project.id, segment_order=1, start_time=0.5, end_time=1.8, text="Speech segment 1")
    t2 = TranscriptSegment(project_id=project.id, segment_order=2, start_time=2.0, end_time=2.8, text="Speech segment 2")
    db_session.add_all([t1, t2])
    db_session.commit()

    tr1 = TranslationSegment(project_id=project.id, transcript_segment_id=t1.id, segment_order=1, khmer_text="ផ្នែកសំឡេងទីមួយ")
    tr2 = TranslationSegment(project_id=project.id, transcript_segment_id=t2.id, segment_order=2, khmer_text="ផ្នែកសំឡេងទីពីរ")
    db_session.add_all([tr1, tr2])
    db_session.commit()

    a1 = GeneratedAudio(project_id=project.id, translation_segment_id=tr1.id, audio_path=str(test_audio_file), duration_seconds=1.0, is_outdated=False)
    a2 = GeneratedAudio(project_id=project.id, translation_segment_id=tr2.id, audio_path=str(test_audio_file), duration_seconds=0.7, is_outdated=False)
    db_session.add_all([a1, a2])
    db_session.commit()

    job = ProcessingJob(project_id=project.id, job_type="dub", status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    # Execute dubbing worker
    process_dubbing(project.id, job.id, db=db_session)

    db_session.refresh(job)
    db_session.refresh(project)
    db_session.refresh(video)

    assert job.status == JobStatus.COMPLETED
    assert job.progress_percentage == 100
    assert project.status == ProjectStatus.COMPLETED
    assert video.exported_video_path is not None

    exported_path = Path(video.exported_video_path)
    assert exported_path.exists()
    assert exported_path.stat().st_size > 0

    # Probe exported video with FFprobe to verify streams
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_name,codec_type:format=duration",
        "-of", "json",
        str(exported_path),
    ]
    res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    probe_data = json.loads(res.stdout)

    streams = probe_data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    assert has_video is True
    assert has_audio is True

    format_dur = float(probe_data["format"]["duration"])
    assert 2.8 <= format_dur <= 3.2


def test_audio_longer_than_available_time(tmp_path: Path):
    """Case 1: Audio is longer than available time slot, even at 1.25x tempo."""
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "long_timeline.wav"

    # Create 2.5s audio
    long_audio = tmp_path / "tone_2500ms.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=2.5",
        "-ar", "44100", "-ac", "2", str(long_audio),
    ], check=True, capture_output=True)

    # Available window is only 1.0s (start 0.0, end 1.0, video ends at 1.0)
    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=1.0, text="Text")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="អត្ថបទ")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(long_audio), duration_seconds=2.5)

    with pytest.raises(TimingConflictError) as exc_info:
        service.synchronize("p1", [(t, tr, a)], target_duration=1.0, output_timeline_path=timeline_path)

    assert len(exc_info.value.conflicts) == 1
    c = exc_info.value.conflicts[0]
    assert c.overflow_seconds > 0.5
    assert c.required_tempo > 1.25
    assert "Shorten the Khmer translation" in c.suggested_action


def test_audio_shorter_than_available_time(test_audio_file: Path, tmp_path: Path):
    """Case 2: Audio is shorter than available time slot."""
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "short_timeline.wav"

    # 1.0s audio in 3.0s window
    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.5, end_time=2.0, text="Text")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="អត្ថបទ")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    res = service.synchronize("p1", [(t, tr, a)], target_duration=3.0, output_timeline_path=timeline_path)
    assert len(res.conflicts) == 0
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert 2.9 <= dur <= 3.1


def test_exact_duration_audio(test_audio_file: Path, tmp_path: Path):
    """Case 3: Audio duration matches original segment duration exactly."""
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "exact_timeline.wav"

    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=1.0, text="Text")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="អត្ថបទ")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    res = service.synchronize("p1", [(t, tr, a)], target_duration=1.0, output_timeline_path=timeline_path)
    assert len(res.conflicts) == 0
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert 0.95 <= dur <= 1.05


def test_last_segment_exceeding_video_duration(test_audio_file: Path, tmp_path: Path):
    """Case 4: The last speech segment exceeds the video duration boundary."""
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "tail_overflow.wav"

    # Video is 2.0s, last segment starts at 1.5s, audio is 1.0s
    # Available window is 2.0 - 1.5 = 0.5s.
    # At 1.25x tempo, 1.0 / 1.25 = 0.8s > 0.5s. Overflow = 0.3s.
    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=1.5, end_time=2.0, text="Last words")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ពាក្យចុងក្រោយ")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    with pytest.raises(TimingConflictError) as exc_info:
        service.synchronize("p1", [(t, tr, a)], target_duration=2.0, output_timeline_path=timeline_path)

    c = exc_info.value.conflicts[0]
    assert c.segment_order == 1
    assert c.overflow_seconds >= 0.25


def test_multiple_consecutive_segments(test_audio_file: Path, tmp_path: Path):
    """Case 5: Multiple consecutive speech segments in order."""
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "consecutive_timeline.wav"

    # 3 segments in a 6.0s timeline:
    # Seg 1: 0.5 - 1.5 (audio 1.0s) -> ends at 1.5
    # Seg 2: 2.5 - 3.5 (audio 1.0s) -> ends at 3.5
    # Seg 3: 4.5 - 5.5 (audio 1.0s) -> ends at 5.5
    t1 = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.5, end_time=1.5, text="First")
    tr1 = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ទីមួយ")
    a1 = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    t2 = TranscriptSegment(id="t2", project_id="p1", segment_order=2, start_time=2.5, end_time=3.5, text="Second")
    tr2 = TranslationSegment(id="tr2", project_id="p1", segment_order=2, khmer_text="ទីពីរ")
    a2 = GeneratedAudio(id="a2", project_id="p1", translation_segment_id="tr2", audio_path=str(test_audio_file), duration_seconds=1.0)

    t3 = TranscriptSegment(id="t3", project_id="p1", segment_order=3, start_time=4.5, end_time=5.5, text="Third")
    tr3 = TranslationSegment(id="tr3", project_id="p1", segment_order=3, khmer_text="ទីបី")
    a3 = GeneratedAudio(id="a3", project_id="p1", translation_segment_id="tr3", audio_path=str(test_audio_file), duration_seconds=1.0)

    res = service.synchronize(
        "p1",
        [(t1, tr1, a1), (t2, tr2, a2), (t3, tr3, a3)],
        target_duration=6.0,
        output_timeline_path=timeline_path,
    )
    assert res.segments_count == 3
    assert len(res.conflicts) == 0
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert 5.9 <= dur <= 6.1


def test_overlapping_segments(test_audio_file: Path, tmp_path: Path):
    """Case 6: Transcript segments with overlapping timestamps handled without crash."""
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "overlap_timeline.wav"

    # Segments overlap: Seg 1 [1.0, 2.5], Seg 2 [2.0, 3.5]
    t1 = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=1.0, end_time=2.5, text="Overlap 1")
    tr1 = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ត្រួតស៊ីគ្នា ១")
    a1 = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    t2 = TranscriptSegment(id="t2", project_id="p1", segment_order=2, start_time=2.0, end_time=3.5, text="Overlap 2")
    tr2 = TranslationSegment(id="tr2", project_id="p1", segment_order=2, khmer_text="ត្រួតស៊ីគ្នា ២")
    a2 = GeneratedAudio(id="a2", project_id="p1", translation_segment_id="tr2", audio_path=str(test_audio_file), duration_seconds=1.0)

    res = service.synchronize(
        "p1",
        [(t1, tr1, a1), (t2, tr2, a2)],
        target_duration=4.5,
        output_timeline_path=timeline_path,
        strict_validation=False,
    )
    assert res.timeline_path.exists()
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert dur >= 3.0


def test_silence_padding(test_audio_file: Path, tmp_path: Path):
    """Case 7: Silence padding before speech, between speech, and trailing silence."""
    service = AudioSynchronizationService()
    timeline_path = tmp_path / "silence_padded_timeline.wav"

    # Segment starts at 2.0s and ends at 3.0s in 5.0s video
    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=2.0, end_time=3.0, text="Mid")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="កណ្តាល")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(test_audio_file), duration_seconds=1.0)

    res = service.synchronize("p1", [(t, tr, a)], target_duration=5.0, output_timeline_path=timeline_path)
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert 4.95 <= dur <= 5.05


def test_safe_tempo_adjustment(tmp_path: Path):
    """Case 8: Khmer speech is slightly longer (1.15s) than window (1.0s) and fits within 1.25x tempo."""
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "tempo_fit_timeline.wav"

    # 1.15s tone
    tone = tmp_path / "tone_1150ms.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=1.15",
        "-ar", "44100", "-ac", "2", str(tone),
    ], check=True, capture_output=True)

    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=1.0, text="Slightly long")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="វែងបន្តិច")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(tone), duration_seconds=1.15)

    # 1.15s at tempo ~1.20x fits into 1.0s window without conflict
    res = service.synchronize("p1", [(t, tr, a)], target_duration=2.0, output_timeline_path=timeline_path)
    assert len(res.conflicts) == 0
    dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert 1.95 <= dur <= 2.05


def test_unresolved_timing_conflicts_details(tmp_path: Path):
    """Case 9: Detailed attributes of TimingConflict."""
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "conflict_details.wav"

    long_audio = tmp_path / "tone_3s.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=700:duration=3.0",
        "-ar", "44100", "-ac", "2", str(long_audio),
    ], check=True, capture_output=True)

    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.5, end_time=1.5, text="Long text")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="វែងខ្លាំង")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(long_audio), duration_seconds=3.0)

    with pytest.raises(TimingConflictError) as exc_info:
        service.synchronize("p1", [(t, tr, a)], target_duration=2.0, output_timeline_path=timeline_path)

    c = exc_info.value.conflicts[0]
    assert c.segment_order == 1
    assert c.start_time == 0.5
    assert c.end_time == 1.5
    assert c.original_duration == 1.0
    assert c.khmer_duration >= 2.9
    assert c.required_tempo > 1.25
    assert c.max_tempo_factor == 1.25
    assert c.overflow_seconds > 0.5
    assert len(c.suggested_action) > 10
    assert len(c.message) > 20


def test_correct_output_stream_durations(test_video_file: Path, tmp_path: Path):
    """Case 10: Output video and audio stream durations verified strictly with FFprobe."""
    exporter = VideoExportService()

    # Generate exact 3.0s timeline
    timeline_path = tmp_path / "exact_3s_timeline.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0",
        "-ar", "44100", "-ac", "2", str(timeline_path),
    ], check=True, capture_output=True)

    output_mp4 = tmp_path / "verified_durations.mp4"
    res = exporter.export(
        video_path=test_video_file,
        audio_timeline_path=timeline_path,
        output_video_path=output_mp4,
        expected_duration=3.0,
        tolerance_seconds=0.15,
    )
    assert res.video_path.exists()
    assert 2.9 <= res.duration_seconds <= 3.1

    # Verify that a mismatched timeline raises VideoProcessingError
    short_timeline = tmp_path / "short_1s_timeline.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
        "-ar", "44100", "-ac", "2", str(short_timeline),
    ], check=True, capture_output=True)

    mismatch_output = tmp_path / "mismatch.mp4"
    with pytest.raises(VideoProcessingError, match="duration mismatch"):
        exporter.export(
            video_path=test_video_file,
            audio_timeline_path=short_timeline,
            output_video_path=mismatch_output,
            expected_duration=3.0,
            tolerance_seconds=0.15,
        )


def test_prevention_of_silent_truncation(tmp_path: Path):
    """Case 11: Speech is never cut off silently. Overflowing speech is preserved in non-strict mode."""
    service = AudioSynchronizationService(max_tempo_factor=1.25)
    timeline_path = tmp_path / "full_speech.wav"

    # 2.5s speech in 1.0s window
    long_speech = tmp_path / "speech_2500ms.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=350:duration=2.5",
        "-ar", "44100", "-ac", "2", str(long_speech),
    ], check=True, capture_output=True)

    t = TranscriptSegment(id="t1", project_id="p1", segment_order=1, start_time=0.0, end_time=1.0, text="Full sentence")
    tr = TranslationSegment(id="tr1", project_id="p1", segment_order=1, khmer_text="ប្រយោគពេញលេញ")
    a = GeneratedAudio(id="a1", project_id="p1", translation_segment_id="tr1", audio_path=str(long_speech), duration_seconds=2.5)

    # In strict mode, export is blocked
    with pytest.raises(TimingConflictError):
        service.synchronize("p1", [(t, tr, a)], target_duration=1.0, output_timeline_path=timeline_path, strict_validation=True)

    # In non-strict mode, full speech is preserved (duration >= 2.5 / 1.25 = 2.0s, not cut at 1.0s)
    res = service.synchronize("p1", [(t, tr, a)], target_duration=1.0, output_timeline_path=timeline_path, strict_validation=False)
    actual_dur = service.video_processor.get_audio_duration(res.timeline_path)
    assert actual_dur >= 1.95  # Preserved full duration at 1.25x tempo, NOT truncated at 1.0s
