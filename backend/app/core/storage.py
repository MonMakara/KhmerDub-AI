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
    """
    safe_id = sanitize_project_id(project_id)
    if not safe_id or safe_id in [".", "..", "/", "\\"]:
        raise ValueError(f"Invalid project ID for deletion: '{project_id}'")

    deleted_paths = []

    # 1. Project directory: data/projects/{safe_id}
    base_projects_dir = (settings.DATA_DIR / "projects").resolve()
    project_dir = (base_projects_dir / safe_id).resolve()
    # Strict validation: project_dir must be an immediate child of base_projects_dir
    if project_dir.parent == base_projects_dir and project_dir.name == safe_id and project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=False)
        deleted_paths.append(str(project_dir))
        logger.info(f"Deleted project directory: {project_dir}")

    # 2. Uploads directory: data/uploads/{safe_id}
    base_uploads_dir = settings.UPLOADS_DIR.resolve()
    upload_dir = (base_uploads_dir / safe_id).resolve()
    if upload_dir.parent == base_uploads_dir and upload_dir.name == safe_id and upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=False)
        deleted_paths.append(str(upload_dir))
        logger.info(f"Deleted upload directory: {upload_dir}")

    # 3. Legacy temp files: data/temp/tts_{safe_id}_*.mp3
    temp_dir = settings.TEMP_DIR.resolve()
    if temp_dir.exists():
        for temp_file in temp_dir.glob(f"tts_{safe_id}_*"):
            resolved = temp_file.resolve()
            if resolved.parent == temp_dir and resolved.is_file():
                try:
                    resolved.unlink()
                    deleted_paths.append(str(resolved))
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {resolved}: {e}")

    return {
        "project_id": safe_id,
        "deleted_paths": deleted_paths,
        "deleted_count": len(deleted_paths),
    }
