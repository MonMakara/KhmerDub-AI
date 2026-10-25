import re
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_project_id(project_id: str) -> str:
    """Validate and sanitize project_id to prevent path traversal."""
    if not project_id:
        raise ValueError("Invalid project_id: empty or None")
    stripped = project_id.strip()
    if "/" in stripped or "\\" in stripped or ".." in stripped:
        raise ValueError(f"Path traversal characters detected in project_id: '{project_id}'")
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", stripped)
    if not sanitized:
        raise ValueError(f"Invalid project_id: '{project_id}'")
    return sanitized


def get_project_base_dir(project_id: str) -> Path:
    """Return root directory for project-specific storage: data/projects/{project_id}/."""
    safe_id = sanitize_project_id(project_id)
    base = settings.DATA_DIR / "projects" / safe_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_project_original_dir(project_id: str) -> Path:
    """Return directory for original uploaded video: data/projects/{project_id}/original/."""
    d = get_project_base_dir(project_id) / "original"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_extracted_dir(project_id: str) -> Path:
    """Return directory for extracted audio: data/projects/{project_id}/extracted/."""
    d = get_project_base_dir(project_id) / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_generated_audio_dir(project_id: str) -> Path:
    """Return directory for persistent TTS speech segments: data/projects/{project_id}/generated_audio/."""
    d = get_project_base_dir(project_id) / "generated_audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_output_dir(project_id: str) -> Path:
    """Return directory for final synchronized audio and video exports: data/projects/{project_id}/output/."""
    d = get_project_base_dir(project_id) / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_subtitles_dir(project_id: str) -> Path:
    """Return directory for subtitle files: data/projects/{project_id}/subtitles/."""
    d = get_project_base_dir(project_id) / "subtitles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_subtitle_file_path(project_id: str, language: str, format: str) -> Path:
    """Return standard path for project-specific subtitle export file."""
    safe_lang = re.sub(r"[^a-zA-Z0-9_-]", "", language.strip())
    safe_fmt = re.sub(r"[^a-zA-Z0-9_-]", "", format.strip().lower())
    return get_project_subtitles_dir(project_id) / f"{safe_lang}.{safe_fmt}"


def get_audio_segment_path(project_id: str, segment_id: str) -> Path:
    """Return standard persistent path for a synthesized Khmer audio segment."""
    safe_seg = re.sub(r"[^a-zA-Z0-9_-]", "", segment_id.strip())
    return get_project_generated_audio_dir(project_id) / f"segment_{safe_seg}.mp3"


def get_timeline_audio_path(project_id: str) -> Path:
    """Return standard path for the complete synchronized Khmer timeline WAV."""
    return get_project_output_dir(project_id) / "khmer_timeline.wav"


def get_exported_video_path(project_id: str) -> Path:
    """Return standard path for the final dubbed MP4 video."""
    return get_project_output_dir(project_id) / "dubbed_khmer.mp4"


def resolve_audio_file(project_id: str, segment_id: str, stored_path: Optional[str] = None) -> Path:
    """Resolve audio segment file path with full backward compatibility for existing files."""
    if stored_path:
        p = Path(stored_path)
        if p.exists() and p.stat().st_size > 0:
            return p

    # Check project-specific persistent path
    standard_path = get_audio_segment_path(project_id, segment_id)
    if standard_path.exists() and standard_path.stat().st_size > 0:
        return standard_path

    # Check Phase 5 legacy temp path
    safe_proj = sanitize_project_id(project_id)
    safe_seg = re.sub(r"[^a-zA-Z0-9_-]", "", segment_id.strip())
    legacy_temp = settings.TEMP_DIR / f"tts_{safe_proj}_{safe_seg}.mp3"
    if legacy_temp.exists() and legacy_temp.stat().st_size > 0:
        return legacy_temp

    return standard_path


def delete_project_storage(project_id: str) -> Dict[str, Any]:
    """
    Safely delete all file storage belonging to a project.
    Strictly prevents path traversal and ensures only project-owned subdirectories
    under DATA_DIR are removed. Never touches shared volumes, model caches, or .secrets.
    Handles symlinks, missing files, and partially-deleted states safely and idempotently.
    """
    safe_id = sanitize_project_id(project_id)
    if not safe_id or safe_id in [".", "..", "/", "\\"]:
        raise ValueError(f"Invalid project ID for deletion: '{project_id}'")

    deleted_paths = []

    # 1. Project directory: data/projects/{safe_id}
    base_projects_dir = (settings.DATA_DIR / "projects").resolve()
    project_path = base_projects_dir / safe_id

    # If the project root itself is a symlink, unlink the symlink directly without following it
    if project_path.is_symlink():
        try:
            project_path.unlink()
            deleted_paths.append(str(project_path))
            logger.info(f"Unlinked project directory symlink: {project_path}")
        except Exception as e:
            logger.warning(f"Failed to unlink project directory symlink {project_path}: {e}")
    elif project_path.exists() and project_path.is_dir():
        # Verify strict containment inside base_projects_dir
        resolved = project_path.resolve()
        if resolved.parent == base_projects_dir and resolved.name == safe_id:
            try:
                shutil.rmtree(project_path, ignore_errors=False)
                deleted_paths.append(str(project_path))
                logger.info(f"Deleted project directory: {project_path}")
            except Exception as e:
                logger.warning(f"Failed to remove project directory {project_path}: {e}")

    # 2. Uploads directory: data/uploads/{safe_id}
    base_uploads_dir = settings.UPLOADS_DIR.resolve()
    upload_path = base_uploads_dir / safe_id

    if upload_path.is_symlink():
        try:
            upload_path.unlink()
            deleted_paths.append(str(upload_path))
            logger.info(f"Unlinked upload directory symlink: {upload_path}")
        except Exception as e:
            logger.warning(f"Failed to unlink upload directory symlink {upload_path}: {e}")
    elif upload_path.exists():
        if upload_path.is_dir():
            resolved = upload_path.resolve()
            if resolved.parent == base_uploads_dir and resolved.name == safe_id:
                try:
                    shutil.rmtree(upload_path, ignore_errors=False)
                    deleted_paths.append(str(upload_path))
                    logger.info(f"Deleted upload directory: {upload_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove upload directory {upload_path}: {e}")
        elif upload_path.is_file():
            try:
                upload_path.unlink()
                deleted_paths.append(str(upload_path))
            except Exception as e:
                logger.warning(f"Failed to unlink upload file {upload_path}: {e}")

    # 3. Legacy temp files: data/temp/tts_{safe_id}_*.mp3
    temp_dir = settings.TEMP_DIR.resolve()
    if temp_dir.exists():
        for temp_file in temp_dir.glob(f"tts_{safe_id}_*"):
            try:
                # If temp_file is a symlink, unlink the symlink itself, NEVER its target!
                if temp_file.is_symlink():
                    temp_file.unlink()
                    deleted_paths.append(str(temp_file))
                elif temp_file.is_file():
                    temp_file.unlink()
                    deleted_paths.append(str(temp_file))
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {e}")

    return {
        "project_id": safe_id,
        "deleted_paths": deleted_paths,
        "deleted_count": len(deleted_paths),
    }
