import re
import logging
from pathlib import Path
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_project_id(project_id: str) -> str:
    """Validate and sanitize project_id to prevent path traversal."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", project_id.strip())
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
