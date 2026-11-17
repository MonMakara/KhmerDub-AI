"""Audio cleanup lifecycle using existing ToolkitTask persistence and storage."""
import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.storage import get_toolkit_task_dir
from app.core.config import settings
from app.core.ai_guard import acquire_ai_inference_slot
from app.database.session import SessionLocal
from app.models.toolkit import ToolkitTask
from app.services.video.cleaning import AudioCleaningProcessor, CleaningCancelled, CleaningError

logger = logging.getLogger(__name__)
CLEANING_SLOT = threading.Semaphore(1)
SUBMIT_LOCK = threading.Lock()
SEPARATION_PYTHON = Path("/opt/audio-cleaning-env/bin/python")


def get_separation_python() -> Path:
    """Return the Python interpreter for Demucs speech/music separation.
    Checks:
    1. /opt/audio-cleaning-env/bin/python (baked into Docker image)
    2. settings.MODEL_CACHE_DIR / 'audio-cleaning-env' / 'bin' / 'python' (persistent Docker volume)
    """
    candidates = [
        Path("/opt/audio-cleaning-env/bin/python"),
        settings.MODEL_CACHE_DIR / "audio-cleaning-env" / "bin" / "python",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def separation_repo() -> Path:
    return settings.MODEL_CACHE_DIR / "audio_cleaning"


def capabilities() -> dict:
    sep_py = get_separation_python()
    music = sep_py.is_file() and (separation_repo() / "955717e8-8726e21a.th").is_file()
    return {
        "noise_available": bool(shutil.which("ffmpeg")),
        "music_available": music,
        "music_reason": None if music else "The local speech/music separation engine or checkpoint is not installed.",
        "noise_engine": "FFmpeg afftdn (CPU)",
        "strengths": ["light", "balanced", "strong"],
        "stream_policy": "First audio stream in file order; other tracks are not mixed into speech.",
        "progress_kind": "Estimated overall stage progress; each FFmpeg pass measures processed time.",
    }


def task_cancelled(task_id: str) -> bool:
    with SessionLocal() as db:
        task = db.get(ToolkitTask, task_id)
        return task is None or task.status not in ("pending", "processing")


def process_cleaning(task_id: str) -> None:
    acquired = False
    root = get_toolkit_task_dir(task_id)
    work = root / ".cleaning-work"
    processor = AudioCleaningProcessor()
    try:
        while not acquired:
            if task_cancelled(task_id):
                raise CleaningCancelled()
            acquired = CLEANING_SLOT.acquire(timeout=.25)
        with SessionLocal() as db:
            task = db.get(ToolkitTask, task_id)
            if task is None or task.status != "pending":
                return
            changed = db.query(ToolkitTask).filter_by(id=task_id, status="pending").update({ToolkitTask.status: "processing"})
            if changed != 1:
                return
            source = Path(task.source_file_path)
            options = json.loads(task.source_media_metadata)
            db.commit()
        cancelled = lambda: task_cancelled(task_id)

        def phase(name: str, percent: int, pass_percent: int | None = None, **extra) -> None:
            with SessionLocal() as db:
                task = db.get(ToolkitTask, task_id)
                if task is None or task.status != "processing":
                    raise CleaningCancelled()
                meta = json.loads(task.output_media_metadata or "{}")
                meta.update(phase=name, phase_progress=pass_percent, **extra)
                db.query(ToolkitTask).filter_by(id=task_id, status="processing").update({
                    ToolkitTask.progress_percentage: percent,
                    ToolkitTask.output_media_metadata: json.dumps(meta),
                })
                db.commit()

        phase("Validating media", 3)
        info = processor.inspect(source)
        free = shutil.disk_usage(root).free
        required = int(info["input_duration"] * 1_400_000 + source.stat().st_size * 2 + 100_000_000)
        if free < required:
            raise CleaningError("Not enough free disk space for safe processing and verification.")
        if options["mode"] == "music" and not capabilities()["music_available"]:
            raise CleaningError(capabilities()["music_reason"])
        work.mkdir(parents=True, exist_ok=False)
        finished = work / "finished"
        finished.mkdir()
        original = finished / "original.wav"
        cleaned = finished / "cleaned.wav"
        mp3 = finished / "cleaned.mp3"
        phase("Extracting original audio", 8, **info)
        processor.extract_original(source, original, info, cancelled,
                                   lambda p: phase("Extracting original audio", 8 + p*12//100, p))
        expected = processor.get_audio_duration(original)
        engine_info = {"engine": capabilities()["noise_engine"], "device": "cpu"}
        if options["mode"] == "noise":
            phase("Loading noise filter", 20, **engine_info)
            processor.denoise(original, cleaned, options["strength"], cancelled,
                              lambda p: phase("Removing noise", 22 + p*38//100, p))
        else:
            phase("Waiting for AI processing slot", 20)
            while True:
                if cancelled():
                    raise CleaningCancelled()
                try:
                    with acquire_ai_inference_slot("Music separation", timeout=.5):
                        phase("Loading separation model", 21)
                        engine_info = processor.separate_music(original, cleaned, finished/"background.wav",
                            work, options["strength"], separation_repo(), get_separation_python(), cancelled,
                            lambda p: phase("Separating speech and music", 22+p*38//100, p))
                    break
                except TimeoutError:
                    continue
        processor.encode_mp3(cleaned, mp3, expected, cancelled,
                             lambda p: phase("Encoding audio", 60 + p*10//100, p))
        phase("Verifying audio", 72)
        actual = processor.validate_audio(cleaned, expected, cancelled)
        processor.validate_audio(mp3, expected, cancelled)
        video_meta = {}
        video = finished / "cleaned.mp4"
        if info["has_video"]:
            video_meta = processor.export_clean_video(source, cleaned, video, info, cancelled,
                lambda p: phase("Encoding and verifying video", 76 + p*18//100, p))
        phase("Verifying output", 96)
        manifest = {
            **info, **video_meta, "mode": options["mode"], "strength": options["strength"],
            **engine_info, "phase": "Completed", "phase_progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "input_audio_duration": expected, "output_audio_duration": actual,
            "duration_difference": actual - expected,
            "files": [p.name for p in finished.iterdir()],
            "quality_notice": "Compare speech before and after. Separation may retain singing/music or affect quiet words. Strong processing can introduce artifacts; speech completeness has not been human-verified.",
        }
        # A single directory publish, followed by a conditional status transition.
        # Downloads remain unavailable unless the completed transition wins cancellation.
        with SessionLocal() as db:
            claimed = db.query(ToolkitTask).filter_by(id=task_id, status="processing").update({ToolkitTask.progress_percentage: 99})
            if claimed != 1:
                db.rollback()
                raise CleaningCancelled()
            output = root / "output"
            finished.replace(output)
            db.query(ToolkitTask).filter_by(id=task_id, status="processing").update({
                ToolkitTask.status: "completed", ToolkitTask.progress_percentage: 100,
                ToolkitTask.output_file_path: str(output / "cleaned.wav"),
                ToolkitTask.output_filename: "cleaned.wav",
                ToolkitTask.output_duration_seconds: actual,
                ToolkitTask.output_file_size_bytes: (output / "cleaned.wav").stat().st_size,
                ToolkitTask.output_media_metadata: json.dumps(manifest),
            })
            db.commit()
    except Exception as exc:
        logger.info("Audio cleanup %s ended: %s", task_id, exc, exc_info=not isinstance(exc, CleaningCancelled))
        with SessionLocal() as db:
            task = db.get(ToolkitTask, task_id)
            if task and task.status in ("pending", "processing", "cancelling"):
                task.status = "cancelled" if isinstance(exc, CleaningCancelled) else "failed"
                task.error_message = str(exc) if isinstance(exc, CleaningError) else (
                    "Processing cancelled; original preserved." if isinstance(exc, CleaningCancelled)
                    else "Audio processing failed. Original file preserved; please retry or try Light strength.")
                meta = json.loads(task.output_media_metadata or "{}")
                meta["phase"] = task.status.capitalize()
                task.output_media_metadata = json.dumps(meta)
                db.commit()
    finally:
        try:
            if work.is_dir() and work.resolve().parent == root.resolve():
                shutil.rmtree(work)
        except OSError:
            logger.exception("Could not remove owned cleanup staging files for %s", task_id)
        finally:
            if acquired:
                CLEANING_SLOT.release()
