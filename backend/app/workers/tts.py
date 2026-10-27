import hashlib
import logging
from datetime import datetime
from app.core.timezone import get_cambodia_now_naive
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import get_audio_segment_path
from app.database.session import SessionLocal
from app.models.project import (
    Project,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.tts.base import TTSProvider
from app.services.tts.registry import get_tts_provider
from app.services.tts.exceptions import TTSError

logger = logging.getLogger(__name__)


def synthesize_segment_audio(
    project_id: str,
    segment: TranslationSegment,
    provider: Optional[TTSProvider] = None,
    db: Optional[Session] = None,
    voice: Optional[str] = None,
    seed: Optional[int] = None,
) -> GeneratedAudio:
    """Helper to synthesize audio for a single translation segment and update the database."""
    if db is None:
        raise ValueError("Database session required for synthesize_segment_audio")

    project = db.query(Project).filter(Project.id == project_id).first()
    provider_name = project.tts_provider if project and project.tts_provider else "gtts"
    chosen_voice = voice or (project.tts_voice if project and project.tts_voice else "default")

    if provider is None:
        provider = get_tts_provider(provider_name)

    output_path = get_audio_segment_path(project_id, segment.id)
    kwargs = {}
    if seed is not None:
        kwargs["seed"] = seed

    result = provider.synthesize(
        text=segment.khmer_text,
        output_path=output_path,
        language="km",
        voice=chosen_voice,
        **kwargs,
    )

    # Measure real duration of synthesized audio without destructive silence trimming
    if output_path.exists() and output_path.stat().st_size > 0:
        try:
            from app.services.video.ffmpeg import FFmpegVideoProcessor
            vp = FFmpegVideoProcessor()
            measured_dur = vp.get_audio_duration(output_path)
            if measured_dur > 0:
                result.duration_seconds = measured_dur
        except Exception as e:
            logger.warning("Duration probe failed for segment %s: %s", segment.id, e)

    audio_record = (
        db.query(GeneratedAudio)
        .filter(GeneratedAudio.translation_segment_id == segment.id)
        .first()
    )

    if audio_record:
        audio_record.audio_path = str(result.audio_path)
        audio_record.duration_seconds = result.duration_seconds
        audio_record.provider = result.provider_name
        audio_record.voice = result.voice
        audio_record.is_outdated = False
        audio_record.updated_at = get_cambodia_now_naive()
    else:
        audio_record = GeneratedAudio(
            project_id=project_id,
            translation_segment_id=segment.id,
            audio_path=str(result.audio_path),
            duration_seconds=result.duration_seconds,
            provider=result.provider_name,
            voice=result.voice,
            is_outdated=False,
            created_at=get_cambodia_now_naive(),
            updated_at=get_cambodia_now_naive(),
        )
        db.add(audio_record)

    db.commit()
    db.refresh(audio_record)
    return audio_record


def process_tts(project_id: str, job_id: str, db: Optional[Session] = None) -> None:
    """Synchronous worker function to run in background tasks for Khmer speech synthesis."""
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

        translation_segments = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .order_by(TranslationSegment.segment_order.asc())
            .all()
        )

        if not translation_segments:
            error_msg = "No translated Khmer segments found to synthesize. Please translate first."
            logger.error(error_msg)
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            project.status = ProjectStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 10
        project.status = ProjectStatus.GENERATING_VOICE
        db.commit()

        provider_name = project.tts_provider or "gtts"
        voice_name = project.tts_voice or "default"
        provider = get_tts_provider(provider_name)
        total_segments = len(translation_segments)
        logger.info(
            "Starting TTS synthesis for project %s (%d segments) [provider=%s, voice=%s]...",
            project_id,
            total_segments,
            provider_name,
            voice_name,
        )

        # Deterministic project seed for consistent acoustic rendering across cuts
        project_seed = int(hashlib.md5(project_id.encode("utf-8")).hexdigest()[:8], 16)

        for idx, seg in enumerate(translation_segments):
            if not seg.khmer_text or not seg.khmer_text.strip():
                logger.warning(
                    "Skipping segment order %d with empty Khmer text",
                    seg.segment_order,
                )
                continue

            try:
                synthesize_segment_audio(
                    project_id=project_id,
                    segment=seg,
                    provider=provider,
                    db=db,
                    voice=voice_name,
                    seed=project_seed,
                )
            except Exception as e:
                logger.error(
                    "Failed to synthesize segment %s (order %d): %s",
                    seg.id,
                    seg.segment_order,
                    e,
                )
                raise TTSError(f"Error synthesizing segment {seg.segment_order}: {e}") from e

            # Update progress
            progress = 10 + int(80 * ((idx + 1) / total_segments))
            job.progress_percentage = min(progress, 90)
            db.commit()

        is_timing_aware = (getattr(project, "pipeline_version", "v1") in ("v2", "v2.1", "v2.2", "v2.3"))
        if is_timing_aware:
            job.progress_percentage = 92
            db.commit()
            logger.info("Executing automated timing optimization for project %s (pipeline=%s)...", project_id, project.pipeline_version)
            try:
                from app.services.dubbing.timing_optimizer import TimingOptimizerService
                optimizer = TimingOptimizerService()
                opt_res = optimizer.optimize_project(project_id, db)
                logger.info(
                    "Automated timing optimization finished for %s: %d total, %d fitted, %d speed-adjusted, %d sentence-optimized, %d unresolved",
                    project_id,
                    opt_res.total_segments,
                    opt_res.fitted_naturally,
                    opt_res.speed_adjusted,
                    opt_res.sentence_optimized,
                    opt_res.unresolved_conflicts,
                )
            except Exception as e:
                logger.error("Automated timing optimization encountered an error for project %s: %s", project_id, e)

        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True

        job.progress_percentage = 100
        job.status = JobStatus.COMPLETED
        project.status = ProjectStatus.VOICE_GENERATED
        db.commit()
        logger.info("Successfully completed TTS speech synthesis for project %s", project_id)

    except Exception as e:
        logger.exception("Unexpected error in process_tts: %s", e)
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
