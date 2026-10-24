import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.project import Project, Video, TranscriptSegment, ProcessingJob, ProjectStatus, JobStatus
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.exceptions import TranscriptionError

logger = logging.getLogger(__name__)


def process_transcription(project_id: str, job_id: str, db: Optional[Session] = None) -> None:
    """Synchronous worker function designed to run in background tasks for STT transcription."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()
        video = db.query(Video).filter(Video.project_id == project_id).first()

        if not job or not project or not video:
            logger.error("Job, project, or video record missing: project_id=%s, job_id=%s", project_id, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Project or video record missing"
                db.commit()
            return

        if not video.extracted_audio_path or not Path(video.extracted_audio_path).exists():
            error_msg = "Extracted audio file does not exist. Please extract audio first."
            logger.error(error_msg)
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            project.status = ProjectStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 20
        project.status = ProjectStatus.TRANSCRIBING
        db.commit()

        audio_path = Path(video.extracted_audio_path)
        provider = FasterWhisperTranscriptionProvider()
        segments = provider.transcribe(audio_path, language=project.original_language or "en")

        job.progress_percentage = 80
        db.commit()

        # Safely replace any existing transcript segments on retranscription
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete()

        # Insert new segments
        for seg in segments:
            db_segment = TranscriptSegment(
                project_id=project_id,
                segment_order=seg.segment_order,
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
            )
            db.add(db_segment)

        project.status = ProjectStatus.TRANSCRIBED
        job.status = JobStatus.COMPLETED
        job.progress_percentage = 100
        job.error_message = None
        db.commit()

        logger.info(
            "Successfully completed transcription for project %s: saved %d segments",
            project_id,
            len(segments),
        )

    except TranscriptionError as e:
        logger.error("Transcription error for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    except Exception as e:
        logger.exception("Unexpected error during transcription for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected transcription failure: {e}"
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    finally:
        if should_close:
            db.close()
