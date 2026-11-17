import hashlib
import json
import logging
import shutil
import uuid
from pathlib import Path
import time
from app.core.timezone import get_cambodia_now_naive
from typing import Optional
from sqlalchemy.orm import Session

from app.core.storage import get_audio_segment_path, resolve_audio_file
from app.services.tts.selection import effective_voice, validate_voice, audio_matches_selection
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
from app.services.tts.registry import DEFAULT_PROVIDER, DEFAULT_VOICE, get_tts_provider
from app.services.tts.exceptions import TTSError, TTSGenerationError

logger = logging.getLogger(__name__)


def synthesize_segment_audio(
    project_id: str,
    segment: TranslationSegment,
    provider: Optional[TTSProvider] = None,
    db: Optional[Session] = None,
    voice: Optional[str] = None,
    seed: Optional[int] = None,
    candidate_text: Optional[str] = None,
    expected_text: Optional[str] = None,
    max_duration: Optional[float] = None,
) -> GeneratedAudio:
    """Helper to synthesize audio for a single translation segment and update the database."""
    if db is None:
        raise ValueError("Database session required for synthesize_segment_audio")

    db.refresh(segment)
    project = db.query(Project).populate_existing().filter(Project.id == project_id).one()
    provider_name, chosen_voice = effective_voice(project, segment)
    expected_revision = segment.voice_revision or 0
    approved_text = segment.khmer_text
    if candidate_text is not None and (segment.is_manually_edited or approved_text != expected_text):
        raise TTSGenerationError("Translation changed or was manually approved; automatic replacement cancelled.")
    spoken_text = candidate_text if candidate_text is not None else approved_text
    if segment.is_outdated:
        raise TTSGenerationError("Source translation is outdated. Review and update the Khmer translation before generating speech.")
    segment_id = segment.id
    if provider is None:
        validate_voice(db, provider_name, chosen_voice, legacy=not segment.voice_override_id)
        provider = get_tts_provider(provider_name)
    # Release the read transaction during slow inference. Publication is conditional.
    db.commit()

    output_path = get_audio_segment_path(project_id, segment.id)
    kwargs = {}
    if segment.style:
        kwargs["emotion_style"] = segment.style
    if seed is not None:
        kwargs["seed"] = seed

    # Every attempt has a separate immutable master. A failed retry must never
    # overwrite the current recording or leave its duration paired with new bytes.
    from app.services.video.ffmpeg import FFmpegVideoProcessor
    from app.services.dubbing.speech_guard import SpeechGuardService

    vp = FFmpegVideoProcessor()
    guard = SpeechGuardService()
    attempts_dir = output_path.parent / "raw_masters" / segment.id
    attempts_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    selected = None
    for attempt in range(2):
        candidate = attempts_dir / f"{run_id}_{attempt}{output_path.suffix}"
        attempt_kwargs = dict(kwargs)
        if attempt:
            attempt_kwargs["seed"] = (seed + 1) if seed is not None else 43
        try:
            candidate_result = provider.synthesize(
                text=spoken_text,
                output_path=candidate,
                language="km",
                voice=chosen_voice,
                **attempt_kwargs,
            )
            # Use the provider's returned file, rather than assuming it honored
            # the requested destination. Production VoxCPM must pass inspection.
            candidate = Path(candidate_result.audio_path)
            strict_quality = candidate_result.provider_name == "voxcpm"
            try:
                measured_duration = vp.get_audio_duration(candidate)
            except Exception:
                if strict_quality:
                    raise
                measured_duration = candidate_result.duration_seconds
            if measured_duration <= 0 and not strict_quality:
                measured_duration = candidate_result.duration_seconds
            if measured_duration <= 0:
                raise TTSGenerationError("Generated speech has no measurable audio duration.")
            candidate_result.duration_seconds = measured_duration
            if strict_quality:
                inspection = guard.inspect_speech_audio(candidate, spoken_text)
                if inspection.completeness_status != "plausibly_complete":
                    raise TTSGenerationError(
                        "Speech requires review: " + (inspection.warning_message or "invalid audio")
                    )
            elif len(spoken_text.strip()) >= 20 and len(spoken_text.strip()) / measured_duration > 24:
                raise TTSGenerationError("Generated speech is suspiciously short; review required.")
            if max_duration is not None and measured_duration > max_duration:
                raise TTSGenerationError("Replacement speech still exceeds its measured timing budget.")
            selected = candidate_result
            break
        except Exception as exc:
            logger.warning("Speech attempt %d failed for %s: %s", attempt + 1, segment.id, exc)
            if attempt == 1:
                raise TTSGenerationError(
                    f"No acceptable speech recording for segment {segment.segment_order}; "
                    "existing audio preserved. Please review the text and voice reference."
                ) from exc

    result = selected
    if (result.provider_name, result.voice) != (provider_name, chosen_voice):
        raise TTSGenerationError("Provider returned a different voice; recording was not published.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    (attempts_dir / f"{run_id}.json").write_text(json.dumps({
        "unit_id": segment.id,
        "translation_revision": hashlib.sha256(spoken_text.encode()).hexdigest(),
        "approved_text": spoken_text,
        "previous_text": approved_text if candidate_text is not None else None,
        "timing_budget_seconds": max_duration,
        "voice_revision": expected_revision,
        "provider": provider_name,
        "audio_revision": run_id,
        "raw_master": str(result.audio_path),
        "measured_duration": result.duration_seconds,
        "voice": result.voice,
        "lexical_status": "unverified_human_listening_required",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep accepted files immutable: no concurrent result can overwrite current bytes.
    accepted_path = output_path.with_name(f"{output_path.stem}.{run_id}{output_path.suffix}")
    shutil.copyfile(result.audio_path, accepted_path)
    result.audio_path = accepted_path
    db.expire_all()
    publication = db.query(TranslationSegment).filter(
        TranslationSegment.id == segment_id,
        TranslationSegment.voice_revision == expected_revision,
        TranslationSegment.khmer_text == approved_text,
        TranslationSegment.is_outdated.is_(False),
    )
    updates = {TranslationSegment.tts_error: None}
    if candidate_text is not None:
        publication = publication.filter(TranslationSegment.is_manually_edited.is_(False))
        updates[TranslationSegment.khmer_text] = spoken_text
        updates[TranslationSegment.explanation] = (
            "Automatically rephrased for the selected voice's measured timing; "
            "replacement speech passed duration checks. Compare meaning and pronunciation before export."
        )
    claimed = publication.update(updates, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        raise TTSGenerationError("Voice or text changed during generation. Previous audio preserved; regenerate this unit.")
    # The conditional write serializes voice mutation and publication in SQLite.
    if provider_name == "voxcpm":
        from app.models.voice import VoiceProfile, VoiceConsent
        authorized = db.query(VoiceProfile).join(VoiceConsent).filter(
            VoiceProfile.id == chosen_voice, VoiceProfile.is_active.is_(True),
            VoiceConsent.is_authorized.is_(True),
        ).first()
        if authorized is None:
            db.rollback()
            raise TTSGenerationError("Speaker consent is no longer authorized. Recording was not published.")

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
        audio_record.voice_revision = expected_revision
        audio_record.is_outdated = False
        audio_record.updated_at = get_cambodia_now_naive()
    else:
        audio_record = GeneratedAudio(
            project_id=project_id,
            translation_segment_id=segment.id,
            audio_path=str(result.audio_path),
            duration_seconds=result.duration_seconds,
            voice_revision=expected_revision,
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

        total_segments = len(translation_segments)

        # Deterministic project seed for consistent acoustic rendering across cuts
        project_seed = int(hashlib.md5(project_id.encode("utf-8")).hexdigest()[:8], 16)

        for idx, seg in enumerate(translation_segments):
            db.refresh(seg)
            db.refresh(project)
            provider_name, voice_name = effective_voice(project, seg)
            if not seg.khmer_text or not seg.khmer_text.strip():
                logger.warning(
                    "Skipping segment order %d with empty Khmer text",
                    seg.segment_order,
                )
                continue

            # Check if this segment already has current, valid generated audio matching target provider & voice
            existing_audio = (
                db.query(GeneratedAudio)
                .filter(GeneratedAudio.translation_segment_id == seg.id)
                .first()
            )
            out_file = resolve_audio_file(project_id, seg.id, existing_audio.audio_path if existing_audio else None)
            if (
                existing_audio
                and audio_matches_selection(project, seg, existing_audio)
                and existing_audio.provider == provider_name
                and existing_audio.voice == voice_name
                and (existing_audio.duration_seconds or 0) > 0
                and out_file.exists()
                and out_file.stat().st_size > 0
            ):
                logger.info(
                    "Segment order %d already has current valid audio (%.2fs), skipping re-synthesis",
                    seg.segment_order,
                    existing_audio.duration_seconds,
                )
                progress = 10 + int(80 * ((idx + 1) / total_segments))
                job.progress_percentage = min(progress, 90)
                db.commit()
                continue

            # Slight delay between consecutive requests for cloud providers to prevent burst throttling
            if provider_name in ("edge", "gtts") and idx > 0:
                time.sleep(0.25)

            generation_revision = seg.voice_revision
            try:
                validate_voice(db, provider_name, voice_name, legacy=not seg.voice_override_id)
                provider = get_tts_provider(provider_name)
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
                failed_id = seg.id
                failed_revision = generation_revision
                db.rollback()
                db.query(TranslationSegment).filter_by(id=failed_id, voice_revision=failed_revision).update(
                    {TranslationSegment.tts_error: str(e)}, synchronize_session=False)
                db.commit()
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
                from app.services.dubbing.duration_repair import DurationRepairService
                DurationRepairService(optimizer=optimizer).repair_project(project_id, db, seed=project_seed)
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
