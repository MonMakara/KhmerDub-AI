"""Persistent unit voice selection and source identity preservation."""
import json
from typing import Any

from sqlalchemy.orm import Session, object_session

from app.models.project import Project, TranslationSegment, TranscriptSegment, GeneratedAudio
from app.models.voice import VoiceProfile, VoiceConsent
from app.services.tts.exceptions import VoiceNotSupportedError
from app.services.tts.registry import (
    AVAILABLE_VOICES, DEFAULT_PROVIDER, DEFAULT_VOICE, list_supported_voices,
)


def effective_voice(project: Project, segment: TranslationSegment) -> tuple[str, str]:
    provider = segment.voice_override_provider or project.tts_provider or DEFAULT_PROVIDER
    voice = segment.voice_override_id or project.tts_voice or DEFAULT_VOICE
    if provider in ("voxcpm", "voxcpm2", "custom"):
        provider = "voxcpm"
        for prefix in ("custom:", "voxcpm:", "voxcpm2:"):
            if voice.startswith(prefix):
                voice = voice[len(prefix):]
                break
        # New overrides always store UUIDs. Resolve old project defaults which
        # historically allowed names without rewriting the legacy project.
        db = object_session(segment) or object_session(project)
        if db is not None and not segment.voice_override_id:
            profile = db.query(VoiceProfile).filter(
                (VoiceProfile.id == voice) | (VoiceProfile.name == voice),
            ).first()
            if profile:
                voice = profile.id
    return provider, voice


def voice_catalog(db: Session) -> list[dict[str, Any]]:
    """Use the existing registry and include unavailable profiles with a reason."""
    voices = list_supported_voices(db=db, language="km")
    present = {v["voice"] for v in voices if v.get("is_custom")}
    for voice in voices:
        voice["availability_reason"] = None if voice.get("is_available", True) else "Voice worker offline"
    for profile in db.query(VoiceProfile).filter(VoiceProfile.language == "km").all():
        if profile.id in present:
            continue
        consent = db.query(VoiceConsent).filter_by(id=profile.consent_id).first()
        reason = "Profile inactive" if not profile.is_active else "Speaker consent missing or revoked"
        if profile.is_active and consent and consent.is_authorized:
            reason = "Voice unavailable"
        voices.append({
            "provider": "voxcpm", "voice": profile.id, "profile_id": profile.id,
            "label": f"{profile.name} (Custom Clone)", "gender": profile.gender,
            "language": "km", "description": reason, "is_custom": True,
            "is_available": False, "availability_reason": reason,
        })
    return voices


def validate_voice(db: Session, provider: str, voice: str, *, legacy: bool = False) -> None:
    # Old stored Google projects remain processable, but cannot select Google anew.
    if legacy and provider == "gtts" and voice == "default":
        return
    # A standard voice must not wait on an unrelated offline custom worker.
    builtin = next((v for v in AVAILABLE_VOICES
                    if v["provider"] == provider and v["voice"] == voice
                    and v.get("language") == "km"), None)
    if builtin:
        if not builtin.get("is_available", True):
            raise VoiceNotSupportedError("Selected standard voice is unavailable")
        return
    selected = next((v for v in voice_catalog(db)
                     if v["provider"] == provider and v["voice"] == voice), None)
    if not selected:
        raise VoiceNotSupportedError("Select an existing Khmer-compatible voice by its registered ID.")
    if not selected.get("is_available", True):
        raise VoiceNotSupportedError(selected.get("availability_reason") or "Selected voice unavailable")


def source_keys(segments: list[Any]) -> set[str]:
    result: set[str] = set()
    for segment in segments:
        words = getattr(segment, "words", None)
        if words is None and getattr(segment, "words_json", None):
            words = json.loads(segment.words_json)
        ids = [(w.get("word_id") if isinstance(w, dict) else w.word_id) for w in words or []]
        ids = [identifier for identifier in ids if identifier]
        if ids:
            result.update(f"word:{identifier}" for identifier in ids)
        elif getattr(segment, "id", None):
            result.add(f"segment:{segment.id}")
    return result


def unit_source_keys(db: Session, segment: TranslationSegment) -> set[str]:
    ids = json.loads(segment.source_segment_ids or "[]")
    if not ids and segment.transcript_segment_id:
        ids = [segment.transcript_segment_id]
    members = db.query(TranscriptSegment).filter(
        TranscriptSegment.project_id == segment.project_id, TranscriptSegment.id.in_(ids),
    ).all()
    return source_keys(members)


def assignment_map(existing: list[TranslationSegment]) -> dict[str, tuple[str, str] | None]:
    assignments: dict[str, tuple[str, str] | None] = {}
    for segment in existing:
        if not segment.voice_override_id:
            continue
        pair = (segment.voice_override_provider, segment.voice_override_id)
        for key in json.loads(segment.voice_source_keys or "[]"):
            if key in assignments and assignments[key] != pair:
                raise ValueError("Conflicting saved voices. Reset the affected unit overrides before regrouping.")
            assignments[key] = pair
    return assignments


def partition_voice(keys: set[str], assignments: dict) -> tuple[str, str] | None:
    choices = {assignments.get(key) for key in keys}
    if len(choices) > 1:
        raise ValueError("This change would merge different voice assignments. Reset affected overrides or keep separate units.")
    return next(iter(choices), None)


def preserve_partition(segments: list[Any], existing: list[TranslationSegment]) -> None:
    if any(s.voice_override_id and not json.loads(s.voice_source_keys or "[]") for s in existing):
        raise ValueError("Reset unmapped legacy voice overrides before replacing this transcript.")
    assignments = assignment_map(existing)
    if not assignments:
        return
    covered = source_keys(segments)
    if not set(assignments).issubset(covered):
        raise ValueError("Saved voice assignments cannot be matched to the new source. Reset overrides before replacing this transcript.")
    for segment in segments:
        partition_voice(source_keys([segment]), assignments)


def voice_aware_groups(segments: list[Any], existing: list[TranslationSegment]) -> list[Any]:
    """Keep different source assignments in separate synthesis units."""
    from app.services.dubbing.grouper import DubbingGrouper

    preserve_partition(segments, existing)
    assignments = assignment_map(existing)
    normalized = []
    for segment in segments:
        normalized.append({
            "id": segment.id, "segment_order": segment.segment_order,
            "start_time": segment.start_time, "end_time": segment.end_time,
            "text": segment.text,
            "_voice_key": partition_voice(source_keys([segment]), assignments),
        })
    return DubbingGrouper().group_segments(normalized)


def set_unit_voice(db: Session, project: Project, segment: TranslationSegment,
                   provider: str | None, voice: str | None) -> None:
    if (segment.voice_override_provider, segment.voice_override_id) == (provider, voice):
        return
    keys = unit_source_keys(db, segment)
    db.query(TranslationSegment).filter_by(id=segment.id).update({
        TranslationSegment.voice_override_provider: provider,
        TranslationSegment.voice_override_id: voice,
        TranslationSegment.voice_source_keys: json.dumps(sorted(keys)) if voice else None,
        TranslationSegment.voice_revision: TranslationSegment.voice_revision + 1,
        TranslationSegment.tts_error: None,
    }, synchronize_session="fetch")
    db.query(GeneratedAudio).filter_by(translation_segment_id=segment.id).update(
        {GeneratedAudio.is_outdated: True}, synchronize_session="fetch")
    if project.video:
        project.video.is_export_outdated = True


def audio_matches_selection(project: Project, segment: TranslationSegment, audio: GeneratedAudio) -> bool:
    if audio.is_outdated or segment.is_outdated:
        return False
    if audio.voice_revision is None:
        return not segment.voice_override_id and (segment.voice_revision or 0) == 0
    return (audio.voice_revision == segment.voice_revision
            and (audio.provider, audio.voice) == effective_voice(project, segment))
