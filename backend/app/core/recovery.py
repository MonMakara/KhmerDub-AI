import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    JobStatus,
    ProjectStatus,
)
from app.core.storage import delete_project_storage

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


def recover_interrupted_deletions(db: Session) -> int:
    """Recover and finalize any projects left in DELETING status due to a server restart.

    Guarantees:
    - Finds projects left in ProjectStatus.DELETING.
    - Safely removes project files on disk via delete_project_storage.
    - Cascade-deletes all associated database entities in foreign-key dependency order.
    - Idempotent and safe to run on every startup.
    - Server crashes during deletion never leave projects permanently stuck in DELETING.
    """
    stuck_projects = (
        db.query(Project)
        .filter(Project.status == ProjectStatus.DELETING)
        .all()
    )

    if not stuck_projects:
        logger.info("Startup check: No interrupted project deletions found.")
        return 0

    logger.warning("Startup check: Found %d interrupted project deletion(s) to finalize.", len(stuck_projects))
    recovered_count = 0

    for project in stuck_projects:
        project_id = project.id
        project_title = project.title
        logger.info(
            "Resuming interrupted deletion for project %s ('%s')",
            project_id,
            project_title,
        )

        # 1. Clean up project files on disk
        try:
            storage_info = delete_project_storage(project_id)
            logger.info(
                "Cleaned storage for interrupted project %s: %d file(s)/dir(s) removed",
                project_id,
                storage_info.get("deleted_count", 0),
            )
        except Exception as e:
            logger.error("Failed to delete storage for stuck project %s during startup: %s", project_id, e)

        # 2. Safely purge database records in foreign-key dependency order
        try:
            db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).delete(synchronize_session=False)
            db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).delete(synchronize_session=False)
            db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete(synchronize_session=False)
            db.query(Video).filter(Video.project_id == project_id).delete(synchronize_session=False)
            db.query(ProcessingJob).filter(ProcessingJob.project_id == project_id).delete(synchronize_session=False)
            db.delete(project)
            db.commit()
            recovered_count += 1
            logger.info("Successfully completed interrupted deletion for project %s ('%s')", project_id, project_title)
        except Exception as db_err:
            db.rollback()
            logger.error(
                "Failed to delete database records for stuck project %s on startup: %s",
                project_id,
                db_err,
            )

    return recovered_count

