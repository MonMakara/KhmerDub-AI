import re
import json
import math
import logging
from pathlib import Path
from typing import List, Optional
from app.core.timezone import get_cambodia_now_naive

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    Query,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    resolve_audio_file,
    delete_project_storage,
)
from app.database.session import get_db
from app.services.subtitles.generator import (
    SubtitleCue,
    generate_srt,
    generate_vtt,
    generate_txt,
)
from app.services.subtitles.parser import (
    parse_transcript_content,
    TranscriptParseError,
)
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    SubtitleSegment,
    ProjectSpeaker,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectDeleteResponse,
    ProjectResponse,
    ProjectSummaryResponse,
    ProcessingJobResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
    TranscriptResponse,
    SegmentationPreviewItem,
    SegmentationPreviewResponse,
    SegmentationApplyRequest,
    SegmentationApplyResponse,
    SegmentSplitRequest,
    SegmentSplitResponse,
    TranslationSegmentResponse,
    TranslationSegmentUpdate,
    TranslationListResponse,
    GeneratedAudioResponse,
    GeneratedAudioListResponse,
    TimingConflictResponse,
    ExportStatusResponse,
    AudioStatusSummary,
    SegmentVoiceUpdate,
    BulkSegmentVoiceUpdate,
    ProjectVoiceUpdate,
    ProjectTranslationSettingsUpdate,
    AIImproveRequest,
    AIImproveResponse,
    AlternativeOption,
    AlternativesResponse,
    ApplyTranslationRequest,
    ProjectSpeakerResponse,
    ProjectSpeakerUpdate,
    SegmentSpeakerUpdate,
    BulkSegmentSpeakerUpdate,
    DiarizationRunRequest,
    DiarizationRunResponse,
)
from app.schemas.voice import (
    VoiceProfileResponse,
    CloneCandidateResponse,
    CloneCandidatesListResponse,
    CloneFromVideoRequest,
    CloneSpeakerVoiceRequest,
    CloneSpeakerVoiceResponse,
    ClonedSpeakerItem,
    AutoDiarizeAndCloneRequest,
    AutoDiarizeAndCloneResponse,
)
from app.services.voice.extractor import VideoVoiceExtractor
from app.services.voice.diarizer import AudioDiarizer
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import (
    CorruptedVideoError,
    InvalidVideoFormatError,
    VideoProcessingError,
)
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.translation.registry import (
    get_translation_provider,
    validate_translation_provider,
    get_active_ai_provider_name,
)
from app.services.translation.formatter import KhmerTextFormatter
from app.services.translation.exceptions import (
    ProviderAuthenticationError,
    RateLimitError,
)
from app.services.tts.registry import (
    get_tts_provider,
    is_valid_voice_combination,
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
)
from app.workers.audio_extraction import process_audio_extraction
from app.workers.transcription import process_transcription
from app.services.transcription.base import (
    TranscriptionSegment, WordTiming, project_segment_id,
)
from app.services.transcription.segmentation import (
    segment_transcript,
    split_segment_at_word,
    merge_adjacent_segments,
)
from app.workers.translation import process_translation
from app.workers.tts import process_tts, synthesize_segment_audio
from app.workers.dubbing import process_dubbing
from app.services.dubbing import AutoFitService

from app.services.tts.exceptions import TTSError
from app.services.tts.selection import (
    effective_voice, voice_catalog, validate_voice, set_unit_voice,
    preserve_partition, audio_matches_selection, partition_voice, assignment_map, source_keys,
    voice_aware_groups,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    name = Path(filename).name
    # Strip any characters except alphanumeric, dashes, dots, and underscores
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return sanitized or "video.mp4"


@router.get("", response_model=List[ProjectSummaryResponse])
def list_projects(db: Session = Depends(get_db)) -> List[ProjectSummaryResponse]:
    """Retrieve all dubbing projects, excluding any currently undergoing deletion."""
    projects = (
        db.query(Project)
        .filter(Project.status != ProjectStatus.DELETING)
        .order_by(Project.created_at.desc())
        .all()
    )
    return projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    """Create a new dubbing project."""
    tts_provider = (payload.tts_provider or DEFAULT_PROVIDER).strip().lower()
    tts_voice = (payload.tts_voice or DEFAULT_VOICE).strip()
    if not is_valid_voice_combination(tts_provider, tts_voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice combination: provider='{tts_provider}', voice='{tts_voice}'",
        )

    trans_provider = (payload.translation_provider or "nllb").strip().lower()
    trans_style = (payload.translation_style or "natural").strip().lower()
    if not validate_translation_provider(trans_provider):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation provider: '{trans_provider}'",
        )

    project = Project(
        title=payload.title,
        original_language=payload.original_language,
        target_language=payload.target_language,
        translation_provider=trans_provider,
        translation_style=trans_style,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
        pipeline_version=payload.pipeline_version or "v2.3",
        status=ProjectStatus.CREATED,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _voice_mutation_allowed(db: Session, project_id: str) -> None:
    active = db.query(ProcessingJob).filter(
        ProcessingJob.project_id == project_id,
        ProcessingJob.job_type.in_(["dub", "translate", "transcribe"]),
        ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
    ).first()
    if active:
        raise HTTPException(status_code=409, detail="Wait for export or source processing to finish before changing voices.")


@router.get("/{project_id}/segment-voices")
def get_segment_voices(project_id: str, db: Session = Depends(get_db)):
    if not db.query(Project).filter_by(id=project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    return {"voices": voice_catalog(db)}


def _save_segment_voices(project_id: str, ids: List[str], payload: SegmentVoiceUpdate, db: Session):
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=409, detail="Project is deleting")
    _voice_mutation_allowed(db, project_id)
    provider = payload.provider.strip().lower() if payload.provider else None
    voice = payload.voice.strip() if payload.voice else None
    target_style = (payload.emotion_style or payload.style or "").strip() or None

    if bool(provider) != bool(voice):
        raise HTTPException(status_code=400, detail="Provide both provider and voice, or reset both to null.")
    if provider:
        try:
            validate_voice(db, provider, voice)
        except TTSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    segments = db.query(TranslationSegment).filter(
        TranslationSegment.project_id == project_id, TranslationSegment.id.in_(set(ids)),
    ).all()
    if len(segments) != len(set(ids)):
        raise HTTPException(status_code=404, detail="One or more dubbing units were not found in this project.")
    for segment in segments:
        if provider is not None and voice is not None:
            set_unit_voice(db, project, segment, provider, voice)
        elif payload.provider is None and payload.voice is None and not target_style:
            set_unit_voice(db, project, segment, None, None)
        if target_style:
            segment.style = target_style
            segment.updated_at = get_cambodia_now_naive()
    db.commit()
    return [_enrich_translation_segment(s) for s in segments]


@router.patch("/{project_id}/translations/voices")
def update_segment_voices(project_id: str, payload: BulkSegmentVoiceUpdate, db: Session = Depends(get_db)):
    return {"segments": _save_segment_voices(project_id, payload.segment_ids, payload, db)}


@router.patch("/{project_id}/translations/{segment_id}/voice", response_model=TranslationSegmentResponse)
def update_segment_voice(project_id: str, segment_id: str, payload: SegmentVoiceUpdate,
                         db: Session = Depends(get_db)):
    return _save_segment_voices(project_id, [segment_id], payload, db)[0]


def _recalculate_speaker_stats(db: Session, project_id: str) -> None:
    """Recalculate segment counts and durations for all speakers in a project."""
    speakers = db.query(ProjectSpeaker).filter(ProjectSpeaker.project_id == project_id).all()
    transcript_segs = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).all()
    grouped: Dict[str, List[TranscriptSegment]] = {}
    for s in transcript_segs:
        if s.speaker_label:
            grouped.setdefault(s.speaker_label, []).append(s)

    for spk in speakers:
        assigned = grouped.get(spk.speaker_label, [])
        spk.segment_count = len(assigned)
        spk.total_duration = round(sum(max(0.0, s.end_time - s.start_time) for s in assigned), 2)
        spk.updated_at = get_cambodia_now_naive()
    db.commit()


@router.post("/{project_id}/diarization/run", response_model=DiarizationRunResponse)
def run_project_diarization(
    project_id: str,
    payload: Optional[DiarizationRunRequest] = None,
    db: Session = Depends(get_db),
) -> DiarizationRunResponse:
    """Run acoustic multi-speaker diarization and character profiling on project segments."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=409, detail="Project is deleting")

    min_speakers = payload.min_speakers if payload and payload.min_speakers else 1
    max_speakers = payload.max_speakers if payload and payload.max_speakers else 6
    if min_speakers > max_speakers:
        raise HTTPException(status_code=400, detail="min_speakers cannot be greater than max_speakers")

    diarizer = AudioDiarizer()
    try:
        result = diarizer.diarize_project(
            db=db,
            project_id=project_id,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Diarization failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Diarization failed: {e}")

    speakers = (
        db.query(ProjectSpeaker)
        .filter(ProjectSpeaker.project_id == project_id)
        .order_by(ProjectSpeaker.speaker_label.asc())
        .all()
    )

    return DiarizationRunResponse(
        project_id=project_id,
        speakers_detected=len(speakers),
        speakers=[ProjectSpeakerResponse.model_validate(s) for s in speakers],
        assigned_segments_count=len(result.segment_assignments),
        message=f"Successfully detected {len(speakers)} speaker(s) across {len(result.segment_assignments)} segments.",
    )


@router.get("/{project_id}/speakers", response_model=List[ProjectSpeakerResponse])
def get_project_speakers(
    project_id: str,
    db: Session = Depends(get_db),
) -> List[ProjectSpeakerResponse]:
    """Retrieve all detected character/speaker profiles for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    speakers = (
        db.query(ProjectSpeaker)
        .filter(ProjectSpeaker.project_id == project_id)
        .order_by(ProjectSpeaker.speaker_label.asc())
        .all()
    )
    return [ProjectSpeakerResponse.model_validate(s) for s in speakers]


@router.put("/{project_id}/speakers/{speaker_label}", response_model=ProjectSpeakerResponse)
def update_project_speaker(
    project_id: str,
    speaker_label: str,
    payload: ProjectSpeakerUpdate,
    db: Session = Depends(get_db),
) -> ProjectSpeakerResponse:
    """Update speaker display name, color, or cast a bulk voice for this character."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=409, detail="Project is deleting")

    speaker = (
        db.query(ProjectSpeaker)
        .filter(ProjectSpeaker.project_id == project_id, ProjectSpeaker.speaker_label == speaker_label)
        .first()
    )
    if not speaker:
        raise HTTPException(status_code=404, detail=f"Speaker '{speaker_label}' not found")

    _voice_mutation_allowed(db, project_id)

    if payload.display_name is not None and payload.display_name.strip():
        speaker.display_name = payload.display_name.strip()
    if payload.color is not None and payload.color.strip():
        speaker.color = payload.color.strip()

    # If voice assignment is specified, validate and cascade
    provider = payload.assigned_voice_provider.strip().lower() if payload.assigned_voice_provider else None
    voice = payload.assigned_voice_id.strip() if payload.assigned_voice_id else None

    if bool(provider) != bool(voice):
        raise HTTPException(status_code=400, detail="Provide both assigned_voice_provider and assigned_voice_id, or neither.")

    if provider and voice:
        try:
            validate_voice(db, provider, voice)
        except TTSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        speaker.assigned_voice_provider = provider
        speaker.assigned_voice_id = voice
        db.commit()

        # Cascade to all translation segments belonging to this speaker
        diarizer = AudioDiarizer()
        diarizer.apply_speaker_voice(
            db=db,
            project_id=project_id,
            speaker_label=speaker_label,
            provider=provider,
            voice_id=voice,
        )

    speaker.updated_at = get_cambodia_now_naive()
    db.commit()
    db.refresh(speaker)
    return ProjectSpeakerResponse.model_validate(speaker)


@router.put("/{project_id}/transcript/{segment_id}/speaker", response_model=TranscriptSegmentResponse)
def update_transcript_segment_speaker(
    project_id: str,
    segment_id: str,
    payload: SegmentSpeakerUpdate,
    db: Session = Depends(get_db),
) -> TranscriptSegmentResponse:
    """Manually assign or reassign a speaker to a transcript segment and its translation unit."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=409, detail="Project is deleting")

    segment = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id, TranscriptSegment.id == segment_id)
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Transcript segment not found")

    new_label = payload.speaker_label.strip() if payload.speaker_label else None

    # Validate speaker exists if non-null
    if new_label:
        spk = db.query(ProjectSpeaker).filter(
            ProjectSpeaker.project_id == project_id, ProjectSpeaker.speaker_label == new_label
        ).first()
        if not spk:
            # Auto-create speaker if not found
            color_idx = db.query(ProjectSpeaker).filter(ProjectSpeaker.project_id == project_id).count()
            palette = ["indigo", "emerald", "amber", "rose", "cyan", "purple", "teal", "orange"]
            spk = ProjectSpeaker(
                project_id=project_id,
                speaker_label=new_label,
                display_name=new_label.replace("_", " ").title(),
                detected_gender="unknown",
                color=palette[color_idx % len(palette)],
                assigned_voice_provider="edge",
                assigned_voice_id="km-KH-PisethNeural",
                segment_count=0,
                total_duration=0.0,
                created_at=get_cambodia_now_naive(),
                updated_at=get_cambodia_now_naive(),
            )
            db.add(spk)
            db.commit()

    segment.speaker_label = new_label

    # Propagate to corresponding translation segments
    trans_segs = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).all()
    for trans in trans_segs:
        is_match = False
        if trans.transcript_segment_id == segment_id:
            is_match = True
        elif trans.source_segment_ids:
            try:
                src_ids = json.loads(trans.source_segment_ids)
                if isinstance(src_ids, list) and segment_id in src_ids:
                    is_match = True
            except Exception:
                pass

        if is_match:
            trans.speaker_label = new_label
            # If the assigned speaker has a voice, cascade to translation segment
            if new_label:
                speaker_model = db.query(ProjectSpeaker).filter(
                    ProjectSpeaker.project_id == project_id, ProjectSpeaker.speaker_label == new_label
                ).first()
                if speaker_model and speaker_model.assigned_voice_provider and speaker_model.assigned_voice_id:
                    set_unit_voice(
                        db, project, trans,
                        speaker_model.assigned_voice_provider,
                        speaker_model.assigned_voice_id,
                    )

    db.commit()
    _recalculate_speaker_stats(db, project_id)
    db.refresh(segment)
    return TranscriptSegmentResponse.model_validate(segment)



@router.patch("/{project_id}/voice", response_model=ProjectResponse)
def update_project_voice(
    project_id: str,
    voice_update: ProjectVoiceUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update selected TTS provider and voice for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    provider = (voice_update.tts_provider or DEFAULT_PROVIDER).strip().lower()
    voice = (voice_update.tts_voice or DEFAULT_VOICE).strip()

    if not is_valid_voice_combination(provider, voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice combination: provider='{provider}', voice='{voice}'",
        )

    _voice_mutation_allowed(db, project_id)
    try:
        validate_voice(db, provider, voice)
    except TTSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if project.tts_provider != provider or project.tts_voice != voice:
        project.tts_provider = provider
        project.tts_voice = voice
        # Explicit overrides are independent of a new project default.
        inherited = db.query(TranslationSegment).filter(
            TranslationSegment.project_id == project_id,
            TranslationSegment.voice_override_id.is_(None),
        )
        inherited_ids = [s.id for s in inherited.all()]
        inherited.update({TranslationSegment.voice_revision: TranslationSegment.voice_revision + 1,
                          TranslationSegment.tts_error: None}, synchronize_session="fetch")
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id,
            (GeneratedAudio.translation_segment_id.in_(inherited_ids)) | (GeneratedAudio.translation_segment_id.is_(None))).update(
            {GeneratedAudio.is_outdated: True}, synchronize_session="fetch"
        )
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
        db.commit()
        db.refresh(project)

    return project


@router.patch("/{project_id}/translation-settings", response_model=ProjectResponse)
def update_project_translation_settings(
    project_id: str,
    payload: ProjectTranslationSettingsUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update selected translation provider and style for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    provider_id = (payload.translation_provider or "nllb").strip().lower()
    style_id = (payload.translation_style or "natural").strip().lower()

    if not validate_translation_provider(provider_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation provider: '{provider_id}'. Valid options: nllb, gemini",
        )

    valid_styles = ["natural", "simple", "formal", "short", "standard"]
    if style_id not in valid_styles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation style: '{style_id}'. Valid options: {', '.join(valid_styles)}",
        )

    project.translation_provider = provider_id
    project.translation_style = style_id
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    """Retrieve details for a specific project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )
    return project


@router.get("/{project_id}/voice/clone-candidates", response_model=CloneCandidatesListResponse)
def get_clone_candidates(
    project_id: str,
    max_candidates: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> CloneCandidatesListResponse:
    """Analyze video transcript and return optimal speech candidate clips for voice cloning."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    extractor = VideoVoiceExtractor()
    candidates = extractor.find_candidates(project, max_candidates=max_candidates)

    cand_responses = [
        CloneCandidateResponse(
            candidate_id=c.candidate_id,
            segment_order=c.segment_order,
            segment_ids=c.segment_ids,
            start_time=c.start_time,
            end_time=c.end_time,
            duration=c.duration,
            text=c.text,
            score=c.score,
            preview_url=c.preview_url,
        )
        for c in candidates
    ]
    recommended_id = cand_responses[0].candidate_id if cand_responses else None

    return CloneCandidatesListResponse(
        project_id=project_id,
        candidates=cand_responses,
        recommended_candidate_id=recommended_id,
    )


@router.get("/{project_id}/voice/preview-candidate")
def preview_clone_candidate(
    project_id: str,
    start_time: float = Query(..., ge=0.0),
    end_time: float = Query(..., ge=0.0),
    db: Session = Depends(get_db),
):
    """Stream a short audio preview slice directly from the project video."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be greater than start_time.")

    extractor = VideoVoiceExtractor()
    try:
        source_media = extractor.resolve_source_audio_path(project)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    temp_preview = settings.TEMP_DIR / f"candidate_{project_id}_{int(start_time*100)}_{int(end_time*100)}.wav"
    try:
        extractor.extract_speech_slice(
            source_media_path=source_media,
            start_time=start_time,
            end_time=end_time,
            output_path=temp_preview,
            min_duration=0.5,
            target_sample_rate=24000,
        )
    except Exception as e:
        logger.warning("Preview extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to extract candidate preview: {e}")

    return FileResponse(temp_preview, media_type="audio/wav")


@router.post("/{project_id}/voice/clone-from-video", response_model=VoiceProfileResponse, status_code=status.HTTP_201_CREATED)
def clone_voice_from_video(
    project_id: str,
    payload: CloneFromVideoRequest,
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Extract speech reference audio from the video, create an authorized cloned VoiceProfile,
    and optionally set it as the active project voice.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    _voice_mutation_allowed(db, project_id)

    extractor = VideoVoiceExtractor()
    try:
        profile = extractor.clone_voice_from_video(
            project_id=project_id,
            db=db,
            segment_id=payload.segment_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            voice_name=payload.voice_name,
            set_as_project_voice=payload.set_as_project_voice,
            store_in_voice_studio=payload.store_in_voice_studio,
        )
    except Exception as e:
        logger.exception("Failed to clone voice from video for project %s: %s", project_id, e)
        raise HTTPException(status_code=400, detail=str(e))

    return VoiceProfileResponse.model_validate(profile)


@router.post("/{project_id}/speakers/clone-voices", response_model=CloneSpeakerVoiceResponse, status_code=status.HTTP_201_CREATED)
def clone_speakers_from_video(
    project_id: str,
    payload: Optional[CloneSpeakerVoiceRequest] = None,
    db: Session = Depends(get_db),
) -> CloneSpeakerVoiceResponse:
    """Extract reference audio from project video for detected speakers, clone character voices,
    and cast them automatically with the choice to keep them project-only (no need to store in Voice Studio).
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    _voice_mutation_allowed(db, project_id)

    speaker_label = payload.speaker_label if payload else None
    store_in_studio = payload.store_in_voice_studio if payload else False

    extractor = VideoVoiceExtractor()
    try:
        results = extractor.clone_speaker_voices(
            project_id=project_id,
            db=db,
            speaker_label=speaker_label,
            store_in_voice_studio=store_in_studio,
        )
    except Exception as e:
        logger.exception("Failed to clone speaker voices for project %s: %s", project_id, e)
        raise HTTPException(status_code=400, detail=str(e))

    items = [ClonedSpeakerItem(**r) for r in results]
    dest_str = "and stored in Voice Studio" if store_in_studio else "(project-only; not stored in Voice Studio)"
    return CloneSpeakerVoiceResponse(
        project_id=project_id,
        cloned_speakers=items,
        created_profiles_count=len(items),
        message=f"Successfully cloned {len(items)} character voice(s) {dest_str}.",
    )


@router.post("/{project_id}/speakers/auto-detect-and-clone", response_model=AutoDiarizeAndCloneResponse)
def auto_detect_and_clone_speakers(
    project_id: str,
    payload: Optional[AutoDiarizeAndCloneRequest] = None,
    db: Session = Depends(get_db),
) -> AutoDiarizeAndCloneResponse:
    """Automatically detect all speaking characters in the video via speaker diarization,
    extract high-fidelity reference audio for each speaker, and clone their voices
    using VoxCPM to speak in Khmer with their original vocal timbre.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=409, detail="Project is deleting")

    _voice_mutation_allowed(db, project_id)

    # Verify transcript exists
    transcript_count = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).count()
    if transcript_count == 0:
        raise HTTPException(status_code=400, detail="No transcript segments found. Transcribe video first.")

    min_speakers = payload.min_speakers if payload and payload.min_speakers else 1
    max_speakers = payload.max_speakers if payload and payload.max_speakers else 6
    store_in_studio = payload.store_in_voice_studio if payload else False

    if min_speakers > max_speakers:
        raise HTTPException(status_code=400, detail="min_speakers cannot be greater than max_speakers")

    # Step 1: Run Speaker Diarization
    diarizer = AudioDiarizer()
    try:
        diarizer.diarize_project(
            db=db,
            project_id=project_id,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except Exception as e:
        logger.exception("Diarization failed in auto_detect_and_clone for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Speaker detection failed: {e}")

    # Step 2: Clone Voices for All Detected Speakers
    extractor = VideoVoiceExtractor()
    try:
        clone_results = extractor.clone_speaker_voices(
            project_id=project_id,
            db=db,
            store_in_voice_studio=store_in_studio,
        )
    except Exception as e:
        logger.exception("Voice extraction/cloning failed in auto_detect_and_clone for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Voice cloning from video failed: {e}")

    # If only 1 speaker was detected and cloned, set as project default voice
    if len(clone_results) == 1:
        first_cloned = clone_results[0]
        project.tts_provider = "voxcpm"
        project.tts_voice = first_cloned["voice_profile_id"]
        db.commit()

    # Step 3: Refresh and collect speakers
    speakers = (
        db.query(ProjectSpeaker)
        .filter(ProjectSpeaker.project_id == project_id)
        .order_by(ProjectSpeaker.speaker_label.asc())
        .all()
    )

    cloned_items = [ClonedSpeakerItem(**r) for r in clone_results]
    spk_items = [ProjectSpeakerResponse.model_validate(s) for s in speakers]

    dest_str = "and saved in Voice Studio" if store_in_studio else "(project-only)"
    msg = (
        f"Successfully detected {len(speakers)} character(s) and cloned {len(cloned_items)} voice(s) {dest_str}. "
        "Each character is now configured to speak their translated Khmer lines using their cloned voice."
    )

    return AutoDiarizeAndCloneResponse(
        project_id=project_id,
        speakers_detected=len(speakers),
        cloned_voices_count=len(cloned_items),
        speakers=spk_items,
        cloned_speakers=cloned_items,
        message=msg,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Rename an existing project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rename a project that is being deleted",
        )

    project.title = payload.title
    project.updated_at = get_cambodia_now_naive()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectDeleteResponse:
    """
    Safely delete a project and all associated files and database records.
    Precondition: Project must not have active background processing jobs.
    Two-stage deletion:
      Stage 1: Mark project status as 'deleting' to block new jobs and mutations.
      Stage 2: Safely remove files and cascade-delete database records.
    Idempotent and resilient: if deletion was interrupted, safely resumes Stage 2.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1. Check for active background processing jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    active_project_statuses = [
        ProjectStatus.TRANSCRIBING,
        ProjectStatus.TRANSLATING,
        ProjectStatus.GENERATING_VOICE,
        ProjectStatus.SYNCHRONIZING,
    ]
    if active_job or project.status in active_project_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete project with active background processing jobs. Please wait for the job to complete or fail before deleting.",
        )

    title = project.title

    # 2. Stage 1: Mark project as deleting to prevent new incoming jobs and mutations
    if project.status != ProjectStatus.DELETING:
        project.status = ProjectStatus.DELETING
        db.commit()

    # 3. Stage 2: Clean up project files on disk
    deleted_files_count = 0
    try:
        storage_info = delete_project_storage(project_id)
        deleted_files_count = storage_info.get("deleted_count", 0)
    except Exception as e:
        logger.error(f"Error deleting storage for project {project_id}: {e}")

    # 4. Safe explicit database cleanup in foreign-key dependency order
    try:
        db.query(SubtitleSegment).filter(SubtitleSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).delete(synchronize_session=False)
        db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(Video).filter(Video.project_id == project_id).delete(synchronize_session=False)
        db.query(ProcessingJob).filter(ProcessingJob.project_id == project_id).delete(synchronize_session=False)
        db.delete(project)
        db.commit()
    except Exception as db_err:
        db.rollback()
        logger.error(f"Failed to delete database records for project {project_id}: {db_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during project deletion: {str(db_err)}",
        )

    return ProjectDeleteResponse(
        message=f"Project '{title}' and all associated assets have been successfully deleted.",
        id=project_id,
        deleted_files_count=deleted_files_count,
    )


@router.post("/{project_id}/upload", response_model=ProjectResponse)
async def upload_video(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Upload an MP4 video file, validate with FFprobe, and trigger audio extraction."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename provided")

    safe_name = sanitize_filename(file.filename)
    if not safe_name.lower().endswith((".mp4", ".mov")):
        raise HTTPException(status_code=400, detail="Only MP4 video files are accepted")

    project_dir = settings.UPLOADS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    dest_path = project_dir / safe_name

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB buffer

    try:
        with open(dest_path, "wb") as f:
            while chunk := await file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    f.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                        if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE")
                        else 413,
                        detail=f"Video file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.error("Error streaming uploaded file: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to save uploaded file: {e}"
        ) from e
    finally:
        await file.close()

    if total_bytes == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes)")

    # Validate actual media container with FFprobe
    processor = FFmpegVideoProcessor()
    try:
        metadata = processor.get_metadata(dest_path)
    except (CorruptedVideoError, InvalidVideoFormatError) as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except VideoProcessingError as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400, detail=f"Media validation error: {e}"
        ) from e
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error validating video: {e}"
        ) from e

    # Persist or update Video entity
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video:
        video = Video(
            project_id=project_id,
            filename=safe_name,
            file_path=str(dest_path),
            file_size_bytes=total_bytes,
            duration_seconds=metadata.duration_seconds,
            width=metadata.width,
            height=metadata.height,
            video_codec=metadata.video_codec,
            audio_codec=metadata.audio_codec,
        )
        db.add(video)
    else:
        # If replacing an existing video, delete old file if distinct
        if video.file_path and video.file_path != str(dest_path):
            try:
                Path(video.file_path).unlink(missing_ok=True)
            except Exception:
                pass
        video.filename = safe_name
        video.file_path = str(dest_path)
        video.file_size_bytes = total_bytes
        video.duration_seconds = metadata.duration_seconds
        video.width = metadata.width
        video.height = metadata.height
        video.video_codec = metadata.video_codec
        video.audio_codec = metadata.audio_codec
        video.extracted_audio_path = None

    project.original_video_path = str(dest_path)
    project.status = ProjectStatus.UPLOADED

    # Create extraction processing job
    job = ProcessingJob(
        project_id=project_id,
        job_type="extract_audio",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(project)

    # Dispatch audio extraction in background
    background_tasks.add_task(process_audio_extraction, project_id, job.id)

    return project


@router.post("/{project_id}/extract-audio", response_model=ProcessingJobResponse)
def trigger_audio_extraction(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Manually trigger or retry audio extraction for an uploaded video."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(
            status_code=400, detail="No uploaded video found for this project"
        )

    # Check for existing active audio extraction job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "extract_audio",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="extract_audio",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_audio_extraction, project_id, job.id)
    return job


@router.get("/{project_id}/jobs", response_model=List[ProcessingJobResponse])
def get_project_jobs(
    project_id: str, db: Session = Depends(get_db)
) -> List[ProcessingJobResponse]:
    """Retrieve all processing jobs for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.project_id == project_id)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )
    return jobs


@router.api_route("/{project_id}/video", methods=["GET", "HEAD"])
def get_project_video(project_id: str, db: Session = Depends(get_db)):
    """Stream or preview the uploaded video file."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video.file_path,
        media_type="video/mp4",
        filename=video.filename,
    )


@router.api_route("/{project_id}/audio", methods=["GET", "HEAD"])
def get_project_audio(project_id: str, db: Session = Depends(get_db)):
    """Stream or preview the extracted WAV audio file."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if (
        not video
        or not video.extracted_audio_path
        or not Path(video.extracted_audio_path).exists()
    ):
        raise HTTPException(
            status_code=404, detail="Extracted audio file not found"
        )

    return FileResponse(
        video.extracted_audio_path,
        media_type="audio/wav",
        filename="extracted_audio.wav",
        content_disposition_type="inline",
    )


@router.post("/{project_id}/transcribe", response_model=ProcessingJobResponse)
def start_transcription(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Start asynchronous speech-to-text transcription using faster-whisper."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = db.query(Video).filter(Video.project_id == project_id).first()
    if (
        not video
        or not video.extracted_audio_path
        or not Path(video.extracted_audio_path).exists()
    ):
        raise HTTPException(
            status_code=400,
            detail="Extracted audio file not found. Please upload a video first.",
        )

    # Prevent duplicate concurrent transcription jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "transcribe",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A transcription job is already in progress for this project.",
        )

    job = ProcessingJob(
        project_id=project_id,
        job_type="transcribe",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_transcription, project_id, job.id)
    return job


@router.get("/{project_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    project_id: str, db: Session = Depends(get_db)
) -> TranscriptResponse:
    """Retrieve all transcribed segments for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return TranscriptResponse(
        project_id=project_id,
        status=project.status,
        segmentation_mode=project.segmentation_mode or "sentence",
        segments=segments,
    )


@router.get("/{project_id}/transcript/export")
def export_project_transcript(
    project_id: str,
    format: str = Query("srt", description="Export format: 'srt', 'vtt', 'txt', 'json'"),
    mode: str = Query("cues", description="Export mode: 'cues' (raw subtitle cues) or 'dubbing_units' (grouped speech units for AI translation)"),
    db: Session = Depends(get_db),
):
    """Export project transcript as SRT, WebVTT, plain text, or structured JSON."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    if not segments:
        raise HTTPException(status_code=400, detail="No transcript segments found to export.")

    pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"
    is_grouped_dubbing = (pipeline_ver in ("v2.3", "v3", "v3.0"))

    export_units = None
    if mode == "dubbing_units" and is_grouped_dubbing:
        saved_voice_units = db.query(TranslationSegment).filter_by(project_id=project_id).all()
        export_units = voice_aware_groups(segments, saved_voice_units)

    base_title = sanitize_filename(project.title or "project").replace(".mp4", "")
    fmt = (format or "srt").strip().lower()

    if export_units is not None:
        if fmt == "json":
            items = [
                {
                    "segment_order": u.unit_order,
                    "start_time": u.start_time,
                    "end_time": u.end_time,
                    "duration_seconds": round(u.duration, 2),
                    "text": u.combined_english_text,
                    "source_segment_ids": u.source_segment_ids,
                    "source_segment_orders": u.source_segment_orders,
                }
                for u in export_units
            ]
            content = json.dumps(items, ensure_ascii=False, indent=2)
            filename = f"{base_title}_dubbing_units.json"
            mime_type = "application/json; charset=utf-8"
        else:
            cues = [
                SubtitleCue(
                    sequence=u.unit_order,
                    start_time=u.start_time,
                    end_time=u.end_time,
                    text=u.combined_english_text,
                )
                for u in export_units
            ]
            if fmt == "srt":
                content = generate_srt(cues, prevent_overlaps=True, filter_empty=True)
                filename = f"{base_title}_dubbing_units.srt"
                mime_type = "text/plain; charset=utf-8"
            elif fmt == "vtt":
                content = generate_vtt(cues, prevent_overlaps=True, filter_empty=True)
                filename = f"{base_title}_dubbing_units.vtt"
                mime_type = "text/vtt; charset=utf-8"
            elif fmt == "txt":
                content = generate_txt(cues, filter_empty=True)
                filename = f"{base_title}_dubbing_units.txt"
                mime_type = "text/plain; charset=utf-8"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported format '{fmt}'. Choose 'srt', 'vtt', 'txt', or 'json'.",
                )
    else:
        if fmt == "json":
            items = [
                {
                    "segment_order": s.segment_order,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "text": s.text,
                    "speaker_label": s.speaker_label,
                }
                for s in segments
            ]
            content = json.dumps(items, ensure_ascii=False, indent=2)
            filename = f"{base_title}_transcript.json"
            mime_type = "application/json; charset=utf-8"
        else:
            cues = [
                SubtitleCue(
                    sequence=s.segment_order,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=s.text,
                )
                for s in segments
            ]
            if fmt == "srt":
                content = generate_srt(cues, prevent_overlaps=True, filter_empty=True)
                filename = f"{base_title}_transcript.srt"
                mime_type = "text/plain; charset=utf-8"
            elif fmt == "vtt":
                content = generate_vtt(cues, prevent_overlaps=True, filter_empty=True)
                filename = f"{base_title}_transcript.vtt"
                mime_type = "text/vtt; charset=utf-8"
            elif fmt == "txt":
                content = generate_txt(cues, filter_empty=True)
                filename = f"{base_title}_transcript.txt"
                mime_type = "text/plain; charset=utf-8"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported format '{fmt}'. Choose 'srt', 'vtt', 'txt', or 'json'.",
                )

    return Response(
        content=content.encode("utf-8"),
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        },
    )


@router.post("/{project_id}/transcript/import")
async def import_project_transcript(
    project_id: str,
    file: Optional[UploadFile] = File(None),
    raw_content: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Import transcript cues from SRT, WebVTT, plain text, or JSON file."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = ""
    filename = ""
    if file is not None and getattr(file, "filename", None) and hasattr(file, "read"):
        filename = file.filename or ""
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8", errors="replace")
    elif isinstance(raw_content, str) and raw_content.strip():
        content = raw_content
        filename = "pasted_transcript.txt"
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or provide raw_content.")

    content = content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Transcript content is empty.")

    parsed_cues = []
    warnings = []
    is_json = content.startswith(("[", "{")) or filename.lower().endswith(".json")

    if is_json:
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "segments" in data:
                data = data["segments"]
            if isinstance(data, list):
                for idx, item in enumerate(data, start=1):
                    if isinstance(item, dict):
                        txt = (item.get("text") or item.get("transcript") or item.get("sentence") or item.get("english") or "").strip()
                        if txt:
                            st = float(item.get("start_time") or item.get("start") or (idx - 1) * 3.0)
                            et = float(item.get("end_time") or item.get("end") or (st + 2.5))
                            spk = item.get("speaker_label") or item.get("speaker")
                            parsed_cues.append({
                                "order": idx,
                                "text": txt,
                                "start": max(0.0, st),
                                "end": max(st + 0.1, et),
                                "speaker": spk,
                            })
        except Exception as e:
            logger.warning("JSON transcript parse failed: %s. Attempting subtitle parser.", e)

    if not parsed_cues:
        try:
            res = parse_transcript_content(content, filename=filename)
            warnings = res.warnings
            total_segs = len(res.segments)
            video_dur = project.video.duration_seconds if (project.video and project.video.duration_seconds) else None

            for idx, seg in enumerate(res.segments, start=1):
                if not res.has_timestamps or seg.start_time is None:
                    if video_dur and video_dur > 0 and total_segs > 0:
                        slot = video_dur / total_segs
                        st = round((idx - 1) * slot, 3)
                        et = round(min(video_dur, idx * slot), 3)
                    else:
                        st = round((idx - 1) * 3.0, 3)
                        et = round(idx * 3.0, 3)
                else:
                    st = max(0.0, float(seg.start_time))
                    et = max(st + 0.1, float(seg.end_time))
                parsed_cues.append({
                    "order": idx,
                    "text": seg.text,
                    "start": st,
                    "end": et,
                    "speaker": None,
                })
        except TranscriptParseError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse transcript: {e}")

    if not parsed_cues:
        raise HTTPException(status_code=400, detail="No readable speech cues found in uploaded transcript.")

    # Remove existing transcript segments
    db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete(synchronize_session=False)

    new_segments = []
    for cue in parsed_cues:
        t_seg = TranscriptSegment(
            project_id=project_id,
            segment_order=cue["order"],
            start_time=cue["start"],
            end_time=cue["end"],
            text=cue["text"],
            speaker_label=cue["speaker"],
            is_manually_edited=True,
        )
        new_segments.append(t_seg)
        db.add(t_seg)

    # Invalidate translations & exports
    for tr in db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).all():
        tr.is_outdated = True

    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    project.segmentation_mode = "custom"
    if project.status in (
        ProjectStatus.CREATED,
        ProjectStatus.UPLOADED,
        ProjectStatus.AUDIO_EXTRACTED,
        ProjectStatus.FAILED,
    ):
        project.status = ProjectStatus.TRANSCRIBED

    db.commit()

    return {
        "message": f"Successfully imported {len(new_segments)} transcript segments.",
        "segment_count": len(new_segments),
        "status": project.status,
        "warnings": warnings,
    }


@router.patch(
    "/{project_id}/transcript/{segment_id}",
    response_model=TranscriptSegmentResponse,
)
def update_transcript_segment(
    project_id: str,
    segment_id: str,
    payload: TranscriptSegmentUpdate,
    db: Session = Depends(get_db),
) -> TranscriptSegmentResponse:
    """Update transcription text for a single segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.id == segment_id,
            TranscriptSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Transcript segment not found")

    clean_text = payload.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Segment text cannot be empty")

    old_text = segment.text
    segment.text = clean_text

    # If transcript text changed, mark corresponding translation as outdated
    if old_text != clean_text:
        segment.is_manually_edited = True
        segment.is_approximate = True
        linked_trans = None
        if segment.dubbing_unit_id:
            linked_trans = db.query(TranslationSegment).filter(TranslationSegment.id == segment.dubbing_unit_id).first()
        if not linked_trans:
            linked_trans = (
                db.query(TranslationSegment)
                .filter(
                    TranslationSegment.project_id == project_id,
                    (TranslationSegment.transcript_segment_id == segment_id)
                    | (TranslationSegment.source_segment_ids.like(f"%{segment_id}%")),
                )
                .first()
            )
        if linked_trans:
            linked_trans.is_outdated = True
            # Update combined source text if member transcript changed
            if linked_trans.source_segment_ids:
                try:
                    src_ids = json.loads(linked_trans.source_segment_ids)
                    member_segs = db.query(TranscriptSegment).filter(TranscriptSegment.id.in_(src_ids)).order_by(TranscriptSegment.segment_order).all()
                    linked_trans.source_text = " ".join(m.text for m in member_segs)
                except Exception:
                    pass
            if linked_trans.generated_audio:
                linked_trans.generated_audio.is_outdated = True
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True

    db.commit()
    db.refresh(segment)
    return segment


def _load_raw_segments_for_project(project: Project, db: Session) -> List[TranscriptionSegment]:
    """Retrieve raw transcription segments with word timings for a project."""
    if project.raw_transcript_json:
        try:
            data = json.loads(project.raw_transcript_json)
            return [TranscriptionSegment.from_dict(d) for d in data]
        except Exception as e:
            logger.warning("Failed to deserialize project.raw_transcript_json: %s", e)

    # Check data/projects/{project_id}/asr_raw.json
    try:
        asr_dir = Path(settings.PROJECTS_DATA_DIR if hasattr(settings, "PROJECTS_DATA_DIR") else "/app/data/projects") / project.id
        asr_file = asr_dir / "asr_raw.json"
        if asr_file.exists():
            data = json.loads(asr_file.read_text(encoding="utf-8"))
            return [TranscriptionSegment.from_dict(d) for d in data]
    except Exception as e:
        logger.warning("Failed to read asr_raw.json: %s", e)

    # Fallback to current db TranscriptSegment rows
    db_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project.id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    result = []
    for s in db_segs:
        words = None
        if s.words_json:
            try:
                w_list = json.loads(s.words_json)
                words = [WordTiming.from_dict(w) for w in w_list]
            except Exception:
                pass
        result.append(
            TranscriptionSegment(
                segment_order=s.segment_order,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                words=words,
                is_approximate=s.is_approximate,
                is_manually_edited=s.is_manually_edited,
            )
        )
    return result


@router.get(
    "/{project_id}/transcript/segmentation/preview",
    response_model=SegmentationPreviewResponse,
)
def preview_transcript_segmentation(
    project_id: str,
    mode: str = Query("sentence", description="Segmentation mode: original, sentence, or dubbing"),
    db: Session = Depends(get_db),
) -> SegmentationPreviewResponse:
    """Preview proposed transcript segments and assess downstream invalidation impact."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_segs = _load_raw_segments_for_project(project, db)
    if not raw_segs:
        raise HTTPException(status_code=400, detail="No transcript available to segment")

    mode_clean = mode.lower().strip()
    if mode_clean not in ("original", "sentence", "dubbing"):
        raise HTTPException(status_code=400, detail=f"Unsupported segmentation mode: {mode}")

    proposed = segment_transcript(raw_segs, mode=mode_clean)
    curr_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    has_user_edits = any(s.is_manually_edited for s in curr_segs)
    trans_count = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
    audio_count = db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).count()
    has_video_export = bool(project.video and project.video.exported_video_path)

    requires_confirmation = has_user_edits or trans_count > 0 or audio_count > 0
    impact_warning = None
    if requires_confirmation:
        parts = []
        if has_user_edits:
            parts.append("manual transcript edits")
        if trans_count > 0:
            parts.append(f"{trans_count} Khmer translation(s)")
        if audio_count > 0:
            parts.append(f"{audio_count} generated audio clip(s)")
        impact_warning = (
            f"Applying {mode_clean.title()} segmentation will change transcript segment boundaries and mark "
            + " and ".join(parts)
            + " as outdated. Re-translation will be required."
        )

    preview_items = [
        SegmentationPreviewItem(
            segment_order=s.segment_order,
            start_time=s.start_time,
            end_time=s.end_time,
            duration=round(s.end_time - s.start_time, 2),
            text=s.text,
            is_approximate=s.is_approximate,
        )
        for s in proposed
    ]

    return SegmentationPreviewResponse(
        project_id=project_id,
        current_mode=project.segmentation_mode or "sentence",
        requested_mode=mode_clean,
        current_segment_count=len(curr_segs),
        proposed_segment_count=len(proposed),
        proposed_segments=preview_items,
        has_user_edits=has_user_edits,
        has_translations=trans_count > 0,
        translation_count=trans_count,
        has_audio=audio_count > 0,
        audio_count=audio_count,
        has_exported_video=has_video_export,
        requires_confirmation=requires_confirmation,
        impact_warning=impact_warning,
    )


@router.post(
    "/{project_id}/transcript/segmentation/apply",
    response_model=SegmentationApplyResponse,
)
def apply_transcript_segmentation(
    project_id: str,
    payload: SegmentationApplyRequest,
    db: Session = Depends(get_db),
) -> SegmentationApplyResponse:
    """Apply the selected segmentation mode to the project transcript and invalidate downstream outputs."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project is deleting")

    raw_segs = _load_raw_segments_for_project(project, db)
    if not raw_segs:
        raise HTTPException(status_code=400, detail="No transcript available to segment")

    mode = payload.mode.lower().strip()
    if mode not in ("original", "sentence", "dubbing"):
        raise HTTPException(status_code=400, detail=f"Unsupported segmentation mode: {payload.mode}")

    curr_segs = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).all()
    has_user_edits = any(s.is_manually_edited for s in curr_segs)
    trans_count = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
    audio_count = db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).count()

    needs_confirm = has_user_edits or trans_count > 0 or audio_count > 0
    if needs_confirm and not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: applying new segmentation will invalidate existing translations or audio."
        )

    new_segs = segment_transcript(raw_segs, mode=mode)
    try:
        preserve_partition(new_segs, project.translation_segments)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Invalidate downstream outputs
    inv_trans = 0
    inv_aud = 0
    if trans_count > 0:
        db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).update(
            {TranslationSegment.is_outdated: True}
        )
        inv_trans = trans_count
    if audio_count > 0:
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).update(
            {GeneratedAudio.is_outdated: True}
        )
        inv_aud = audio_count
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    # Preserve approved English/Khmer provenance before changing transcript rows.
    old_segments = {segment.id: segment for segment in curr_segs}
    existing_trans = db.query(TranslationSegment).filter(
        TranslationSegment.project_id == project_id
    ).order_by(TranslationSegment.segment_order.asc()).all()
    previous_source = {}
    for translation in existing_trans:
        previous = old_segments.get(translation.transcript_segment_id)
        previous_source[translation.id] = (
            translation.source_text or (previous.text if previous else ""),
            translation.start_time if translation.start_time is not None else (previous.start_time if previous else None),
            translation.end_time if translation.end_time is not None else (previous.end_time if previous else None),
        )
        translation.transcript_segment_id = None
    db.flush()

    db.query(SubtitleSegment).filter(SubtitleSegment.project_id == project_id).update(
        {SubtitleSegment.is_source_outdated: True}
    )

    # Replace TranscriptSegment rows
    db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete()
    saved_segs: List[TranscriptSegment] = []
    for s in new_segs:
        words_data = json.dumps([w.to_dict() for w in s.words], ensure_ascii=False) if s.words else None
        db_seg = TranscriptSegment(
            id=project_segment_id(project_id, s.id),
            project_id=project_id,
            segment_order=s.segment_order,
            start_time=s.start_time,
            end_time=s.end_time,
            text=s.text,
            words_json=words_data,
            is_approximate=s.is_approximate,
            is_manually_edited=False,
        )
        db.add(db_seg)
        saved_segs.append(db_seg)

    db.flush()

    # Re-group the newly segmented transcript into canonical dubbing units
    from app.services.dubbing.grouper import DubbingGrouper
    grouper = DubbingGrouper()
    new_dubbing_units = voice_aware_groups(saved_segs, existing_trans)

    # Match retained translations by unchanged source content AND interval.
    # Segment order alone can assign approved Khmer to a different English phrase.
    t_seg_map = {segment.id: segment for segment in saved_segs}
    for existing in existing_trans:
        english, start, end = previous_source[existing.id]
        existing.source_text = english
        matching = next((unit for unit in new_dubbing_units
                         if unit.combined_english_text == english
                         and start is not None and end is not None
                         and abs(unit.start_time - start) < 0.001
                         and abs(unit.end_time - end) < 0.001), None)
        if matching:
            existing.source_segment_ids = json.dumps(matching.source_segment_ids)
            existing.transcript_segment_id = matching.source_segment_ids[0]
            for identifier in matching.source_segment_ids:
                t_seg_map[identifier].dubbing_unit_id = existing.id
        # Unmatched records retain their historical source IDs and Khmer text.
        # Their explicit outdated state blocks TTS/export reuse until reviewed.

    project.segmentation_mode = mode
    db.commit()
    for s in saved_segs:
        db.refresh(s)

    return SegmentationApplyResponse(
        project_id=project_id,
        segmentation_mode=mode,
        segment_count=len(saved_segs),
        message=f"Successfully applied {mode.title()} segmentation with {len(saved_segs)} segments",
        segments=saved_segs,
        invalidated_translations=inv_trans,
        invalidated_audios=inv_aud,
    )


@router.post(
    "/{project_id}/transcript/{segment_id}/split",
    response_model=SegmentSplitResponse,
)
def split_transcript_segment(
    project_id: str,
    segment_id: str,
    payload: SegmentSplitRequest,
    db: Session = Depends(get_db),
) -> SegmentSplitResponse:
    """Manually split a transcript segment at the specified word index."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    target_seg = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.id == segment_id, TranscriptSegment.project_id == project_id)
        .first()
    )
    if not target_seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    words = None
    if target_seg.words_json:
        try:
            words = [WordTiming.from_dict(w) for w in json.loads(target_seg.words_json)]
        except Exception:
            pass

    t_seg = TranscriptionSegment(
        segment_order=target_seg.segment_order,
        start_time=target_seg.start_time,
        end_time=target_seg.end_time,
        text=target_seg.text,
        words=words,
        is_approximate=target_seg.is_approximate,
        is_manually_edited=target_seg.is_manually_edited,
    )

    try:
        s1, s2 = split_segment_at_word(t_seg, payload.word_index)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Shift following segment orders up by 1
    following = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order > target_seg.segment_order,
        )
        .all()
    )
    for f in following:
        f.segment_order += 1

    # Update target segment to s1
    target_seg.start_time = s1.start_time
    target_seg.end_time = s1.end_time
    target_seg.text = s1.text
    target_seg.words_json = json.dumps([w.to_dict() for w in s1.words], ensure_ascii=False) if s1.words else None
    target_seg.is_approximate = s1.is_approximate
    target_seg.is_manually_edited = True

    # Add s2 segment
    new_db_seg = TranscriptSegment(
        project_id=project_id,
        segment_order=s2.segment_order,
        start_time=s2.start_time,
        end_time=s2.end_time,
        text=s2.text,
        words_json=json.dumps([w.to_dict() for w in s2.words], ensure_ascii=False) if s2.words else None,
        is_approximate=s2.is_approximate,
        is_manually_edited=True,
    )
    db.add(new_db_seg)
    db.flush()
    for unit in project.translation_segments:
        ids = json.loads(unit.source_segment_ids or "[]")
        if unit.transcript_segment_id != segment_id and segment_id not in ids:
            continue
        keys = json.loads(unit.voice_source_keys or "[]")
        if f"segment:{segment_id}" in keys:
            keys.append(f"segment:{new_db_seg.id}")
            unit.voice_source_keys = json.dumps(keys)
        if ids:
            position = ids.index(segment_id) if segment_id in ids else -1
            if position >= 0:
                ids.insert(position + 1, new_db_seg.id)
                unit.source_segment_ids = json.dumps(ids)
        unit.is_outdated = True
        unit.voice_revision = (unit.voice_revision or 0) + 1
        if unit.generated_audio:
            unit.generated_audio.is_outdated = True

    # Invalidate linked translation
    linked_trans = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.project_id == project_id,
            TranslationSegment.transcript_segment_id == segment_id,
        )
        .first()
    )
    if linked_trans:
        linked_trans.is_outdated = True
        if linked_trans.generated_audio:
            linked_trans.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()

    all_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return SegmentSplitResponse(
        message="Segment successfully split into two",
        segments=all_segs,
    )


@router.post(
    "/{project_id}/transcript/{segment_id}/merge-next",
    response_model=SegmentSplitResponse,
)
def merge_transcript_segment_next(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> SegmentSplitResponse:
    """Manually merge a transcript segment with its next neighbor."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    target_seg = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.id == segment_id, TranscriptSegment.project_id == project_id)
        .first()
    )
    if not target_seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == target_seg.segment_order + 1,
        )
        .first()
    )
    if not next_seg:
        raise HTTPException(status_code=400, detail="No adjacent next segment found to merge with")

    words1 = [WordTiming.from_dict(w) for w in json.loads(target_seg.words_json)] if target_seg.words_json else None
    words2 = [WordTiming.from_dict(w) for w in json.loads(next_seg.words_json)] if next_seg.words_json else None

    t1 = TranscriptionSegment(target_seg.segment_order, target_seg.start_time, target_seg.end_time, target_seg.text, words=words1)
    t2 = TranscriptionSegment(next_seg.segment_order, next_seg.start_time, next_seg.end_time, next_seg.text, words=words2)

    try:
        choices = assignment_map(project.translation_segments)
        partition_voice(source_keys([target_seg, next_seg]), choices)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    merged = merge_adjacent_segments(t1, t2)

    target_seg.start_time = merged.start_time
    target_seg.end_time = merged.end_time
    target_seg.text = merged.text
    target_seg.words_json = json.dumps([w.to_dict() for w in merged.words], ensure_ascii=False) if merged.words else None
    target_seg.is_manually_edited = True

    # Retain source assignment provenance for legacy segments without word IDs.
    for unit in project.translation_segments:
        ids = json.loads(unit.source_segment_ids or "[]")
        if unit.transcript_segment_id not in (target_seg.id, next_seg.id) and not set(ids).intersection({target_seg.id, next_seg.id}):
            continue
        keys = json.loads(unit.voice_source_keys or "[]")
        if f"segment:{next_seg.id}" in keys:
            keys = [k for k in keys if k != f"segment:{next_seg.id}"]
            keys.append(f"segment:{target_seg.id}")
            unit.voice_source_keys = json.dumps(sorted(set(keys)))
        unit.is_outdated = True
        unit.voice_revision = (unit.voice_revision or 0) + 1
        if unit.generated_audio:
            unit.generated_audio.is_outdated = True

    # Delete next_seg
    db.delete(next_seg)

    # Shift following segment orders down by 1
    following = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order > next_seg.segment_order,
        )
        .all()
    )
    for f in following:
        f.segment_order -= 1

    # Invalidate linked translation
    linked_trans = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.project_id == project_id,
            TranslationSegment.transcript_segment_id == segment_id,
        )
        .first()
    )
    if linked_trans:
        linked_trans.is_outdated = True
        if linked_trans.generated_audio:
            linked_trans.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()

    all_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return SegmentSplitResponse(
        message="Segments successfully merged",
        segments=all_segs,
    )


def _enrich_translation_segment(
    trans_seg: TranslationSegment,
) -> TranslationSegmentResponse:
    """Enrich TranslationSegment with timing, style, explanation, and English transcript text."""
    if trans_seg.start_time is not None and trans_seg.end_time is not None:
        start_time = trans_seg.start_time
        end_time = trans_seg.end_time
        english_text = trans_seg.source_text or (trans_seg.transcript_segment.text if trans_seg.transcript_segment else None)
    else:
        start_time = trans_seg.transcript_segment.start_time if trans_seg.transcript_segment else None
        end_time = trans_seg.transcript_segment.end_time if trans_seg.transcript_segment else None
        english_text = trans_seg.transcript_segment.text if trans_seg.transcript_segment else None

    src_ids = None
    if trans_seg.source_segment_ids:
        try:
            src_ids = json.loads(trans_seg.source_segment_ids)
        except Exception:
            src_ids = None

    return TranslationSegmentResponse(
        id=trans_seg.id,
        project_id=trans_seg.project_id,
        transcript_segment_id=trans_seg.transcript_segment_id,
        segment_order=trans_seg.segment_order,
        voice_override_provider=trans_seg.voice_override_provider,
        voice_override_id=trans_seg.voice_override_id,
        effective_tts_provider=effective_voice(trans_seg.project, trans_seg)[0],
        effective_tts_voice=effective_voice(trans_seg.project, trans_seg)[1],
        voice_revision=trans_seg.voice_revision or 0,
        tts_error=trans_seg.tts_error,
        speaker_label=trans_seg.speaker_label,
        khmer_text=trans_seg.khmer_text,
        english_text=english_text,
        start_time=start_time,
        end_time=end_time,
        source_segment_ids=src_ids,
        source_text=trans_seg.source_text,
        style=getattr(trans_seg, "style", "natural") or "natural",
        explanation=getattr(trans_seg, "explanation", None),
        is_manually_edited=trans_seg.is_manually_edited,
        is_outdated=trans_seg.is_outdated,
        created_at=trans_seg.created_at,
        updated_at=trans_seg.updated_at,
    )


@router.post("/{project_id}/translate", response_model=ProcessingJobResponse)
def start_translation(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Start asynchronous English-to-Khmer translation using NLLB-200."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    # Verify transcript segments exist
    transcript_count = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .count()
    )
    if transcript_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No transcript segments found. Please transcribe audio before translating.",
        )

    # Prevent duplicate concurrent translation jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "translate",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A translation job is already in progress for this project.",
        )

    job = ProcessingJob(
        project_id=project_id,
        job_type="translate",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_translation, project_id, job.id)
    return job


@router.get("/{project_id}/translations", response_model=TranslationListResponse)
def get_translations(
    project_id: str, db: Session = Depends(get_db)
) -> TranslationListResponse:
    """Retrieve all translated segments for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segments = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )

    enriched = [_enrich_translation_segment(seg) for seg in segments]

    return TranslationListResponse(
        project_id=project_id,
        status=project.status,
        segments=enriched,
    )


@router.get("/{project_id}/translation/export")
def export_project_translation(
    project_id: str,
    format: str = Query("srt", description="Export format: 'srt', 'vtt', 'txt', 'bilingual', 'json'"),
    db: Session = Depends(get_db),
):
    """Export project translation as Khmer SRT, WebVTT, plain text, bilingual SRT, or JSON."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    trans_segs = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )
    if not trans_segs:
        raise HTTPException(status_code=400, detail="No translation segments found to export.")

    t_segs = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).all()
    t_by_id = {t.id: t for t in t_segs}
    t_by_order = {t.segment_order: t for t in t_segs}

    base_title = sanitize_filename(project.title or "project").replace(".mp4", "")
    fmt = (format or "srt").strip().lower()

    if fmt == "json":
        items = []
        for tr in trans_segs:
            t = t_by_id.get(tr.transcript_segment_id) or t_by_order.get(tr.segment_order)
            st = tr.start_time if tr.start_time is not None else (t.start_time if t else 0.0)
            et = tr.end_time if tr.end_time is not None else (t.end_time if t else (st + 2.0))
            items.append({
                "segment_order": tr.segment_order,
                "start_time": st,
                "end_time": et,
                "source_text": tr.source_text or (t.text if t else ""),
                "khmer_text": tr.khmer_text,
                "speaker_label": tr.speaker_label or (t.speaker_label if t else None),
            })
        content = json.dumps(items, ensure_ascii=False, indent=2)
        filename = f"{base_title}_translation.json"
        mime_type = "application/json; charset=utf-8"
    else:
        cues = []
        for tr in trans_segs:
            t = t_by_id.get(tr.transcript_segment_id) or t_by_order.get(tr.segment_order)
            st = tr.start_time if tr.start_time is not None else (t.start_time if t else 0.0)
            et = tr.end_time if tr.end_time is not None else (t.end_time if t else (st + 2.0))
            en_text = (tr.source_text or (t.text if t else "")).strip()
            km_text = (tr.khmer_text or "").strip()

            if fmt == "bilingual":
                cue_text = f"{en_text}\n{km_text}" if en_text else km_text
            else:
                cue_text = km_text

            cues.append(
                SubtitleCue(
                    sequence=tr.segment_order,
                    start_time=st,
                    end_time=et,
                    text=cue_text,
                )
            )

        if fmt in ("srt", "bilingual"):
            content = generate_srt(cues, prevent_overlaps=True, filter_empty=True)
            filename = f"{base_title}_bilingual.srt" if fmt == "bilingual" else f"{base_title}_translation_km.srt"
            mime_type = "text/plain; charset=utf-8"
        elif fmt == "vtt":
            content = generate_vtt(cues, prevent_overlaps=True, filter_empty=True)
            filename = f"{base_title}_translation_km.vtt"
            mime_type = "text/vtt; charset=utf-8"
        elif fmt == "txt":
            content = generate_txt(cues, filter_empty=True)
            filename = f"{base_title}_translation_km.txt"
            mime_type = "text/plain; charset=utf-8"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format '{fmt}'. Choose 'srt', 'vtt', 'txt', 'bilingual', or 'json'.",
            )

    return Response(
        content=content.encode("utf-8"),
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        },
    )


@router.post("/{project_id}/translation/import")
async def import_project_translation(
    project_id: str,
    file: Optional[UploadFile] = File(None),
    raw_content: Optional[str] = Form(None),
    auto_fit: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
):
    """Import Khmer translations from SRT, WebVTT, plain text, or JSON file."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = ""
    filename = ""
    if file is not None and getattr(file, "filename", None) and hasattr(file, "read"):
        filename = file.filename or ""
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8", errors="replace")
    elif isinstance(raw_content, str) and raw_content.strip():
        content = raw_content
        filename = "pasted_translation.txt"
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or provide raw_content.")

    content = content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Translation content is empty.")

    imported_items = []
    is_json = content.startswith(("[", "{")) or filename.lower().endswith(".json")

    if is_json:
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "segments" in data:
                data = data["segments"]
            if isinstance(data, list):
                for idx, item in enumerate(data, start=1):
                    if isinstance(item, dict):
                        km_text = (item.get("khmer_text") or item.get("khmer") or item.get("text") or "").strip()
                        en_text = (item.get("source_text") or item.get("english") or "").strip()
                        st = float(item.get("start_time") or item.get("start") or (idx - 1) * 3.0)
                        et = float(item.get("end_time") or item.get("end") or (st + 2.5))
                        if km_text or en_text:
                            imported_items.append({
                                "order": idx,
                                "khmer": km_text,
                                "source": en_text,
                                "start": max(0.0, st),
                                "end": max(st + 0.1, et),
                            })
        except Exception as e:
            logger.warning("JSON translation parse failed: %s. Attempting subtitle parser.", e)

    if not imported_items:
        try:
            res = parse_transcript_content(content, filename=filename)
            total_cues = len(res.segments)
            video_dur = project.video.duration_seconds if (project.video and project.video.duration_seconds) else None

            for idx, seg in enumerate(res.segments, start=1):
                raw_text = seg.text or ""
                # Check for bilingual lines (English on top, Khmer below)
                lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
                en_candidate = None
                km_candidate = raw_text
                if len(lines) >= 2:
                    k_idx = -1
                    l_idx = -1
                    for i, l in enumerate(lines):
                        if re.search(r"[\u1780-\u17ff]", l):
                            k_idx = i
                        elif re.search(r"[a-zA-Z]", l):
                            l_idx = i
                    if k_idx != -1 and l_idx != -1:
                        en_candidate = lines[l_idx]
                        km_candidate = lines[k_idx]

                if not res.has_timestamps or seg.start_time is None:
                    if video_dur and video_dur > 0 and total_cues > 0:
                        slot = video_dur / total_cues
                        st = round((idx - 1) * slot, 3)
                        et = round(min(video_dur, idx * slot), 3)
                    else:
                        st = round((idx - 1) * 3.0, 3)
                        et = round(idx * 3.0, 3)
                else:
                    st = max(0.0, float(seg.start_time))
                    et = max(st + 0.1, float(seg.end_time))

                imported_items.append({
                    "order": idx,
                    "khmer": km_candidate,
                    "source": en_candidate,
                    "start": st,
                    "end": et,
                })
        except TranscriptParseError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse translation file: {e}")

    if not imported_items:
        raise HTTPException(status_code=400, detail="No readable translation cues found in file.")

    # Format all imported Khmer texts
    for item in imported_items:
        if item.get("khmer"):
            item["khmer"] = KhmerTextFormatter.format(item["khmer"])

    is_manual = (auto_fit is not True)

    # Align with transcript segments
    t_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )

    pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"
    is_grouped_dubbing = (pipeline_ver in ("v2.3", "v3", "v3.0"))

    updated_count = 0
    if t_segs and is_grouped_dubbing:
        # V2.3 Dubbing Unit Alignment
        saved_voice_units = db.query(TranslationSegment).filter_by(project_id=project_id).all()
        dubbing_units = voice_aware_groups(t_segs, saved_voice_units)
        t_seg_dict = {t.id: t for t in t_segs}

        # Build mapping from dubbing unit to combined Khmer text
        unit_km_map = {}
        if len(imported_items) == len(t_segs):
            # 1-to-1 cue import matching transcript segments: coalesce member cues into dubbing units
            t_id_to_khmer = {
                t.id: (imported_items[idx]["khmer"] or "").strip()
                for idx, t in enumerate(t_segs)
            }
            for u in dubbing_units:
                parts = [t_id_to_khmer.get(sid, "") for sid in u.source_segment_ids]
                parts = [p for p in parts if p]
                unit_km_map[u.unit_order] = KhmerTextFormatter.format(" ".join(parts))
        elif len(imported_items) == len(dubbing_units):
            # Directly matched to dubbing units
            for idx, u in enumerate(dubbing_units):
                unit_km_map[u.unit_order] = KhmerTextFormatter.format(imported_items[idx]["khmer"] or "")
        else:
            # Timestamp overlap matching or proportional fallback
            has_timestamps = any(item.get("start") is not None for item in imported_items)
            for idx, u in enumerate(dubbing_units):
                matched = False
                if has_timestamps:
                    matching = [
                        item["khmer"].strip()
                        for item in imported_items
                        if item.get("khmer") and max(u.start_time, item["start"]) < min(u.end_time, item["end"])
                    ]
                    if matching:
                        unit_km_map[u.unit_order] = KhmerTextFormatter.format(" ".join(matching))
                        matched = True
                if not matched:
                    prop_idx = min(len(imported_items) - 1, int(idx * len(imported_items) / max(1, len(dubbing_units))))
                    unit_km_map[u.unit_order] = KhmerTextFormatter.format(imported_items[prop_idx]["khmer"] or "")

        existing_translations = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .all()
        )
        existing_map = {t.segment_order: t for t in existing_translations}
        retained_ids = set()

        for u in dubbing_units:
            primary_t_id = u.source_segment_ids[0] if u.source_segment_ids else None
            src_ids_json = json.dumps(u.source_segment_ids)
            km_text = unit_km_map.get(u.unit_order, "")
            existing = existing_map.get(u.unit_order)

            if existing:
                existing.khmer_text = km_text
                existing.start_time = u.start_time
                existing.end_time = u.end_time
                existing.source_segment_ids = src_ids_json
                existing.source_text = u.combined_english_text
                existing.transcript_segment_id = primary_t_id
                existing.is_manually_edited = is_manual
                existing.is_outdated = False
                trans_unit_id = existing.id
                if existing.generated_audio:
                    db.delete(existing.generated_audio)
            else:
                new_trans = TranslationSegment(
                    project_id=project_id,
                    transcript_segment_id=primary_t_id,
                    segment_order=u.unit_order,
                    start_time=u.start_time,
                    end_time=u.end_time,
                    source_segment_ids=src_ids_json,
                    source_text=u.combined_english_text,
                    khmer_text=km_text,
                    is_manually_edited=is_manual,
                    is_outdated=False,
                )
                db.add(new_trans)
                db.flush()
                trans_unit_id = new_trans.id

            # Preserve voice assignment if configured
            pair = u.voice_override
            target_unit = existing or new_trans
            if pair:
                target_unit.voice_override_provider = pair[0]
                target_unit.voice_override_id = pair[1]
                target_unit.voice_source_keys = json.dumps(sorted(source_keys(
                    [t_seg_dict[i] for i in u.source_segment_ids if i in t_seg_dict]
                )))

            retained_ids.add(trans_unit_id)

            for src_id in u.source_segment_ids:
                t_member = t_seg_dict.get(src_id)
                if t_member:
                    t_member.dubbing_unit_id = trans_unit_id

        # Clean up stale leftover translation segments
        for old_t in existing_translations:
            if old_t.id not in retained_ids:
                if old_t.generated_audio:
                    db.delete(old_t.generated_audio)
                db.delete(old_t)

        updated_count = len(dubbing_units)

    elif t_segs:
        # Legacy v1: 1-to-1 matching with t_segs
        for idx, t in enumerate(t_segs):
            if idx < len(imported_items):
                item = imported_items[idx]
                km_text = item["khmer"]
            else:
                km_text = ""

            existing_tr = (
                db.query(TranslationSegment)
                .filter(
                    TranslationSegment.project_id == project_id,
                    TranslationSegment.segment_order == t.segment_order,
                )
                .first()
            )
            if existing_tr:
                existing_tr.khmer_text = km_text
                existing_tr.transcript_segment_id = t.id
                existing_tr.start_time = t.start_time
                existing_tr.end_time = t.end_time
                existing_tr.source_text = t.text
                existing_tr.is_manually_edited = is_manual
                existing_tr.is_outdated = False
                if existing_tr.generated_audio:
                    db.delete(existing_tr.generated_audio)
            else:
                new_tr = TranslationSegment(
                    project_id=project_id,
                    transcript_segment_id=t.id,
                    segment_order=t.segment_order,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    source_text=t.text,
                    khmer_text=km_text,
                    is_manually_edited=is_manual,
                    is_outdated=False,
                )
                db.add(new_tr)
            updated_count += 1
    else:
        # No transcript segments exist: create both transcript and translation segments
        for idx, item in enumerate(imported_items, start=1):
            src_text = item.get("source") or f"Segment #{idx}"
            t = TranscriptSegment(
                project_id=project_id,
                segment_order=idx,
                start_time=item["start"],
                end_time=item["end"],
                text=src_text,
                is_manually_edited=is_manual,
            )
            db.add(t)
            db.flush()

            tr = TranslationSegment(
                project_id=project_id,
                transcript_segment_id=t.id,
                segment_order=idx,
                start_time=item["start"],
                end_time=item["end"],
                source_text=src_text,
                khmer_text=item["khmer"],
                is_manually_edited=is_manual,
                is_outdated=False,
            )
            db.add(tr)
            updated_count += 1

    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    project.status = ProjectStatus.TRANSLATED
    db.commit()

    return {
        "message": f"Successfully imported {updated_count} translation segments.",
        "segment_count": updated_count,
        "status": project.status,
    }


@router.patch(
    "/{project_id}/translations/{segment_id}",
    response_model=TranslationSegmentResponse,
)
def update_translation_segment(
    project_id: str,
    segment_id: str,
    payload: TranslationSegmentUpdate,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Manually update Khmer translation text for a single segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    clean_text = payload.khmer_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Translation text cannot be empty")

    if clean_text != segment.khmer_text:
        segment.khmer_text = clean_text
        segment.is_manually_edited = True
        segment.is_outdated = False
        if segment.generated_audio:
            segment.generated_audio.is_outdated = True
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
        db.commit()
        db.refresh(segment)

    return _enrich_translation_segment(segment)


@router.post(
    "/{project_id}/translations/{segment_id}/retranslate",
    response_model=TranslationSegmentResponse,
)
def retranslate_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Retranslate a single segment from its corresponding English transcript."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    source_en = segment.source_text or (segment.transcript_segment.text if segment.transcript_segment else None)
    if not source_en:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    # Build lightweight context from surrounding transcript segments
    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_text = f"{prev_seg.text + ' ' if prev_seg else ''}{source_en}{' ' + next_seg.text if next_seg else ''}".strip()

    provider_id = (project.translation_provider or "nllb").lower()
    style = project.translation_style or "natural"
    try:
        if provider_id == "nllb":
            provider = NLLBTranslationProvider()
        else:
            provider = get_translation_provider(provider_id)
        translated_texts = provider.translate(
            texts=[source_en],
            source_lang=project.original_language or "eng_Latn",
            target_lang=project.target_language or "khm_Khmr",
            contexts=[context_text],
            style=style,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to retranslate segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to translate segment: {str(exc)}")

    if not translated_texts or not translated_texts[0]:
        raise HTTPException(
            status_code=500, detail="Failed to generate translation for this segment"
        )

    segment.khmer_text = translated_texts[0]
    segment.style = style
    segment.explanation = None
    segment.is_manually_edited = False
    segment.is_outdated = False
    if segment.generated_audio:
        segment.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True
    db.commit()
    db.refresh(segment)

    return _enrich_translation_segment(segment)


@router.post(
    "/{project_id}/translations/{segment_id}/ai-improve",
    response_model=AIImproveResponse,
)
def ai_improve_segment(
    project_id: str,
    segment_id: str,
    payload: AIImproveRequest,
    db: Session = Depends(get_db),
) -> AIImproveResponse:
    """Use AI LLM (Gemini) to improve, naturalize, or shorten a translation segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.transcript_segment or not segment.transcript_segment.text:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    # Calculate target duration if not provided
    target_duration = payload.target_duration
    if target_duration is None and segment.transcript_segment:
        target_duration = segment.transcript_segment.end_time - segment.transcript_segment.start_time

    # Build surrounding context
    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_parts = []
    if prev_seg:
        context_parts.append(f"Previous English: {prev_seg.text}")
    context_parts.append(f"Current English: {segment.transcript_segment.text}")
    if next_seg:
        context_parts.append(f"Next English: {next_seg.text}")
    context_str = " | ".join(context_parts)

    provider_id = (
        project.translation_provider
        if project.translation_provider and project.translation_provider != "nllb"
        else get_active_ai_provider_name()
    )
    try:
        provider = get_translation_provider(provider_id)
        result = provider.improve_translation(
            english_text=segment.transcript_segment.text,
            current_khmer_text=segment.khmer_text,
            context=context_str,
            target_duration=target_duration,
            style=payload.style or project.translation_style or "natural",
            custom_prompt=payload.custom_prompt,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to AI improve segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"AI improve failed: {str(exc)}")

    return AIImproveResponse(
        segment_id=segment.id,
        original_text=segment.transcript_segment.text,
        current_khmer_text=segment.khmer_text,
        improved_khmer_text=result.improved_khmer_text,
        explanation=result.explanation,
        style=result.style,
        provider=getattr(provider, "name", "gemini"),
        model=getattr(provider, "model", "gemini-3.5-flash"),
    )


@router.post(
    "/{project_id}/translations/{segment_id}/alternatives",
    response_model=AlternativesResponse,
)
def get_translation_alternatives(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> AlternativesResponse:
    """Generate 3 structured translation alternatives (Natural, Simple, Short) using AI LLM."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.transcript_segment or not segment.transcript_segment.text:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    target_duration = (
        segment.transcript_segment.end_time - segment.transcript_segment.start_time
        if segment.transcript_segment
        else None
    )

    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_parts = []
    if prev_seg:
        context_parts.append(f"Previous: {prev_seg.text}")
    context_parts.append(f"Current: {segment.transcript_segment.text}")
    if next_seg:
        context_parts.append(f"Next: {next_seg.text}")
    context_str = " | ".join(context_parts)

    provider_id = (
        project.translation_provider
        if project.translation_provider and project.translation_provider != "nllb"
        else get_active_ai_provider_name()
    )
    try:
        provider = get_translation_provider(provider_id)
        alts = provider.generate_alternatives(
            english_text=segment.transcript_segment.text,
            current_khmer_text=segment.khmer_text,
            context=context_str,
            target_duration=target_duration,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to generate alternatives for segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"Alternatives generation failed: {str(exc)}")

    return AlternativesResponse(
        segment_id=segment.id,
        english_text=segment.transcript_segment.text,
        current_khmer_text=segment.khmer_text,
        alternatives=[
            AlternativeOption(
                style=alt.style,
                label=alt.label,
                khmer_text=alt.khmer_text,
                explanation=alt.explanation,
            )
            for alt in alts
        ],
    )


@router.post(
    "/{project_id}/translations/{segment_id}/apply",
    response_model=TranslationSegmentResponse,
)
def apply_translation_suggestion(
    project_id: str,
    segment_id: str,
    payload: ApplyTranslationRequest,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Apply an AI suggestion or alternative to a translation segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    clean_text = payload.khmer_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Translation text cannot be empty")

    segment.khmer_text = clean_text
    if payload.style:
        segment.style = payload.style
    if payload.explanation is not None:
        segment.explanation = payload.explanation
    segment.is_manually_edited = True
    segment.is_outdated = False

    # Mark generated audio as outdated so user regenerates speech
    if segment.generated_audio:
        segment.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()
    db.refresh(segment)

    return _enrich_translation_segment(segment)


def _enrich_generated_audio(
    audio: GeneratedAudio, project_id: str
) -> GeneratedAudioResponse:
    """Enrich GeneratedAudio with segment order, khmer text, and streaming URL."""
    segment_order = (
        audio.translation_segment.segment_order if audio.translation_segment else None
    )
    khmer_text = (
        audio.translation_segment.khmer_text if audio.translation_segment else None
    )
    audio_url = (
        f"/api/projects/{project_id}/tts/{audio.translation_segment_id}/audio"
        if audio.translation_segment_id
        else None
    )
    return GeneratedAudioResponse(
        id=audio.id,
        project_id=audio.project_id,
        translation_segment_id=audio.translation_segment_id,
        segment_order=segment_order,
        khmer_text=khmer_text,
        audio_path=audio.audio_path,
        duration_seconds=audio.duration_seconds,
        provider=audio.provider,
        voice=audio.voice,
        voice_revision=audio.voice_revision,
        is_outdated=not audio_matches_selection(audio.project, audio.translation_segment, audio),
        created_at=audio.created_at,
        updated_at=audio.updated_at,
        audio_url=audio_url,
    )


@router.post("/{project_id}/tts", response_model=ProcessingJobResponse)
def start_tts(
    project_id: str,
    background_tasks: BackgroundTasks,
    auto_clone_speakers: bool = False,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Trigger background text-to-speech generation for all translated Khmer segments."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    _voice_mutation_allowed(db, project_id)
    translation_count = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .count()
    )
    if translation_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No Khmer translation segments found. Please translate transcript first.",
        )

    if auto_clone_speakers:
        spk_count = db.query(ProjectSpeaker).filter(ProjectSpeaker.project_id == project_id).count()
        if spk_count == 0:
            try:
                diarizer = AudioDiarizer()
                diarizer.diarize_project(db=db, project_id=project_id, min_speakers=1, max_speakers=6)
                extractor = VideoVoiceExtractor()
                clone_res = extractor.clone_speaker_voices(project_id=project_id, db=db, store_in_voice_studio=False)
                if len(clone_res) == 1:
                    project.tts_provider = "voxcpm"
                    project.tts_voice = clone_res[0]["voice_profile_id"]
                    db.commit()
            except Exception as e:
                logger.warning("Auto-clone speakers before TTS failed for project %s: %s", project_id, e)

    # Check for existing pending/running job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "tts",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="tts",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    project.status = ProjectStatus.GENERATING_VOICE
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_tts, project_id, job.id)
    return job


@router.get("/{project_id}/generated-audio", response_model=GeneratedAudioListResponse)
def get_generated_audio(
    project_id: str,
    db: Session = Depends(get_db),
) -> GeneratedAudioListResponse:
    """Retrieve all generated audio records for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    audios = (
        db.query(GeneratedAudio)
        .join(TranslationSegment, GeneratedAudio.translation_segment_id == TranslationSegment.id)
        .filter(GeneratedAudio.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )

    enriched = [_enrich_generated_audio(a, project_id) for a in audios]
    total_duration = sum(a.duration_seconds or 0.0 for a in enriched)
    trans_count = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
    current_cnt = sum(1 for a in enriched if not a.is_outdated)
    outdated_cnt = sum(1 for a in enriched if a.is_outdated)
    missing_cnt = max(0, trans_count - len(enriched))

    return GeneratedAudioListResponse(
        project_id=project_id,
        status=project.status,
        audios=enriched,
        total_duration_seconds=round(total_duration, 2),
        current_count=current_cnt,
        outdated_count=outdated_cnt,
        missing_count=missing_cnt,
    )


@router.post(
    "/{project_id}/tts/{segment_id}/regenerate",
    response_model=GeneratedAudioResponse,
)
def regenerate_audio_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> GeneratedAudioResponse:
    """Regenerate Khmer speech audio for a specific segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.khmer_text or not segment.khmer_text.strip():
        raise HTTPException(status_code=400, detail="Cannot synthesize empty Khmer text")

    _voice_mutation_allowed(db, project_id)
    generation_revision = segment.voice_revision
    try:
        provider_name, voice_name = effective_voice(project, segment)
        validate_voice(db, provider_name, voice_name, legacy=not segment.voice_override_id)
        provider = get_tts_provider(provider_name)
        audio_record = synthesize_segment_audio(
            project_id=project_id,
            segment=segment,
            provider=provider,
            db=db,
            voice=voice_name,
        )
        from app.services.dubbing.duration_repair import DurationRepairService
        DurationRepairService().repair_project(project_id, db, segment_ids={segment_id})
        db.refresh(audio_record)
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
            db.commit()
    except Exception as e:
        logger.error("Failed to regenerate audio segment %s: %s", segment_id, e)
        db.rollback()
        db.query(TranslationSegment).filter_by(id=segment_id, voice_revision=generation_revision).update(
            {TranslationSegment.tts_error: str(e)}, synchronize_session=False)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to generate speech: {e}")

    return _enrich_generated_audio(audio_record, project_id)


@router.api_route("/{project_id}/tts/{segment_id}/audio", methods=["GET", "HEAD"])
def stream_audio_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
):
    """Stream synthesized MP3 audio for browser playback with Range request support."""
    audio_record = (
        db.query(GeneratedAudio)
        .filter(
            GeneratedAudio.project_id == project_id,
            GeneratedAudio.translation_segment_id == segment_id,
        )
        .first()
    )
    if not audio_record:
        raise HTTPException(status_code=404, detail="Generated audio record not found")

    file_path = resolve_audio_file(project_id, segment_id, audio_record.audio_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"tts_{project_id}_{segment_id}.mp3",
        content_disposition_type="inline",
    )


@router.post("/{project_id}/export", response_model=ProcessingJobResponse)
def start_dubbing_export(
    project_id: str,
    background_tasks: BackgroundTasks,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    trim_silence: bool = Query(True),
    fill_mode: str = Query("natural"),
    overflow_policy: str = Query("allow_overlap"),
    strict_validation: bool = Query(False),
    preserve_bgm: bool = Query(False, description="Preserve background music & SFX with audio ducking"),
    ducking_preset: str = Query("balanced", description="Ducking preset: light, balanced, strong, mute"),
    bgm_volume: float = Query(0.35, ge=0.0, le=1.5, description="Background music volume (0.0 to 1.5)"),
    attenuate_center_vocals: bool = Query(True, description="Attenuate original center-channel vocals on stereo audio"),
    aspect_ratio: str = Query("original", description="Target video aspect ratio: original, 9:16, 1:1, 16:9"),
    reframe_mode: str = Query("blur_pillar", description="Reframing mode: blur_pillar, center_crop, fit_black"),
    burn_subtitles: bool = Query(False, description="Burn stylized subtitles directly into exported video"),
    subtitle_style: str = Query("tiktok_yellow", description="Subtitle styling preset: tiktok_yellow, classic_white, boxed_black, headline_bold"),
    subtitle_language: str = Query("km", description="Subtitle language: km (Khmer), en (English), bilingual (both)"),
    subtitle_font: Optional[str] = Query(None, description="Optional custom Khmer font name (Khmer OS Battambang, Khmer OS Muol, etc.)"),
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Trigger background audio synchronization and dubbed video export."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Original video file is missing or not uploaded.",
        )

    translation_segments = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )
    if not translation_segments:
        raise HTTPException(
            status_code=400,
            detail="No Khmer translation segments found. Please translate transcript first.",
        )

    # Validate that every segment has generated audio and none is outdated
    for trans_seg in translation_segments:
        audio = trans_seg.generated_audio
        if not audio:
            audio = (
                db.query(GeneratedAudio)
                .filter(GeneratedAudio.translation_segment_id == trans_seg.id)
                .first()
            )
        if not audio:
            raise HTTPException(
                status_code=400,
                detail=f"Missing generated audio for segment #{trans_seg.segment_order}. Please generate audio first.",
            )
        if not audio_matches_selection(project, trans_seg, audio):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Generated audio for segment #{trans_seg.segment_order} is outdated "
                    f"because translation text was modified. Please regenerate audio before export."
                ),
            )

    # Check for active running export job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "dub",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="dub",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    project.status = ProjectStatus.SYNCHRONIZING
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        process_dubbing,
        project_id,
        job.id,
        max_tempo_factor=max_tempo,
        trim_silence=trim_silence,
        fill_mode=fill_mode,
        overflow_policy=overflow_policy,
        strict_validation=strict_validation,
        preserve_bgm=preserve_bgm,
        ducking_preset=ducking_preset,
        bgm_volume=bgm_volume,
        attenuate_center_vocals=attenuate_center_vocals,
        aspect_ratio=aspect_ratio,
        reframe_mode=reframe_mode,
        burn_subtitles=burn_subtitles,
        subtitle_style=subtitle_style,
        subtitle_language=subtitle_language,
        subtitle_font=subtitle_font,
    )
    return job


@router.get("/{project_id}/export/status", response_model=ExportStatusResponse)
def get_export_status(
    project_id: str,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    db: Session = Depends(get_db),
) -> ExportStatusResponse:
    """Check export readiness, current job status, timing conflicts, and media details."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    dub_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.project_id == project_id, ProcessingJob.job_type == "dub")
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    is_ready = bool(
        video and video.exported_video_path and Path(video.exported_video_path).exists()
    )
    is_outdated = bool(video and video.is_export_outdated)

    video_url = f"/api/projects/{project_id}/export/video" if is_ready else None
    download_url = f"/api/projects/{project_id}/export/download" if is_ready else None

    # Calculate any timing conflicts from current segments
    pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"
    timing_summary: Optional[Dict[str, Any]] = None
    timing_conflicts: List[TimingConflictResponse] = []

    # Calculate audio freshness status across translation units
    trans_units = project.translation_segments or []
    total_units = len(trans_units)
    current_cnt = 0
    outdated_cnt = 0
    missing_cnt = 0

    for tu in trans_units:
        aud = tu.generated_audio
        if aud and audio_matches_selection(project, tu, aud) and aud.audio_path:
            current_cnt += 1
        elif aud and not audio_matches_selection(project, tu, aud):
            outdated_cnt += 1
        else:
            missing_cnt += 1

    audio_status_obj = AudioStatusSummary(
        total_dubbing_units=total_units,
        current=current_cnt,
        outdated=outdated_cnt,
        missing=missing_cnt,
    )

    if pipeline_ver in ("v2", "v2.1", "v2.2", "v2.3") and project.translation_segments:
        from app.services.dubbing.timing_optimizer import TimingOptimizerService
        optimizer = TimingOptimizerService(max_tempo=max_tempo)
        analyses = optimizer.analyze_timeline(project_id, db, max_tempo=max_tempo)

        fitted_naturally = sum(1 for a in analyses if a.status == "natural")
        speed_adjusted = sum(1 for a in analyses if a.status == "speed_adjusted")
        unresolved_items = [a for a in analyses if a.status == "needs_optimization" and a.overflow_seconds > 0.05]

        timing_conflicts = [
            TimingConflictResponse(
                segment_order=u.segment_order,
                transcript_segment_id=u.transcript_segment_id,
                start_time=u.start_time,
                end_time=u.end_time,
                original_duration=u.slot_duration,
                khmer_duration=u.raw_duration,
                available_window=u.available_window,
                effective_window=u.effective_window,
                safety_margin_seconds=optimizer.safety_margin_seconds,
                required_tempo=u.required_tempo,
                max_tempo_factor=max_tempo,
                tempo_factor=u.tempo_factor,
                overflow_seconds=u.overflow_seconds,
                suggested_action=(
                    f"Shorten the Khmer translation for Segment #{u.segment_order} by approximately "
                    f"{max(1, math.ceil(u.overflow_seconds / 0.35))} word(s) (~{u.overflow_seconds:.1f}s excess), regenerate audio, and retry export."
                ),
                message=(
                    f"Segment #{u.segment_order} ({u.raw_duration:.1f}s) exceeds available window "
                    f"({u.available_window:.2f}s raw, {u.effective_window:.2f}s effective with {int(optimizer.safety_margin_seconds * 1000)}ms safety margin) "
                    f"by {u.overflow_seconds:.1f}s even at {max_tempo}x speed."
                ),
            )
            for u in unresolved_items
        ]

        if outdated_cnt > 0 or missing_cnt > 0:
            status_label = "speech_generation_required"
        elif len(unresolved_items) == 0:
            status_label = "ready"
        else:
            status_label = "review_required"

        timing_summary = {
            "alignment_review_units": sum(
                a.local_overflow_seconds > 0.05 or abs(a.alignment_delay_seconds) > 0.5
                for a in analyses
            ),
            "schedule": [
                {
                    "translation_segment_id": a.translation_segment_id,
                    "segment_order": a.segment_order,
                    "local_overflow_seconds": a.local_overflow_seconds,
                    "alignment_delay_seconds": a.alignment_delay_seconds,
                    "scheduled_start": a.scheduled_start,
                    "scheduled_end": a.scheduled_end,
                    "processed_duration": a.processed_duration,
                    "tempo_factor": a.tempo_factor,
                    "status": a.status,
                    "overflow_seconds": a.overflow_seconds,
                }
                for a in analyses
            ],
            "total_segments": len(analyses),
            "fitted_naturally": fitted_naturally,
            "fitted_without_changes": fitted_naturally,
            "speed_adjusted": speed_adjusted,
            "sentence_optimized": 0,
            "automatically_optimized": speed_adjusted,
            "synchronized_successfully": len(analyses) - len(unresolved_items),
            "unresolved_conflicts": len(unresolved_items),
            "status": status_label,
            "audio_status": audio_status_obj.model_dump(),
        }
    elif project.translation_segments:
        target_dur = float(video.duration_seconds or 0.0) if video else 0.0
        sorted_trans = sorted(project.translation_segments, key=lambda s: s.segment_order)
        for idx, trans_seg in enumerate(sorted_trans):
            t_seg = trans_seg.transcript_segment
            audio_rec = trans_seg.generated_audio
            if t_seg and audio_rec and audio_rec.duration_seconds:
                start_time = max(0.0, float(t_seg.start_time))
                end_time = max(start_time, float(t_seg.end_time))
                orig_dur = max(0.1, end_time - start_time)

                if idx < len(sorted_trans) - 1:
                    next_t = sorted_trans[idx + 1].transcript_segment
                    next_start = float(next_t.start_time) if next_t else end_time
                    if next_start > start_time:
                        avail_window = min(next_start - start_time, target_dur - start_time) if target_dur > 0 else (next_start - start_time)
                    else:
                        avail_window = orig_dur
                else:
                    avail_window = (target_dur - start_time) if target_dur > 0 else orig_dur

                avail_window = max(0.1, avail_window)
                raw_dur = float(audio_rec.duration_seconds)

                if raw_dur > avail_window:
                    safety_margin = 0.05
                    effective_window = max(0.05, round(avail_window - safety_margin, 3))
                    required_tempo = round(raw_dur / effective_window, 2)
                    if required_tempo > max_tempo:
                        adjusted_est = raw_dur / max_tempo
                        overflow = round(adjusted_est - effective_window, 2)
                        if overflow > 0.05:
                            est_words = max(1, math.ceil(overflow / 0.35))
                            action = (
                                f"Shorten the Khmer translation for Segment #{t_seg.segment_order} by approximately "
                                f"{est_words} word(s) (~{overflow:.1f}s excess), regenerate audio, and retry export."
                            )
                            timing_conflicts.append(
                                TimingConflictResponse(
                                    segment_order=t_seg.segment_order,
                                    transcript_segment_id=t_seg.id,
                                    start_time=round(start_time, 2),
                                    end_time=round(end_time, 2),
                                    original_duration=round(orig_dur, 2),
                                    khmer_duration=round(raw_dur, 2),
                                    available_window=round(avail_window, 2),
                                    effective_window=round(effective_window, 2),
                                    safety_margin_seconds=safety_margin,
                                    required_tempo=required_tempo,
                                    max_tempo_factor=max_tempo,
                                    tempo_factor=max_tempo,
                                    overflow_seconds=overflow,
                                    suggested_action=action,
                                    message=(
                                        f"Segment #{t_seg.segment_order} ({raw_dur:.1f}s) exceeds available window "
                                        f"({avail_window:.2f}s raw, {effective_window:.2f}s effective with {int(safety_margin * 1000)}ms safety margin) "
                                        f"by {overflow:.1f}s even at {max_tempo}x speed. "
                                        f"{action}"
                                    ),
                                )
                            )

    job_resp = ProcessingJobResponse.model_validate(dub_job) if dub_job else None

    return ExportStatusResponse(
        project_id=project_id,
        status=project.status,
        job=job_resp,
        is_export_ready=is_ready,
        is_export_outdated=is_outdated,
        exported_video_path=video.exported_video_path if video else None,
        audio_timeline_path=video.audio_timeline_path if video else None,
        exported_duration_seconds=video.exported_duration_seconds if video else None,
        exported_file_size_bytes=video.exported_file_size_bytes if video else None,
        timing_conflicts=timing_conflicts,
        timing_summary=timing_summary,
        audio_status=audio_status_obj,
        pipeline_version=pipeline_ver,
        video_url=video_url,
        download_url=download_url,
    )


@router.post("/{project_id}/dubbing/auto-fit", response_model=ExportStatusResponse)
def auto_fit_project_timing(
    project_id: str,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    db: Session = Depends(get_db),
) -> ExportStatusResponse:
    """Automatically shorten Khmer translations and re-synthesize speech to fit within video timestamps."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    auto_fit_service = AutoFitService()
    auto_fit_service.auto_fit_project(project_id, db, max_tempo=max_tempo)

    return get_export_status(project_id=project_id, max_tempo=max_tempo, db=db)


@router.api_route("/{project_id}/export/video", methods=["GET", "HEAD"])
def stream_exported_video(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Stream or preview the exported Khmer-dubbed MP4 video file with HTTP byte ranges."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.exported_video_path or not Path(video.exported_video_path).exists():
        raise HTTPException(status_code=404, detail="Exported dubbed video not found")

    return FileResponse(
        video.exported_video_path,
        media_type="video/mp4",
        filename=f"dubbed_{project_id}.mp4",
    )


@router.get("/{project_id}/export/download")
def download_exported_video(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Download the exported Khmer-dubbed MP4 video file as an attachment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    if not video or not video.exported_video_path or not Path(video.exported_video_path).exists():
        raise HTTPException(status_code=404, detail="Exported dubbed video not found")

    safe_title = sanitize_filename(project.title).replace(".mp4", "")
    download_filename = f"dubbed_{safe_title}.mp4"

    return FileResponse(
        path=video.exported_video_path,
        media_type="video/mp4",
        filename=download_filename,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


