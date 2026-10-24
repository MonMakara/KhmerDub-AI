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
)
from app.services.dubbing.exporter import VideoExportService
from app.services.dubbing.pipeline import DubbingPipeline
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
    result = service.synchronize(
        project_id="p1",
        segment_items=items,
        target_duration=3.0,
        output_timeline_path=timeline_path,
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
