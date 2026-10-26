import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.project import (
    Project,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.synchronizer import TimingConflictError

logger = logging.getLogger(__name__)


def process_dubbing(
    project_id: str,
    job_id: str,
    db: Optional[Session] = None,
    max_tempo_factor: Optional[float] = None,
    trim_silence: bool = False,
) -> None:
    """Background worker for audio synchronization and dubbed video export."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()

        if not job or not project:
            logger.error("Job or project record missing: project_id=%s, job_id=%s", project_id, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Project or job record missing"
                db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 10
        project.status = ProjectStatus.SYNCHRONIZING
        db.commit()

        pipeline = DubbingPipeline()

        def on_progress(pct: int, msg: str):
            logger.info("Dubbing project %s [%d%%]: %s", project_id, pct, msg)
            job.progress_percentage = pct
            db.commit()

        pipeline_result = pipeline.run(
            project_id=project_id,
            db=db,
            on_progress=on_progress,
            max_tempo_factor=max_tempo_factor,
            trim_silence=trim_silence,
        )

        job.progress_percentage = 100
        job.status = JobStatus.COMPLETED
        # If there were timing conflicts, note them in job error_message / metadata for reference
        if pipeline_result.timing_conflicts:
            conflict_summary = (
                f"Exported successfully with {len(pipeline_result.timing_conflicts)} timing conflict(s) "
                f"(speed adjusted up to 1.25x)."
            )
            job.error_message = conflict_summary
        else:
            job.error_message = None

        project.status = ProjectStatus.COMPLETED
        db.commit()
        logger.info("Successfully completed dubbed video export for project %s", project_id)

    except TimingConflictError as e:
        logger.warning(
            "Dubbing export blocked for project %s: %d timing conflict(s) detected",
            project_id,
            len(e.conflicts),
        )
        if db:
            db.rollback()
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            project = db.query(Project).filter(Project.id == project_id).first()
            if job:
                job.status = JobStatus.FAILED
                top_conflict = e.conflicts[0]
                job.error_message = (
                    f"Export prevented: {len(e.conflicts)} speech segment(s) exceed available timing window. "
                    f"{top_conflict.suggested_action}"
                )
            if project:
                project.status = ProjectStatus.VOICE_GENERATED
            db.commit()

    except Exception as e:
        logger.exception("Dubbing worker failed for project %s: %s", project_id, e)
        if db:
            db.rollback()
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            project = db.query(Project).filter(Project.id == project_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
            if project:
                project.status = ProjectStatus.FAILED
            db.commit()
    finally:
        if should_close:
            db.close()
