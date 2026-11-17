import json
import logging
import shutil
import uuid
from app.core.timezone import get_cambodia_now_naive
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    get_project_original_dir,
    get_project_extracted_dir,
)
from app.database.session import SessionLocal
from app.models.project import Project, Video, ProjectStatus
from app.models.toolkit import ToolkitTask
from app.services.downloader.engine import (
    execute_download_job,
    request_download_cancellation,
    DownloadCancelledException,
    DownloadLimitExceededError,
)
from app.services.downloader.metadata import (
    fetch_media_metadata,
    VideoMetadataError,
)
from app.services.downloader.security import (
    SSRFSecurityError,
    UnsupportedSourceError,
    InvalidURLError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)
_video_processor = FFmpegVideoProcessor()


class DownloaderService:
    """Orchestrates video downloader tasks, metadata inspection, and handoffs."""

    def inspect_url(self, url: str) -> Dict[str, Any]:
        """Validate URL and extract metadata without full download."""
        try:
            return fetch_media_metadata(url)
        except SSRFSecurityError as e:
            logger.warning("SSRF rejection for %s: %s", url, e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security violation: {e}",
            )
        except UnsupportedSourceError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except InvalidURLError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid URL: {e}",
            )
        except VideoMetadataError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )
        except Exception as e:
            logger.error("Unexpected error inspecting URL %s: %s", url, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to inspect video link: {e}",
            )

    def start_download(
        self,
        db: Session,
        background_tasks: BackgroundTasks,
        url: str,
        output_type: str,
        quality: str,
        audio_format: str,
        rights_confirmed: bool = True,
    ) -> ToolkitTask:
        """Create and queue a new media download task or reuse an existing completed task."""
        if output_type not in {"video", "audio"}:
            output_type = "video"

        target_fmt = audio_format if output_type == "audio" else "mp4"

        # Check for existing completed download to avoid duplicate network transfers
        candidate_tasks = (
            db.query(ToolkitTask)
            .filter(
                ToolkitTask.tool_type == "video_downloader",
                ToolkitTask.source_file_path == url,
                ToolkitTask.status == "completed",
                ToolkitTask.target_format == target_fmt,
            )
            .order_by(ToolkitTask.created_at.desc())
            .all()
        )
        for existing in candidate_tasks:
            if not existing.output_file_path:
                continue
            cached_path = Path(existing.output_file_path)
            try:
                if not cached_path.exists() or cached_path.stat().st_size == 0:
                    continue
            except OSError:
                continue

            # Verify that format, quality, and processing options match the request
            existing_meta = {}
            if existing.source_media_metadata:
                try:
                    existing_meta = json.loads(existing.source_media_metadata)
                except Exception:
                    pass

            cached_output_type = existing_meta.get("requested_output_type", "video")
            cached_quality = existing_meta.get("requested_quality", "best")
            cached_audio_fmt = existing_meta.get("requested_audio_format", "mp3")

            if cached_output_type != output_type:
                continue
            if cached_quality != quality:
                continue
            if output_type == "audio" and cached_audio_fmt != audio_format:
                continue

            logger.info(
                "Reusing existing completed download task %s for URL: %s (quality=%s, format=%s)",
                existing.id,
                url,
                quality,
                target_fmt,
            )
            return existing

        # Pre-validate URL and fetch title for task display
        meta = self.inspect_url(url)
        title = meta.get("title") or "Downloaded Media"

        task = ToolkitTask(
            id=str(uuid.uuid4()),
            tool_type="video_downloader",
            source_type="url",
            source_filename=f"{title[:100]} ({meta.get('source_platform', 'Web')})",
            source_file_path=url,
            source_media_metadata=json.dumps({
                "title": title,
                "platform": meta.get("source_platform"),
                "uploader": meta.get("uploader"),
                "thumbnail_url": meta.get("thumbnail_url"),
                "duration_seconds": meta.get("duration_seconds"),
                "requested_output_type": output_type,
                "requested_quality": quality,
                "requested_audio_format": audio_format,
                "stage": "queued",
            }),
            target_format=target_fmt,
            status="pending",
            progress_percentage=0,
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        task_id = task.id
        background_tasks.add_task(
            self._async_download_worker,
            task_id=task_id,
            url=url,
            output_type=output_type,
            quality=quality,
            audio_format=audio_format,
        )

        return task

    def cancel_task(self, db: Session, task_id: str) -> Dict[str, Any]:
        """Cancel an in-progress or queued download task."""
        task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status in {"completed", "failed", "cancelled"}:
            return {"task_id": task_id, "status": task.status, "message": f"Task already {task.status}"}

        # Signal engine thread
        signaled = request_download_cancellation(task_id)

        task.status = "cancelled"
        task.error_message = "Download cancelled by user."
        task.updated_at = get_cambodia_now_naive()
        db.commit()

        return {
            "task_id": task_id,
            "status": "cancelled",
            "signaled_worker": signaled,
            "message": "Download task successfully cancelled.",
        }

    def import_to_dubbing(
        self,
        db: Session,
        task_id: str,
        title: Optional[str] = None,
        original_lang: str = "en",
        target_lang: str = "km",
    ) -> Project:
        """Import a completed downloaded video into a Video Dubbing project."""
        task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Toolkit task not found")

        if task.status != "completed":
            raise HTTPException(status_code=400, detail="Only completed download tasks can be imported.")

        if not task.output_file_path or not Path(task.output_file_path).exists():
            raise HTTPException(status_code=404, detail="Downloaded media file is missing from storage.")

        source_video = Path(task.output_file_path)

        # Parse task metadata for project title
        task_meta = {}
        if task.source_media_metadata:
            try:
                task_meta = json.loads(task.source_media_metadata)
            except Exception:
                pass

        proj_title = (title or task_meta.get("title") or task.source_filename or "Imported Video").strip()[:100]

        # 1. Create Project in DB
        new_project = Project(
            id=str(uuid.uuid4()),
            title=proj_title,
            original_language=original_lang.lower(),
            target_language=target_lang.lower(),
            pipeline_version="v2.1",
            status="created",
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)

        try:
            # 2. Setup project storage
            project_orig_dir = get_project_original_dir(new_project.id)
            dest_video_path = project_orig_dir / "original_video.mp4"
            shutil.copy2(source_video, dest_video_path)

            # Copy to uploads dir for backwards compatibility
            uploads_dir = settings.UPLOADS_DIR
            uploads_dir.mkdir(parents=True, exist_ok=True)
            legacy_upload_path = uploads_dir / f"{new_project.id}.mp4"
            shutil.copy2(source_video, legacy_upload_path)

            # 3. Probe video metadata
            probe = _video_processor.get_metadata(dest_video_path)

            # 4. Extract audio track to temp & extracted dir
            temp_dir = settings.TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            audio_temp_path = temp_dir / f"{new_project.id}_audio.wav"

            extracted_dir = get_project_extracted_dir(new_project.id)
            persistent_audio_path = extracted_dir / "extracted_audio.wav"

            if probe.has_audio:
                _video_processor.extract_audio(dest_video_path, audio_temp_path)
                if audio_temp_path.exists():
                    shutil.copy2(audio_temp_path, persistent_audio_path)
                new_project.status = ProjectStatus.AUDIO_EXTRACTED
            else:
                new_project.status = ProjectStatus.UPLOADED

            video = Video(
                project_id=new_project.id,
                filename="original_video.mp4",
                file_path=str(dest_video_path),
                file_size_bytes=dest_video_path.stat().st_size if dest_video_path.exists() else 0,
                duration_seconds=float(probe.duration_seconds) if getattr(probe, "duration_seconds", None) is not None else (float(probe.duration) if getattr(probe, "duration", None) is not None else None),
                width=int(probe.width) if getattr(probe, "width", None) is not None else None,
                height=int(probe.height) if getattr(probe, "height", None) is not None else None,
                video_codec=str(probe.video_codec) if getattr(probe, "video_codec", None) is not None else None,
                audio_codec=str(probe.audio_codec) if getattr(probe, "audio_codec", None) is not None else None,
                extracted_audio_path=str(persistent_audio_path) if getattr(probe, "has_audio", False) else None,
            )
            db.add(video)
            new_project.original_video_path = str(dest_video_path)
            new_project.updated_at = get_cambodia_now_naive()
            db.commit()
            db.refresh(new_project)

            logger.info("Successfully imported task %s into Project %s ('%s')", task_id, new_project.id, new_project.title)
            return new_project

        except Exception as e:
            logger.error("Failed to import task %s into dubbing project: %s", task_id, e)
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to import video into dubbing: {e}",
            )

    def _async_download_worker(
        self,
        task_id: str,
        url: str,
        output_type: str,
        quality: str,
        audio_format: str,
    ):
        """Background thread worker for download execution."""
        db = SessionLocal()
        try:
            task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
            if not task:
                return

            task.status = "processing"
            task.progress_percentage = 5
            db.commit()

            def progress_callback(update_data: Dict[str, Any]):
                local_db = SessionLocal()
                try:
                    t = local_db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
                    if not t:
                        return

                    pct = update_data.get("progress_percentage")
                    if pct is not None:
                        t.progress_percentage = max(0, min(100, int(pct)))

                    st = update_data.get("status")
                    if st:
                        t.status = st

                    # Merge into source_media_metadata
                    cur_meta = {}
                    if t.source_media_metadata:
                        try:
                            cur_meta = json.loads(t.source_media_metadata)
                        except Exception:
                            pass

                    for k in ["stage", "downloaded_bytes", "total_bytes", "speed_bytes_per_sec", "eta_seconds", "detail"]:
                        if k in update_data:
                            cur_meta[k] = update_data[k]

                    t.source_media_metadata = json.dumps(cur_meta)

                    if update_data.get("output_file_path"):
                        t.output_file_path = update_data["output_file_path"]
                        t.output_filename = update_data.get("output_filename")
                        t.output_duration_seconds = update_data.get("output_duration_seconds")
                        t.output_file_size_bytes = update_data.get("output_file_size_bytes")
                        t.output_media_metadata = update_data.get("output_media_metadata")

                    t.updated_at = get_cambodia_now_naive()
                    local_db.commit()
                except Exception as ex:
                    logger.warning("Error in progress callback for %s: %s", task_id, ex)
                finally:
                    local_db.close()

            # Execute
            execute_download_job(
                task_id=task_id,
                url=url,
                output_type=output_type,
                quality=quality,
                audio_format=audio_format,
                progress_callback=progress_callback,
            )

        except DownloadCancelledException:
            logger.info("Task %s was cancelled during execution.", task_id)
            task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
            if task:
                task.status = "cancelled"
                task.error_message = "Download cancelled by user."
                task.updated_at = get_cambodia_now_naive()
                db.commit()
        except DownloadLimitExceededError as e:
            logger.warning("Task %s exceeded size/duration limits: %s", task_id, e)
            task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = str(e)
                task.updated_at = get_cambodia_now_naive()
                db.commit()
        except Exception as e:
            logger.error("Download failed for task %s: %s", task_id, e, exc_info=True)
            task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = str(e)
                task.updated_at = get_cambodia_now_naive()
                db.commit()
        finally:
            db.close()


downloader_service = DownloaderService()
