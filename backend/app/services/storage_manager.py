import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    delete_toolkit_task_storage,
    get_toolkit_base_dir,
    get_voice_profiles_base_dir,
)
from app.core.timezone import get_cambodia_now_naive
from app.models.project import Project
from app.models.toolkit import ToolkitTask
from app.models.voice import VoiceProfile
from app.schemas.storage import (
    StorageCategoryInfo,
    StorageCleanRequest,
    StorageCleanResponse,
    StorageDiskInfo,
    StorageUsageResponse,
)

logger = logging.getLogger(__name__)


def format_bytes(size: int) -> str:
    """Format bytes to human readable string (e.g. 12.4 MB, 4.7 GB)."""
    if size <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def get_dir_size(path: Path) -> int:
    """Calculate total size of directory or file in bytes safely."""
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def count_files(path: Path) -> int:
    """Count non-symlink files in a directory safely."""
    if not path.exists() or not path.is_dir():
        return 0
    count = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    count += 1
            except OSError:
                continue
    except OSError:
        pass
    return count


def get_storage_usage(db: Optional[Session] = None) -> StorageUsageResponse:
    """Collect accurate disk usage, categorization, and cleanable space metrics."""
    # 1. Total Disk Usage
    try:
        disk_path = settings.DATA_DIR if settings.DATA_DIR.exists() else Path("/")
        usage = shutil.disk_usage(disk_path)
        total_disk = usage.total
        free_disk = usage.free
        used_disk = usage.used
    except Exception as e:
        logger.warning("Failed to query disk_usage: %s", e)
        total_disk = 1
        free_disk = 1
        used_disk = 0

    used_pct = round((used_disk / total_disk) * 100, 1) if total_disk > 0 else 0.0
    free_pct = round((free_disk / total_disk) * 100, 1) if total_disk > 0 else 0.0

    disk_info = StorageDiskInfo(
        total_bytes=total_disk,
        total_human=format_bytes(total_disk),
        used_bytes=used_disk,
        used_human=format_bytes(used_disk),
        free_bytes=free_disk,
        free_human=format_bytes(free_disk),
        used_percent=used_pct,
        free_percent=free_pct,
    )

    categories: Dict[str, StorageCategoryInfo] = {}

    # 2. AI Model Cache (Protected)
    model_cache_dir = settings.DATA_DIR / "model_cache"
    model_cache_size = get_dir_size(model_cache_dir)
    # Also check if external MODEL_CACHE_DIR has separate weights
    if settings.MODEL_CACHE_DIR.exists() and settings.MODEL_CACHE_DIR != model_cache_dir:
        try:
            if not settings.MODEL_CACHE_DIR.is_relative_to(settings.DATA_DIR):
                model_cache_size += get_dir_size(settings.MODEL_CACHE_DIR)
        except AttributeError:
            pass

    categories["model_cache"] = StorageCategoryInfo(
        category="model_cache",
        label="AI Model Weights & Checkpoints",
        size_bytes=model_cache_size,
        size_human=format_bytes(model_cache_size),
        item_count=count_files(model_cache_dir),
        path=str(model_cache_dir),
        is_protected=True,
        cleanable=False,
        cleanable_bytes=0,
        cleanable_human="0 B",
        description="Whisper, VoxCPM2, and NLLB neural weights. Strictly protected from automatic purge.",
    )

    # 3. User Projects
    projects_dir = settings.DATA_DIR / "projects"
    projects_size = get_dir_size(projects_dir)
    projects_count = 0
    if db is not None:
        try:
            projects_count = db.query(func.count(Project.id)).scalar() or 0
        except Exception:
            projects_count = len([p for p in projects_dir.iterdir() if p.is_dir()]) if projects_dir.exists() else 0
    elif projects_dir.exists():
        projects_count = len([p for p in projects_dir.iterdir() if p.is_dir()])

    categories["projects"] = StorageCategoryInfo(
        category="projects",
        label="User Dubbing Projects",
        size_bytes=projects_size,
        size_human=format_bytes(projects_size),
        item_count=projects_count,
        path=str(projects_dir),
        is_protected=True,
        cleanable=False,
        cleanable_bytes=0,
        cleanable_human="0 B",
        description="Original videos, audio extractions, subtitles, and exported master media.",
    )

    # 4. Media Toolkit Workspaces & Tasks
    toolkit_dir = settings.DATA_DIR / "toolkit"
    toolkit_size = get_dir_size(toolkit_dir)
    toolkit_count = 0
    if db is not None:
        try:
            toolkit_count = db.query(func.count(ToolkitTask.id)).scalar() or 0
        except Exception:
            toolkit_count = len([p for p in toolkit_dir.iterdir() if p.is_dir()]) if toolkit_dir.exists() else 0
    elif toolkit_dir.exists():
        toolkit_count = len([p for p in toolkit_dir.iterdir() if p.is_dir()])

    # Identify intermediate workdirs in toolkit tasks
    toolkit_intermediate_size = 0
    toolkit_intermediate_count = 0
    if toolkit_dir.exists():
        for workdir in list(toolkit_dir.rglob("fit_work_*")) + list(toolkit_dir.rglob("timeline_assembly_*")):
            if workdir.is_dir():
                toolkit_intermediate_count += 1
                toolkit_intermediate_size += get_dir_size(workdir)

    # Identify tasks older than 7 days that are completed or failed
    old_tasks_count = 0
    old_tasks_size = 0
    cutoff_7d = get_cambodia_now_naive() - timedelta(days=7)
    if db is not None:
        try:
            old_tasks = (
                db.query(ToolkitTask)
                .filter(
                    ToolkitTask.status.in_(["completed", "failed"]),
                    ToolkitTask.created_at <= cutoff_7d,
                )
                .all()
            )
            old_tasks_count = len(old_tasks)
            for t in old_tasks:
                task_path = toolkit_dir / t.id
                if task_path.exists():
                    old_tasks_size += get_dir_size(task_path)
        except Exception as e:
            logger.debug("Failed querying old toolkit tasks: %s", e)

    toolkit_cleanable_bytes = toolkit_intermediate_size + old_tasks_size

    categories["toolkit"] = StorageCategoryInfo(
        category="toolkit",
        label="AI Media Toolkit Workspaces",
        size_bytes=toolkit_size,
        size_human=format_bytes(toolkit_size),
        item_count=toolkit_count,
        path=str(toolkit_dir),
        is_protected=False,
        cleanable=toolkit_cleanable_bytes > 0,
        cleanable_bytes=toolkit_cleanable_bytes,
        cleanable_human=format_bytes(toolkit_cleanable_bytes),
        description="Discrete media processing tasks, audio stems, and intermediate timeline buffers.",
        details={
            "intermediate_workdirs_count": toolkit_intermediate_count,
            "intermediate_workdirs_bytes": toolkit_intermediate_size,
            "intermediate_workdirs_human": format_bytes(toolkit_intermediate_size),
            "old_tasks_count": old_tasks_count,
            "old_tasks_bytes": old_tasks_size,
            "old_tasks_human": format_bytes(old_tasks_size),
        },
    )

    # 5. Temporary Files & TTS Segment Caches
    temp_dir = settings.TEMP_DIR
    temp_size = get_dir_size(temp_dir)
    tts_raw_cache_dir = temp_dir / "tts_raw_cache"
    tts_raw_cache_size = get_dir_size(tts_raw_cache_dir)
    tts_raw_cache_count = count_files(tts_raw_cache_dir)

    tts_previews_dir = temp_dir / "tts_previews"
    tts_previews_size = get_dir_size(tts_previews_dir)
    tts_previews_count = count_files(tts_previews_dir)

    # Non-socket loose files in temp
    loose_temp_size = 0
    loose_temp_count = 0
    if temp_dir.exists():
        for f in temp_dir.iterdir():
            if f.is_file() and not f.name.startswith(".gitkeep"):
                loose_temp_size += get_dir_size(f)
                loose_temp_count += 1

    temp_cleanable_bytes = tts_raw_cache_size + tts_previews_size + loose_temp_size

    categories["temp"] = StorageCategoryInfo(
        category="temp",
        label="Temporary Files & TTS Caches",
        size_bytes=temp_size,
        size_human=format_bytes(temp_size),
        item_count=count_files(temp_dir),
        path=str(temp_dir),
        is_protected=False,
        cleanable=temp_cleanable_bytes > 0,
        cleanable_bytes=temp_cleanable_bytes,
        cleanable_human=format_bytes(temp_cleanable_bytes),
        description="Cached raw TTS segments, waveform previews, and intermediate conversion files.",
        details={
            "tts_raw_cache_bytes": tts_raw_cache_size,
            "tts_raw_cache_count": tts_raw_cache_count,
            "tts_previews_bytes": tts_previews_size,
            "tts_previews_count": tts_previews_count,
            "loose_temp_bytes": loose_temp_size,
            "loose_temp_count": loose_temp_count,
        },
    )

    # 6. Uploads
    uploads_dir = settings.UPLOADS_DIR
    uploads_size = get_dir_size(uploads_dir)
    categories["uploads"] = StorageCategoryInfo(
        category="uploads",
        label="Direct Media Uploads",
        size_bytes=uploads_size,
        size_human=format_bytes(uploads_size),
        item_count=count_files(uploads_dir),
        path=str(uploads_dir),
        is_protected=False,
        cleanable=False,
        cleanable_bytes=0,
        cleanable_human="0 B",
        description="Direct user file uploads, staging files, and raw media sources.",
    )

    # 7. Outputs
    outputs_dir = settings.OUTPUTS_DIR
    outputs_size = get_dir_size(outputs_dir)
    categories["outputs"] = StorageCategoryInfo(
        category="outputs",
        label="Direct Outputs",
        size_bytes=outputs_size,
        size_human=format_bytes(outputs_size),
        item_count=count_files(outputs_dir),
        path=str(outputs_dir),
        is_protected=False,
        cleanable=False,
        cleanable_bytes=0,
        cleanable_human="0 B",
        description="Exported standalone outputs and rendered video clips.",
    )

    # 8. Voice Profiles
    voice_profiles_dir = settings.DATA_DIR / "voice_profiles"
    voice_profiles_size = get_dir_size(voice_profiles_dir)
    voice_count = 0
    if db is not None:
        try:
            voice_count = db.query(func.count(VoiceProfile.id)).scalar() or 0
        except Exception:
            voice_count = len([p for p in voice_profiles_dir.iterdir() if p.is_dir()]) if voice_profiles_dir.exists() else 0
    elif voice_profiles_dir.exists():
        voice_count = len([p for p in voice_profiles_dir.iterdir() if p.is_dir()])

    categories["voice_profiles"] = StorageCategoryInfo(
        category="voice_profiles",
        label="Custom Voice Profiles",
        size_bytes=voice_profiles_size,
        size_human=format_bytes(voice_profiles_size),
        item_count=voice_count,
        path=str(voice_profiles_dir),
        is_protected=True,
        cleanable=False,
        cleanable_bytes=0,
        cleanable_human="0 B",
        description="Reference audio recordings and clone voice profile configurations.",
    )

    # 9. Application & Worker Logs
    logs_dir = settings.DATA_DIR / "logs"
    logs_size = get_dir_size(logs_dir)
    cleanable_logs_size = 0
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.log"):
            try:
                sz = log_file.stat().st_size
                if sz > 50 * 1024:
                    cleanable_logs_size += (sz - 50 * 1024)
            except OSError:
                continue

    categories["logs"] = StorageCategoryInfo(
        category="logs",
        label="Application & Worker Logs",
        size_bytes=logs_size,
        size_human=format_bytes(logs_size),
        item_count=count_files(logs_dir),
        path=str(logs_dir),
        is_protected=False,
        cleanable=cleanable_logs_size > 0,
        cleanable_bytes=cleanable_logs_size,
        cleanable_human=format_bytes(cleanable_logs_size),
        description="Background worker runtime logs, server diagnostics, and process logs.",
    )

    # 10. Database
    db_path = settings.DATA_DIR / "khmerdub.db"
    db_size = get_dir_size(db_path)
    # Include wal or shm files if present
    wal_path = settings.DATA_DIR / "khmerdub.db-wal"
    shm_path = settings.DATA_DIR / "khmerdub.db-shm"
    if wal_path.exists():
        db_size += get_dir_size(wal_path)
    if shm_path.exists():
        db_size += get_dir_size(shm_path)

    categories["database"] = StorageCategoryInfo(
        category="database",
        label="SQLite Database",
        size_bytes=db_size,
        size_human=format_bytes(db_size),
        item_count=1 if db_path.exists() else 0,
        path=str(db_path),
        is_protected=True,
        cleanable=True,  # Can be vacuumed
        cleanable_bytes=0,  # Vacuum reclaimed space varies
        cleanable_human="Variable (via VACUUM)",
        description="Application database storing projects, transcript segments, translation cues, and tasks.",
    )

    total_data_bytes = sum(c.size_bytes for c in categories.values())
    total_cleanable_bytes = (
        temp_cleanable_bytes
        + toolkit_intermediate_size
        + old_tasks_size
        + cleanable_logs_size
    )

    return StorageUsageResponse(
        disk=disk_info,
        categories=categories,
        total_data_bytes=total_data_bytes,
        total_data_human=format_bytes(total_data_bytes),
        total_cleanable_bytes=total_cleanable_bytes,
        total_cleanable_human=format_bytes(total_cleanable_bytes),
    )


def clean_storage(
    targets: List[str],
    older_than_days: int = 7,
    db: Optional[Session] = None,
) -> StorageCleanResponse:
    """Execute safe selective cleanup of temporary files, intermediate caches, logs, and old tasks."""
    freed_bytes = 0
    details: Dict[str, Any] = {}
    processed_targets: List[str] = []

    # Disallowed targets for security and data safety
    forbidden_targets = {"model_cache", "projects", "voice_profiles", ".secrets"}
    clean_targets = [t for t in targets if t not in forbidden_targets]

    # --- Target: temp_caches ---
    if "temp_caches" in clean_targets:
        processed_targets.append("temp_caches")
        temp_freed = 0
        deleted_file_count = 0

        # 1. Clear tts_raw_cache
        raw_cache_dir = settings.TEMP_DIR / "tts_raw_cache"
        if raw_cache_dir.exists():
            for p in raw_cache_dir.iterdir():
                if p.is_file() and not p.name.startswith(".gitkeep"):
                    try:
                        sz = p.stat().st_size
                        p.unlink()
                        temp_freed += sz
                        deleted_file_count += 1
                    except Exception as e:
                        logger.warning("Failed to delete raw TTS cache file %s: %s", p, e)

        # 2. Clear tts_previews
        previews_dir = settings.TEMP_DIR / "tts_previews"
        if previews_dir.exists():
            for p in previews_dir.iterdir():
                if p.is_file() and not p.name.startswith(".gitkeep"):
                    try:
                        sz = p.stat().st_size
                        p.unlink()
                        temp_freed += sz
                        deleted_file_count += 1
                    except Exception as e:
                        logger.warning("Failed to delete preview file %s: %s", p, e)

        # 3. Clear loose preview and temporary audio files in settings.TEMP_DIR
        if settings.TEMP_DIR.exists():
            for p in settings.TEMP_DIR.iterdir():
                if p.is_file() and not p.name.startswith(".gitkeep"):
                    # Check if it matches temporary patterns
                    is_temp_file = (
                        p.name.startswith("preview_")
                        or p.name.endswith("_audio.wav")
                        or p.name.startswith("tts_")
                        or p.name.endswith(".tmp")
                    )
                    if is_temp_file:
                        try:
                            sz = p.stat().st_size
                            p.unlink()
                            temp_freed += sz
                            deleted_file_count += 1
                        except Exception as e:
                            logger.warning("Failed to delete temp file %s: %s", p, e)

        # 4. Clear intermediate workdirs in toolkit (fit_work_* and timeline_assembly_*)
        toolkit_dir = settings.DATA_DIR / "toolkit"
        intermediate_workdirs_freed = 0
        intermediate_workdirs_count = 0
        if toolkit_dir.exists():
            workdirs = list(toolkit_dir.rglob("fit_work_*")) + list(toolkit_dir.rglob("timeline_assembly_*"))
            for wd in workdirs:
                if wd.is_dir():
                    try:
                        sz = get_dir_size(wd)
                        shutil.rmtree(wd, ignore_errors=False)
                        intermediate_workdirs_freed += sz
                        intermediate_workdirs_count += 1
                    except Exception as e:
                        logger.warning("Failed to remove intermediate workdir %s: %s", wd, e)

        temp_freed += intermediate_workdirs_freed
        freed_bytes += temp_freed

        details["temp_caches"] = {
            "freed_bytes": temp_freed,
            "freed_human": format_bytes(temp_freed),
            "deleted_files_count": deleted_file_count,
            "intermediate_workdirs_cleared": intermediate_workdirs_count,
        }

    # --- Target: logs ---
    if "logs" in clean_targets:
        processed_targets.append("logs")
        logs_freed = 0
        truncated_count = 0
        logs_dir = settings.DATA_DIR / "logs"

        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                try:
                    cur_size = log_file.stat().st_size
                    keep_bytes = 50 * 1024  # keep last 50KB for diagnostic continuity
                    if cur_size > keep_bytes:
                        with open(log_file, "rb") as f:
                            f.seek(cur_size - keep_bytes)
                            tail_content = f.read()
                        with open(log_file, "wb") as f:
                            f.write(tail_content)
                        freed = cur_size - keep_bytes
                        logs_freed += freed
                        truncated_count += 1
                except Exception as e:
                    logger.warning("Failed to truncate log file %s: %s", log_file, e)

        freed_bytes += logs_freed
        details["logs"] = {
            "freed_bytes": logs_freed,
            "freed_human": format_bytes(logs_freed),
            "truncated_logs_count": truncated_count,
        }

    # --- Target: old_toolkit_tasks ---
    if "old_toolkit_tasks" in clean_targets:
        processed_targets.append("old_toolkit_tasks")
        tasks_freed = 0
        deleted_tasks_count = 0
        toolkit_dir = settings.DATA_DIR / "toolkit"
        cutoff = get_cambodia_now_naive() - timedelta(days=max(0, older_than_days))

        if db is not None:
            try:
                eligible_tasks = (
                    db.query(ToolkitTask)
                    .filter(
                        ToolkitTask.status.in_(["completed", "failed"]),
                        ToolkitTask.created_at <= cutoff,
                    )
                    .all()
                )
                for task in eligible_tasks:
                    task_path = toolkit_dir / task.id
                    if task_path.exists():
                        tasks_freed += get_dir_size(task_path)
                    delete_toolkit_task_storage(task.id)
                    db.delete(task)
                    deleted_tasks_count += 1
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Failed pruning old toolkit tasks: %s", e)

        freed_bytes += tasks_freed
        details["old_toolkit_tasks"] = {
            "freed_bytes": tasks_freed,
            "freed_human": format_bytes(tasks_freed),
            "deleted_tasks_count": deleted_tasks_count,
            "older_than_days": older_than_days,
        }

    # --- Target: vacuum_db ---
    if "vacuum_db" in clean_targets:
        processed_targets.append("vacuum_db")
        db_freed = 0
        db_path = settings.DATA_DIR / "khmerdub.db"
        size_before = get_dir_size(db_path) if db_path.exists() else 0

        if db is not None and settings.DATABASE_URL.startswith("sqlite"):
            try:
                # Commit any open transaction before running VACUUM
                db.commit()
                # Run VACUUM outside a transaction block
                raw_connection = db.get_bind().raw_connection()
                raw_cursor = raw_connection.cursor()
                raw_cursor.execute("VACUUM")
                raw_cursor.close()
                raw_connection.commit()

                size_after = get_dir_size(db_path) if db_path.exists() else 0
                if size_before > size_after:
                    db_freed = size_before - size_after
            except Exception as e:
                logger.warning("SQLite VACUUM failed or skipped: %s", e)

        freed_bytes += db_freed
        details["vacuum_db"] = {
            "vacuum_executed": True,
            "freed_bytes": db_freed,
            "freed_human": format_bytes(db_freed),
            "size_before": format_bytes(size_before),
            "size_after": format_bytes(get_dir_size(db_path) if db_path.exists() else 0),
        }

    # Fetch updated storage stats after cleanup
    updated_storage = get_storage_usage(db=db)

    return StorageCleanResponse(
        success=True,
        freed_bytes=freed_bytes,
        freed_human=format_bytes(freed_bytes),
        targets_processed=processed_targets,
        details=details,
        storage=updated_storage,
    )


def purge_all_user_data(
    db: Optional[Session] = None,
    keep_models: bool = True,
    keep_voice_profiles: bool = True,
) -> StorageCleanResponse:
    """Purge all user-created projects, toolkit tasks, uploads, outputs, and temp files.

    Voice reference audio and custom voice profiles are strictly preserved.
    AI Model weights (VoxCPM2, Whisper, NLLB) are strictly preserved when keep_models=True.
    Runs inside backend container with root privileges to clean any root-owned task directories.
    """
    freed_bytes = 0
    deleted_projects_count = 0
    deleted_tasks_count = 0

    # 1. Clear Database tables
    if db is not None:
        try:
            db.commit()
            raw_connection = db.get_bind().raw_connection()
            cursor = raw_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF;")

            tables_to_clear = [
                "toolkit_tts_segments",
                "toolkit_transcript_segments",
                "toolkit_translation_segments",
                "toolkit_tasks",
                "generated_audios",
                "translation_segments",
                "subtitle_segments",
                "processing_jobs",
                "project_speakers",
                "transcript_segments",
                "videos",
                "projects",
            ]
            for tbl in tables_to_clear:
                cursor.execute(f"DELETE FROM {tbl};")

            raw_connection.commit()
            cursor.execute("VACUUM;")
            cursor.close()
            raw_connection.commit()
        except Exception as e:
            logger.error("Failed clearing database tables in purge_all_user_data: %s", e)

    # 2. Clean Projects Directory
    projects_dir = settings.DATA_DIR / "projects"
    if projects_dir.exists():
        for item in projects_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            sz = get_dir_size(item)
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=False)
                else:
                    item.unlink(missing_ok=True)
                freed_bytes += sz
                deleted_projects_count += 1
            except Exception as e:
                logger.warning("Failed removing project storage %s: %s", item, e)

    # 3. Clean Toolkit Tasks Directory
    toolkit_dir = settings.DATA_DIR / "toolkit"
    if toolkit_dir.exists():
        for item in toolkit_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            sz = get_dir_size(item)
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=False)
                else:
                    item.unlink(missing_ok=True)
                freed_bytes += sz
                deleted_tasks_count += 1
            except Exception as e:
                logger.warning("Failed removing toolkit storage %s: %s", item, e)

    # 4. Clean Uploads Directory
    uploads_dir = settings.UPLOADS_DIR
    if uploads_dir.exists():
        for item in uploads_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            sz = get_dir_size(item)
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=False)
                else:
                    item.unlink(missing_ok=True)
                freed_bytes += sz
            except Exception as e:
                logger.warning("Failed removing upload %s: %s", item, e)

    # 5. Clean Outputs Directory
    outputs_dir = settings.OUTPUTS_DIR
    if outputs_dir.exists():
        for item in outputs_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            sz = get_dir_size(item)
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=False)
                else:
                    item.unlink(missing_ok=True)
                freed_bytes += sz
            except Exception as e:
                logger.warning("Failed removing output %s: %s", item, e)

    # 6. Clean Temp Directory
    temp_dir = settings.TEMP_DIR
    if temp_dir.exists():
        for item in temp_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            sz = get_dir_size(item)
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=False)
                else:
                    item.unlink(missing_ok=True)
                freed_bytes += sz
            except Exception as e:
                logger.warning("Failed removing temp item %s: %s", item, e)

        # Recreate required empty directories with shared permissions
        for sub in ["tts_raw_cache", "tts_previews", "voxcpm_worker"]:
            sd = temp_dir / sub
            sd.mkdir(parents=True, exist_ok=True)
            try:
                sd.chmod(0o777)
            except OSError:
                pass

    # 7. Truncate Logs
    logs_dir = settings.DATA_DIR / "logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.log"):
            try:
                sz = log_file.stat().st_size
                with open(log_file, "w") as f:
                    f.write("")
                freed_bytes += sz
            except Exception as e:
                logger.warning("Failed truncating log %s: %s", log_file, e)

    # 8. Refetch updated storage
    updated_storage = get_storage_usage(db=db)

    return StorageCleanResponse(
        success=True,
        freed_bytes=freed_bytes,
        freed_human=format_bytes(freed_bytes),
        targets_processed=["all_user_data"],
        details={
            "deleted_projects_count": deleted_projects_count,
            "deleted_tasks_count": deleted_tasks_count,
            "voice_profiles_preserved": keep_voice_profiles,
            "model_cache_preserved": keep_models,
        },
        storage=updated_storage,
    )

