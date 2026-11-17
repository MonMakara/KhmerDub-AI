"""Isolated mixed-voice acceptance on a current uploaded full video.

Copies existing approved Khmer and media without altering their source project.
No translation inference, new model or provider is used.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

from app.database.session import SessionLocal
from app.models.project import (
    Project, Video, TranscriptSegment, TranslationSegment, ProcessingJob,
    GeneratedAudio, JobStatus, ProjectStatus,
)
from app.services.tts.registry import DEFAULT_PROVIDER, DEFAULT_VOICE
from app.services.tts.selection import (
    voice_catalog, set_unit_voice, effective_voice, audio_matches_selection,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.workers.tts import process_tts, synthesize_segment_audio

TITLE = "[Mixed voice acceptance] Bamboo Tree"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_snapshot(db, project_id: str) -> dict:
    project = db.get(Project, project_id)
    return {
        "project": {key: getattr(project, key) for key in
                    ("title", "status", "tts_provider", "tts_voice", "updated_at")},
        "translations": [{key: getattr(s, key) for key in
                          ("id", "khmer_text", "start_time", "end_time", "is_manually_edited", "updated_at")}
                         for s in project.translation_segments],
        "audio": [{"id": a.id, "path": a.audio_path, "hash": digest(Path(a.audio_path)),
                   "voice": a.voice, "outdated": a.is_outdated}
                  for a in project.generated_audios],
    }


def prepare(db) -> Project:
    existing = db.query(Project).filter_by(title=TITLE).first()
    if existing:
        return existing
    candidates = db.query(Project).join(Video).filter(~Project.title.like("[%")).all()
    source = next((p for p in candidates if p.translation_segments and
                   Path(p.video.file_path).is_file() and p.tts_provider == "edge"), None)
    if source is None:
        raise ValueError("No current uploaded video with existing Khmer translations found")
    catalog = voice_catalog(db)
    available = [v for v in catalog if v.get("is_available", True)]
    standard = [v for v in available if not v.get("is_custom")]
    if len(standard) < 2:
        raise ValueError("Two existing Khmer standard voices are required")
    custom = next((v for v in available if v.get("is_custom")), None)
    before = source_snapshot(db, source.id)
    project = Project(title=TITLE, tts_provider=DEFAULT_PROVIDER, tts_voice=DEFAULT_VOICE,
                      pipeline_version="v2.3", status=ProjectStatus.TRANSLATED,
                      segmentation_mode=source.segmentation_mode,
                      raw_transcript_json=source.raw_transcript_json)
    db.add(project)
    db.flush()
    root = Path("/app/data/projects") / project.id
    root.mkdir(parents=True, exist_ok=True)
    upload = Path("/app/data/uploads") / project.id / source.video.filename
    upload.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.video.file_path, upload)
    audio = root / "source_audio.wav"
    shutil.copy2(source.video.extracted_audio_path, audio)
    video = Video(project_id=project.id, filename=upload.name, file_path=str(upload),
                  file_size_bytes=upload.stat().st_size, duration_seconds=source.video.duration_seconds,
                  width=source.video.width, height=source.video.height,
                  video_codec=source.video.video_codec, audio_codec=source.video.audio_codec,
                  extracted_audio_path=str(audio))
    db.add(video)
    project.original_video_path = str(upload)
    members = {}
    for old in source.transcript_segments:
        new = TranscriptSegment(project_id=project.id, segment_order=old.segment_order,
                                start_time=old.start_time, end_time=old.end_time,
                                text=old.text, words_json=old.words_json,
                                is_approximate=old.is_approximate)
        db.add(new)
        db.flush()
        members[old.id] = new
    units = []
    for old in source.translation_segments:
        ids = json.loads(old.source_segment_ids or "[]") or [old.transcript_segment_id]
        new_ids = [members[i].id for i in ids if i in members]
        new = TranslationSegment(project_id=project.id, segment_order=old.segment_order,
                                 transcript_segment_id=new_ids[0] if new_ids else None,
                                 source_segment_ids=json.dumps(new_ids), source_text=old.source_text,
                                 start_time=old.start_time, end_time=old.end_time,
                                 khmer_text=old.khmer_text, is_manually_edited=True)
        db.add(new)
        db.flush()
        for i in ids:
            if i in members:
                members[i].dubbing_unit_id = new.id
        units.append(new)
    db.flush()
    for index, unit in enumerate(units):
        chosen = custom if custom and index % 7 == 2 else standard[index % 2]
        if (chosen["provider"], chosen["voice"]) != (DEFAULT_PROVIDER, DEFAULT_VOICE):
            set_unit_voice(db, project, unit, chosen["provider"], chosen["voice"])
    db.commit()
    evidence = {
        "project_id": project.id, "source_project_id": source.id,
        "source_sha256": digest(upload), "duration": video.duration_seconds,
        "source_before": before, "catalog": catalog,
        "custom_tested": bool(custom),
        "custom_status": "included" if custom else "offline or unavailable; not tested",
        "units": [{"id": u.id, "order": u.segment_order, "text": u.khmer_text,
                   "selected": effective_voice(project, u), "revision": u.voice_revision}
                  for u in units],
    }
    (root / "mixed_voice_preparation.json").write_text(json.dumps(evidence, default=str, ensure_ascii=False, indent=2))
    return project


def run(db, project: Project) -> None:
    root = Path("/app/data/projects") / project.id
    evidence = json.loads((root / "mixed_voice_preparation.json").read_text())
    job = ProcessingJob(project_id=project.id, job_type="tts", status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    process_tts(project.id, job.id, db=db)
    db.refresh(job)
    if job.status != JobStatus.COMPLETED:
        raise RuntimeError(job.error_message)
    db.expire_all()
    units = project.translation_segments
    checks = []
    processor = FFmpegVideoProcessor()
    for unit in units:
        audio = unit.generated_audio
        assert audio_matches_selection(project, unit, audio)
        assert (audio.provider, audio.voice) == effective_voice(project, unit)
        measured = processor.get_audio_duration(Path(audio.audio_path))
        assert abs(measured - audio.duration_seconds) < .001
        checks.append({"id": unit.id, "selected": effective_voice(project, unit),
                       "recorded": [audio.provider, audio.voice], "duration": measured,
                       "path": audio.audio_path, "hash": digest(Path(audio.audio_path))})
    evidence["generated_checks"] = checks
    # Only the first unit changes; every other accepted recording must be unchanged.
    selected = units[0]
    options = [v for v in voice_catalog(db) if v.get("is_available", True) and not v.get("is_custom")]
    different = next(v for v in options if (v["provider"], v["voice"]) != effective_voice(project, selected))
    set_unit_voice(db, project, selected, different["provider"], different["voice"])
    db.commit()
    assert not audio_matches_selection(project, selected, selected.generated_audio)
    synthesize_segment_audio(project.id, selected, db=db)
    for unit, check in zip(units[1:], checks[1:]):
        db.refresh(unit.generated_audio)
        assert digest(Path(unit.generated_audio.audio_path)) == check["hash"]
        assert unit.generated_audio.audio_path == check["path"]
    evidence["targeted_regeneration"] = {"unit_id": selected.id, "new_voice": effective_voice(project, selected),
                                        "other_units_unchanged": len(units)-1}
    analysis = TimingOptimizerService().analyze_timeline(project.id, db)
    evidence["schedule"] = [vars(a) for a in analysis]
    evidence["unresolved_conflicts"] = sum(a.status == "needs_optimization" and a.overflow_seconds > .05 for a in analysis)
    (root / "mixed_voice_acceptance.json").write_text(json.dumps(evidence, default=str, ensure_ascii=False, indent=2))
    result = DubbingPipeline().run(project.id, db, strict_validation=True, trim_silence=False)
    project.status = ProjectStatus.COMPLETED
    db.commit()
    evidence["export"] = vars(result.export_result)
    after = source_snapshot(db, evidence["source_project_id"])
    assert json.dumps(after, default=str, sort_keys=True) == json.dumps(evidence["source_before"], sort_keys=True)
    assert digest(Path(project.video.file_path)) == evidence["source_sha256"]
    evidence["source_project_unchanged"] = True
    evidence["human_listening"] = "not performed; voice identity is verified by provider/request metadata only"
    (root / "mixed_voice_acceptance.json").write_text(json.dumps(evidence, default=str, ensure_ascii=False, indent=2))
    print(json.dumps({"project_id": project.id, "units": len(units), "export": str(result.export_result.video_path),
                      "custom": evidence["custom_status"], "unresolved_conflicts": evidence["unresolved_conflicts"]}))


def verify_current(db, project: Project) -> None:
    """Recheck the final UI-tested state without regenerating speech."""
    root = Path("/app/data/projects") / project.id
    evidence = json.loads((root / "mixed_voice_acceptance.json").read_text())
    prepared = {u["id"]: u for u in evidence["units"]}
    prior = {u["id"]: u for u in evidence["generated_checks"]}
    checks = []
    for unit in project.translation_segments:
        audio = unit.generated_audio
        assert unit.khmer_text == prepared[unit.id]["text"]
        assert audio_matches_selection(project, unit, audio)
        checks.append({"id": unit.id, "order": unit.segment_order,
                       "selected": effective_voice(project, unit),
                       "recorded": [audio.provider, audio.voice],
                       "revision": unit.voice_revision, "audio_revision": audio.voice_revision,
                       "measured_duration": FFmpegVideoProcessor().get_audio_duration(Path(audio.audio_path)),
                       "hash": digest(Path(audio.audio_path)), "path": audio.audio_path})
    assert all(c["hash"] == prior[c["id"]]["hash"] for c in checks[1:])
    result = DubbingPipeline().run(project.id, db, strict_validation=True, trim_silence=False)
    project.status = ProjectStatus.COMPLETED
    db.commit()
    after = source_snapshot(db, evidence["source_project_id"])
    assert json.dumps(after, default=str, sort_keys=True) == json.dumps(evidence["source_before"], sort_keys=True)
    evidence["final_ui_verified_units"] = checks
    evidence["ui_targeted_regeneration_other_units_unchanged"] = len(checks)-1
    evidence["final_export"] = vars(result.export_result)
    evidence["source_project_unchanged"] = True
    (root / "mixed_voice_acceptance.json").write_text(json.dumps(evidence, default=str, ensure_ascii=False, indent=2))
    print("FINAL_CURRENT_EXPORT", result.export_result, flush=True)


if __name__ == "__main__":
    with SessionLocal() as session:
        session.get_bind().echo = False
        acceptance = prepare(session)
        print("ACCEPTANCE_PROJECT", acceptance.id, flush=True)
        if "--verify" in sys.argv:
            verify_current(session, acceptance)
        elif "--prepare" not in sys.argv:
            run(session, acceptance)
