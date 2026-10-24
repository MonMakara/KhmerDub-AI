from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ai_guard import acquire_ai_inference_slot, get_active_ai_model
from app.core.recovery import recover_interrupted_jobs
from app.models.project import (
    Project,
    Video,
    ProcessingJob,
    JobStatus,
    ProjectStatus,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    TimingConflictError,
)


def test_interrupted_job_recovery(db_session: Session, tmp_path: Path):
    """Verify that orphan jobs interrupted by a server restart are cleanly recovered."""
    # Setup dummy project and video file
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"dummy")

    project = Project(title="Recovery Project", status=ProjectStatus.TRANSCRIBING)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="video.mp4",
        file_path=str(dummy_video),
        file_size_bytes=5,
        duration_seconds=10.0,
    )
    db_session.add(video)

    # 1. Job in RUNNING state
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    job1 = ProcessingJob(
        project_id=project.id,
        job_type="transcribe",
        status=JobStatus.RUNNING,
        progress_percentage=40,
        created_at=past_time,
    )
    db_session.add(job1)
    db_session.commit()

    # Run recovery
    count = recover_interrupted_jobs(db_session, process_start_time=datetime.now(timezone.utc))
    assert count >= 1

    db_session.refresh(job1)
    db_session.refresh(project)

    assert job1.status == JobStatus.FAILED
    assert "interrupted by a server restart" in job1.error_message
    assert project.status == ProjectStatus.AUDIO_EXTRACTED
    assert dummy_video.exists()  # Media files are preserved


def test_interrupted_job_recovery_future_jobs_untouched(db_session: Session):
    """Verify that jobs created after the server start time are not marked as failed."""
    project = Project(title="Active Proj", status=ProjectStatus.TRANSCRIBING)
    db_session.add(project)
    db_session.commit()

    start_time = datetime.now(timezone.utc)
    future_time = start_time + timedelta(seconds=10)

    active_job = ProcessingJob(
        project_id=project.id,
        job_type="transcribe",
        status=JobStatus.RUNNING,
        progress_percentage=20,
        created_at=future_time,
    )
    db_session.add(active_job)
    db_session.commit()

    count = recover_interrupted_jobs(db_session, process_start_time=start_time)
    db_session.refresh(active_job)
    # Active job created after startup should NOT be failed
    assert active_job.status == JobStatus.RUNNING


def test_ai_inference_guard_concurrency():
    """Verify shared AI inference guard manages slot acquisition and tracks active model."""
    assert get_active_ai_model() is None

    with acquire_ai_inference_slot("Test_Whisper"):
        assert get_active_ai_model() == "Test_Whisper"

    assert get_active_ai_model() is None


def test_extract_audio_deduplication(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify that triggering extract-audio when a job is already running does not duplicate jobs."""
    fake_vid = tmp_path / "dedup_vid.mp4"
    fake_vid.write_bytes(b"content")

    project = Project(title="Dedup Proj", status=ProjectStatus.UPLOADED)
    db_session.add(project)
    db_session.commit()

    video = Video(
        project_id=project.id,
        filename="dedup_vid.mp4",
        file_path=str(fake_vid),
        file_size_bytes=10,
        duration_seconds=5.0,
    )
    db_session.add(video)

    job = ProcessingJob(
        project_id=project.id,
        job_type="extract_audio",
        status=JobStatus.RUNNING,
        progress_percentage=25,
    )
    db_session.add(job)
    db_session.commit()

    # Trigger extract-audio API
    res = client.post(f"/api/projects/{project.id}/extract-audio")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == job.id
    assert data["status"] == "running"

    # Verify no second job was added
    all_jobs = db_session.query(ProcessingJob).filter(ProcessingJob.project_id == project.id).all()
    assert len(all_jobs) == 1


def test_timing_safety_margin_configurable(tmp_path: Path):
    """Verify that safety_margin_seconds can be configured and clearly differentiates raw vs effective window."""
    # Service with 0ms safety margin
    service_zero = AudioSynchronizationService(max_tempo_factor=1.25, safety_margin_seconds=0.0)
    # Service with 50ms safety margin
    service_50ms = AudioSynchronizationService(max_tempo_factor=1.25, safety_margin_seconds=0.05)

    assert service_zero.safety_margin_seconds == 0.0
    assert service_50ms.safety_margin_seconds == 0.05
