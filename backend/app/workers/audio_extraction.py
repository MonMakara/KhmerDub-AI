import logging
from pathlib import Path
from app.database.session import SessionLocal
from app.models.project import Project, Video, ProcessingJob, ProjectStatus, JobStatus
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import VideoProcessingError

logger = logging.getLogger(__name__)


def process_audio_extraction(project_id: str, job_id: str) -> None:
    """Synchronous worker function designed to run in background tasks."""
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()
        video = db.query(Video).filter(Video.project_id == project_id).first()

        if not job or not project or not video:
            logger.error("Job, project, or video not found for audio extraction: project_id=%s, job_id=%s", project_id, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Project or video record missing"
                db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 20
        db.commit()

        video_path = Path(video.file_path)
        output_audio_path = Path(video.file_path).parent / "extracted_audio.wav"

        processor = FFmpegVideoProcessor()
        processor.extract_audio(video_path, output_audio_path)

        # Update video record
        video.extracted_audio_path = str(output_audio_path)
        project.status = ProjectStatus.AUDIO_EXTRACTED

        job.status = JobStatus.COMPLETED
        job.progress_percentage = 100
        job.error_message = None
        db.commit()

        logger.info("Successfully extracted audio for project %s to %s", project_id, output_audio_path)

    except VideoProcessingError as e:
        logger.error("Video processing error during audio extraction for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    except Exception as e:
        logger.exception("Unexpected error during audio extraction for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected processing error: {e}"
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    finally:
        db.close()
