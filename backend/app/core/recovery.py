import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.project import Project, ProcessingJob, JobStatus, ProjectStatus

logger = logging.getLogger(__name__)


def recover_interrupted_jobs(db: Session, process_start_time: Optional[datetime] = None) -> int:
    """Safely recover and finalize orphan jobs interrupted by a previous server restart or shutdown.
    
    Guarantees:
    - Never deletes any generated media files on disk.
    - Never deletes any database entities (transcripts, translations, audios).
    - Only marks jobs that were left in PENDING or RUNNING status prior to this server process starting.
    - Resets the linked project status back to the last known complete milestone.
    """
    cutoff = process_start_time or datetime.now(timezone.utc)
    
    interrupted_jobs = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .all()
    )

    if not interrupted_jobs:
        logger.info("Startup check: No interrupted background jobs found.")
        return 0

    recovered_count = 0
    for job in interrupted_jobs:
        # Avoid touching jobs created after the current process startup
        if job.created_at and job.created_at.tzinfo is None:
            # Handle naive datetime from SQLite
            created_at_utc = job.created_at.replace(tzinfo=timezone.utc)
        else:
            created_at_utc = job.created_at

        if created_at_utc and created_at_utc > cutoff:
            continue

        logger.warning(
            "Recovering orphan job %s (type=%s, project_id=%s, previous_status=%s)",
            job.id,
            job.job_type,
            job.project_id,
            job.status.value,
        )

        job.status = JobStatus.FAILED
        job.error_message = (
            "Job was interrupted by a server restart or shutdown. "
            "No completed files or records were removed; please retry this step."
        )

        project = db.query(Project).filter(Project.id == job.project_id).first()
        if project:
            # Restore project status to previous completed milestone
            if job.job_type == "extract_audio":
                project.status = ProjectStatus.UPLOADED
            elif job.job_type == "transcribe" and project.status == ProjectStatus.TRANSCRIBING:
                project.status = ProjectStatus.AUDIO_EXTRACTED
            elif job.job_type == "translate" and project.status == ProjectStatus.TRANSLATING:
                project.status = ProjectStatus.TRANSCRIBED
            elif job.job_type == "tts" and project.status == ProjectStatus.GENERATING_VOICE:
                project.status = ProjectStatus.TRANSLATED
            elif job.job_type == "dub" and project.status == ProjectStatus.SYNCHRONIZING:
                project.status = ProjectStatus.VOICE_GENERATED

        recovered_count += 1

    if recovered_count > 0:
        db.commit()
        logger.info("Successfully recovered %d interrupted background job(s).", recovered_count)

    return recovered_count
