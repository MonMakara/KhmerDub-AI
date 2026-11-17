import hashlib
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    get_voice_profile_audio_path,
    sanitize_project_id,
)
from app.core.timezone import get_cambodia_now_naive
from app.models.project import Project, Video, TranscriptSegment, TranslationSegment
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.voice.inspector import AudioQualityInspector

logger = logging.getLogger(__name__)


@dataclass
class CloneCandidate:
    candidate_id: str
    segment_order: int
    segment_ids: List[str]
    start_time: float
    end_time: float
    duration: float
    text: str
    score: float
    preview_url: str = ""


class VideoVoiceExtractor:
    """Service to discover candidate speech segments in a video,
    extract high-fidelity reference audio slices, and create authorized
    VoxCPM voice profiles for project dubbing.
    """

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        inspector: Optional[AudioQualityInspector] = None,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.inspector = inspector or AudioQualityInspector(ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)

    def resolve_source_audio_path(self, project: Project) -> Path:
        """Resolve the cleanest audio file available for the project video."""
        video = project.video
        if not video:
            raise ValueError(f"Project '{project.id}' has no associated video.")

        # 1. Prefer extracted mono/stereo audio track if present
        if video.extracted_audio_path:
            p = Path(video.extracted_audio_path)
            if p.exists() and p.stat().st_size > 0:
                return p

        # 2. Fall back to original video file
        if video.file_path:
            p = Path(video.file_path)
            if p.exists() and p.stat().st_size > 0:
                return p

        # 3. Fall back to project.original_video_path
        if project.original_video_path:
            p = Path(project.original_video_path)
            if p.exists() and p.stat().st_size > 0:
                return p

        raise FileNotFoundError(f"No valid source media found for project '{project.id}'.")

    def find_candidates(self, project: Project, max_candidates: int = 5) -> List[CloneCandidate]:
        """Analyze project transcript segments and return ranked candidate speech clips
        suitable for voice cloning conditioning.
        """
        segments: List[TranscriptSegment] = sorted(
            project.transcript_segments,
            key=lambda s: (s.start_time, s.segment_order),
        )
        if not segments:
            return []

        candidates: List[CloneCandidate] = []
        n = len(segments)

        # 1. Evaluate single segments
        for idx, seg in enumerate(segments):
            dur = max(0.0, seg.end_time - seg.start_time)
            text = (seg.text or "").strip()
            words = text.split()
            word_count = len(words)

            if dur < 1.0 or word_count < 2:
                continue

            score = 50.0

            # Duration scoring: optimal VoxCPM reference length is 4.0s - 7.0s
            if 4.0 <= dur <= 7.0:
                score += 40.0
            elif 3.0 <= dur < 4.0:
                score += 30.0
            elif 7.0 < dur <= 10.0:
                score += 25.0
            elif 2.0 <= dur < 3.0:
                score += 15.0
            else:
                score += 5.0

            # Word density check (2.0 - 4.0 words/sec is typical natural speech)
            wps = word_count / max(0.5, dur)
            if 1.5 <= wps <= 4.0:
                score += 10.0
            elif wps > 5.5 or wps < 0.8:
                score -= 15.0

            # Punctuation / lexical completion bonus
            if text.endswith((".", "!", "?")):
                score += 5.0

            cand_id = f"seg_{seg.segment_order}"
            preview_url = f"/api/projects/{project.id}/voice/preview-candidate?start_time={seg.start_time:.2f}&end_time={seg.end_time:.2f}"
            candidates.append(
                CloneCandidate(
                    candidate_id=cand_id,
                    segment_order=seg.segment_order,
                    segment_ids=[seg.id],
                    start_time=round(seg.start_time, 2),
                    end_time=round(seg.end_time, 2),
                    duration=round(dur, 2),
                    text=text,
                    score=round(score, 1),
                    preview_url=preview_url,
                )
            )

        # 2. Evaluate 2-segment connected phrase windows (useful when individual segments are short)
        for idx in range(n - 1):
            s1 = segments[idx]
            s2 = segments[idx + 1]
            dur1 = s1.end_time - s1.start_time
            dur2 = s2.end_time - s2.start_time
            gap = s2.start_time - s1.end_time

            # Ensure both segments contain sufficient speech (>= 1.0s and >= 2 words)
            w1 = len((s1.text or "").split())
            w2 = len((s2.text or "").split())
            if dur1 < 1.0 or dur2 < 1.0 or w1 < 2 or w2 < 2:
                continue

            # Only merge if pause between them is short (< 0.45s) and combined duration is optimal
            if 0.0 <= gap <= 0.45 and (dur1 < 3.8 or dur2 < 3.8):
                combined_dur = s2.end_time - s1.start_time
                if 3.5 <= combined_dur <= 8.5:
                    combined_text = f"{(s1.text or '').strip()} {(s2.text or '').strip()}"
                    score = 80.0
                    if 4.0 <= combined_dur <= 6.5:
                        score += 15.0

                    cand_id = f"merged_{s1.segment_order}_{s2.segment_order}"
                    preview_url = f"/api/projects/{project.id}/voice/preview-candidate?start_time={s1.start_time:.2f}&end_time={s2.end_time:.2f}"
                    candidates.append(
                        CloneCandidate(
                            candidate_id=cand_id,
                            segment_order=s1.segment_order,
                            segment_ids=[s1.id, s2.id],
                            start_time=round(s1.start_time, 2),
                            end_time=round(s2.end_time, 2),
                            duration=round(combined_dur, 2),
                            text=combined_text,
                            score=round(score, 1),
                            preview_url=preview_url,
                        )
                    )

        # Sort descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:max_candidates]

    def extract_speech_slice(
        self,
        source_media_path: Path,
        start_time: float,
        end_time: float,
        output_path: Path,
        min_duration: float = 3.2,
        target_sample_rate: int = 48000,
    ) -> Path:
        """Extract a slice of speech from source media and format it as 48kHz mono 16-bit PCM WAV.
        Guarantees minimum duration by padding symmetrically if necessary, and applies 15ms
        boundary micro-fades to eliminate clicks and pops.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        st = max(0.0, float(start_time))
        et = max(st + 0.1, float(end_time))
        dur = et - st

        # Symmetrically expand if shorter than min_duration required by VoxCPM reference conditioner
        if dur < min_duration:
            extra = min_duration - dur
            pad = extra / 2.0
            st = max(0.0, st - pad)
            et = st + min_duration

        audio_filters = (
            "highpass=f=75,lowpass=f=12000,afftdn=nf=-25,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "afade=t=in:ss=0:d=0.015,areverse,afade=t=in:ss=0:d=0.015,areverse"
        )
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", f"{st:.3f}",
            "-to", f"{et:.3f}",
            "-i", str(source_media_path),
            "-vn", "-sn",
            "-ar", str(target_sample_rate),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-af", audio_filters,
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to extract speech slice: {res.stderr}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Extracted speech slice was not created or is empty at {output_path}")

        return output_path

    def clone_voice_from_video(
        self,
        project_id: str,
        db: Session,
        segment_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        voice_name: Optional[str] = None,
        set_as_project_voice: bool = True,
        store_in_voice_studio: bool = True,
    ) -> VoiceProfile:
        """Extract speech reference audio from the project video and register an authorized
        custom VoiceProfile for Khmer voice cloning.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        source_media = self.resolve_source_audio_path(project)

        clip_start = start_time
        clip_end = end_time
        ref_text = ""

        # If explicit start/end not provided, resolve from segment_id or auto-detect best candidate
        if clip_start is None or clip_end is None or (clip_end - clip_start) < 0.5:
            if segment_id:
                seg = db.query(TranscriptSegment).filter(
                    TranscriptSegment.id == segment_id,
                    TranscriptSegment.project_id == project_id,
                ).first()
                if not seg:
                    raise ValueError(f"Transcript segment '{segment_id}' not found in project.")
                clip_start = seg.start_time
                clip_end = seg.end_time
                ref_text = seg.text or ""
            else:
                candidates = self.find_candidates(project, max_candidates=1)
                if not candidates:
                    raise ValueError(
                        "No suitable speech segments found in video transcript to clone. "
                        "Please specify start_time and end_time manually."
                    )
                best = candidates[0]
                clip_start = best.start_time
                clip_end = best.end_time
                ref_text = best.text

        profile_id = str(uuid.uuid4())
        target_path = get_voice_profile_audio_path(profile_id)
        temp_extracted = settings.TEMP_DIR / f"video_clone_{profile_id}.wav"

        try:
            # 1. Extract slice with micro-fades
            self.extract_speech_slice(
                source_media_path=source_media,
                start_time=clip_start,
                end_time=clip_end,
                output_path=temp_extracted,
                min_duration=3.2,
                target_sample_rate=48000,
            )

            # 2. Inspect and normalize reference audio via AudioQualityInspector
            meta = self.inspector.normalize_reference_audio(temp_extracted, target_path)
            audio_bytes = target_path.read_bytes()
            sig_hash = hashlib.sha256(audio_bytes).hexdigest()

            # 3. Create VoiceConsent record
            clean_proj_title = project.title.strip() if project.title else "Project Video"
            speaker_label = f"Speaker ({clean_proj_title[:40]})"
            consent = VoiceConsent(
                id=str(uuid.uuid4()),
                speaker_name=speaker_label,
                authorized_by="Video Dubbing Creator",
                consent_statement=(
                    f"Authorized voice reference extraction from project video '{clean_proj_title}' "
                    f"at timestamps {clip_start:.2f}s - {clip_end:.2f}s for AI voice conditioning and Khmer dubbing."
                ),
                signature_hash=sig_hash,
                is_authorized=True,
                granted_at=get_cambodia_now_naive(),
            )
            db.add(consent)
            db.flush()

            # 4. Create VoiceProfile record
            default_name = f"{clean_proj_title[:24]} Cloned Voice"
            clean_name = (voice_name or default_name).strip()

            # Ensure unique name if profile with same name already exists
            existing_name = db.query(VoiceProfile).filter(VoiceProfile.name == clean_name).first()
            if existing_name:
                clean_name = f"{clean_name} ({profile_id[:4]})"

            voice_profile = VoiceProfile(
                id=profile_id,
                name=clean_name,
                description=f"Cloned directly from video '{clean_proj_title}' (clip: {clip_start:.1f}s - {clip_end:.1f}s).",
                gender="neutral",
                language="km",
                reference_audio_path=str(target_path),
                reference_audio_duration=meta.get("duration", round(clip_end - clip_start, 2)),
                reference_audio_sample_rate=meta.get("sample_rate", 48000),
                reference_transcript=ref_text,
                audio_format="wav",
                is_active=True,
                is_library=store_in_voice_studio,
                project_id=project_id,
                consent_id=consent.id,
            )
            db.add(voice_profile)

            # 5. Optionally apply as active voice for the project
            if set_as_project_voice:
                project.tts_provider = "voxcpm"
                project.tts_voice = profile_id
                # Flag existing synthesized audio segments as outdated so they can be regenerated with new voice
                for trans_seg in project.translation_segments:
                    if trans_seg.generated_audio:
                        trans_seg.generated_audio.is_outdated = True
                    trans_seg.is_outdated = False

            db.commit()
            db.refresh(voice_profile)
            logger.info(
                "Successfully created cloned voice profile '%s' (id=%s) from project '%s' (%.2fs - %.2fs)",
                voice_profile.name,
                voice_profile.id,
                project.id,
                clip_start,
                clip_end,
            )
            return voice_profile

        finally:
            if temp_extracted.exists():
                try:
                    temp_extracted.unlink()
                except OSError:
                    pass

    def clone_speaker_voices(
        self,
        project_id: str,
        db: Session,
        speaker_label: Optional[str] = None,
        store_in_voice_studio: bool = False,
    ) -> List[Dict[str, Any]]:
        """Clone voices from detected speakers in a multi-speaker video, with the choice
        to keep them project-scoped (no need to store in Voice Studio) or save to the global library.
        """
        from app.models.project import ProjectSpeaker
        from app.services.voice.diarizer import AudioDiarizer

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        source_media = self.resolve_source_audio_path(project)

        speakers_query = db.query(ProjectSpeaker).filter(ProjectSpeaker.project_id == project_id)
        if speaker_label:
            speakers_query = speakers_query.filter(ProjectSpeaker.speaker_label == speaker_label)
        speakers = speakers_query.order_by(ProjectSpeaker.speaker_label.asc()).all()

        if not speakers:
            raise ValueError("No speakers found to clone. Please run speaker diarization first.")

        all_transcript_segs = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.project_id == project_id)
            .order_by(TranscriptSegment.start_time.asc())
            .all()
        )

        cloned_results = []
        clean_proj_title = project.title.strip() if project.title else "Project Video"
        diarizer = AudioDiarizer()

        for spk in speakers:
            spk_segs = [s for s in all_transcript_segs if s.speaker_label == spk.speaker_label]
            if not spk_segs:
                continue

            # Pick best reference clip for this speaker (ideal duration: 3.5s - 8s)
            best_seg = None
            best_score = -1.0
            for seg in spk_segs:
                dur = seg.end_time - seg.start_time
                if dur < 0.4:
                    continue
                if 3.0 <= dur <= 9.0:
                    score = dur
                elif dur < 3.0:
                    score = dur * 0.5
                else:
                    score = max(0.1, 14.0 - dur)

                if score > best_score:
                    best_score = score
                    best_seg = seg

            if not best_seg:
                best_seg = spk_segs[0]

            clip_start = best_seg.start_time
            clip_end = best_seg.end_time
            dur = clip_end - clip_start

            # If clip is short, attempt to bridge with consecutive segment of same speaker
            if dur < 3.0:
                try:
                    seg_idx = all_transcript_segs.index(best_seg)
                    if seg_idx + 1 < len(all_transcript_segs):
                        nxt = all_transcript_segs[seg_idx + 1]
                        if nxt.speaker_label == spk.speaker_label and (nxt.start_time - clip_end) < 1.0:
                            clip_end = nxt.end_time
                except Exception:
                    pass

            profile_id = str(uuid.uuid4())
            target_path = get_voice_profile_audio_path(profile_id)
            temp_extracted = settings.TEMP_DIR / f"speaker_clone_{profile_id}.wav"

            try:
                self.extract_speech_slice(
                    source_media_path=source_media,
                    start_time=clip_start,
                    end_time=clip_end,
                    output_path=temp_extracted,
                    min_duration=3.2,
                    target_sample_rate=48000,
                )

                meta = self.inspector.normalize_reference_audio(temp_extracted, target_path)
                audio_bytes = target_path.read_bytes()
                sig_hash = hashlib.sha256(audio_bytes).hexdigest()

                consent = VoiceConsent(
                    id=str(uuid.uuid4()),
                    speaker_name=f"{spk.display_name} ({clean_proj_title[:30]})",
                    authorized_by="Video Dubbing Creator",
                    consent_statement=(
                        f"Authorized voice reference extraction for character '{spk.display_name}' "
                        f"from project video '{clean_proj_title}' ({clip_start:.2f}s - {clip_end:.2f}s) "
                        f"for Khmer multi-character voice conditioning."
                    ),
                    signature_hash=sig_hash,
                    is_authorized=True,
                    granted_at=get_cambodia_now_naive(),
                )
                db.add(consent)
                db.flush()

                clean_name = f"{spk.display_name} ({clean_proj_title[:16]})"
                existing = db.query(VoiceProfile).filter(VoiceProfile.name == clean_name).first()
                if existing:
                    clean_name = f"{clean_name} ({profile_id[:4]})"

                voice_profile = VoiceProfile(
                    id=profile_id,
                    name=clean_name,
                    description=f"Cloned for character {spk.display_name} from '{clean_proj_title}' ({clip_start:.1f}s - {clip_end:.1f}s).",
                    gender=spk.detected_gender if spk.detected_gender in ("male", "female") else "neutral",
                    language="km",
                    reference_audio_path=str(target_path),
                    reference_audio_duration=meta.get("duration", round(clip_end - clip_start, 2)),
                    reference_audio_sample_rate=meta.get("sample_rate", 48000),
                    reference_transcript=best_seg.text or "",
                    audio_format="wav",
                    is_active=True,
                    is_library=store_in_voice_studio,
                    project_id=project_id,
                    consent_id=consent.id,
                )
                db.add(voice_profile)
                db.flush()

                # Assign this voice to the speaker profile
                spk.assigned_voice_provider = "voxcpm"
                spk.assigned_voice_id = profile_id
                spk.updated_at = get_cambodia_now_naive()

                # Cascade voice override to all translation segments belonging to this speaker
                diarizer.apply_speaker_voice(
                    db=db,
                    project_id=project_id,
                    speaker_label=spk.speaker_label,
                    provider="voxcpm",
                    voice_id=profile_id,
                )

                cloned_results.append({
                    "speaker_label": spk.speaker_label,
                    "display_name": spk.display_name,
                    "voice_profile_id": profile_id,
                    "voice_profile_name": clean_name,
                    "assigned_voice_provider": "voxcpm",
                    "is_library": store_in_voice_studio,
                })

            finally:
                if temp_extracted.exists():
                    try:
                        temp_extracted.unlink()
                    except OSError:
                        pass

        db.commit()
        return cloned_results
