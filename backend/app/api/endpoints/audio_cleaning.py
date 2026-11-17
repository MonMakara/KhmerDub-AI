"""Audio cleanup endpoints; results share the existing toolkit history."""
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.endpoints.toolkit import _serialize_task
from app.core.config import settings
from app.core.storage import get_toolkit_task_dir
from app.database.session import get_db
from app.models.project import Project
from app.models.toolkit import ToolkitTask
from app.services.audio_cleaning import capabilities, process_cleaning, SUBMIT_LOCK
from app.services.video.cleaning import FORMATS, PRESETS

router = APIRouter(tags=["toolkit"])


def get_task(task_id: str, db: Session) -> ToolkitTask:
    try:
        uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Cleaning task not found.") from exc
    task = db.get(ToolkitTask, task_id)
    if not task or task.tool_type != "audio_cleaning":
        raise HTTPException(status_code=404, detail="Cleaning task not found.")
    return task


@router.get("/capabilities")
def get_capabilities():
    caps = capabilities()
    return {
        **caps,
        "available": bool(caps.get("noise_available") or caps.get("music_available")),
        "modes": ["noise", "music"],
        "engine_name": caps.get("noise_engine", "FFmpeg"),
        "description": "Background noise removal & speech isolation",
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
        "input_extensions": sorted(FORMATS),
    }


@router.post("/start", status_code=202)
@router.post("/clean", status_code=202, include_in_schema=False)
async def start_cleaning(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    project_id: str | None = Form(None),
    mode: str = Form("noise"), strength: str = Form("balanced"),
    db: Session = Depends(get_db),
):
    if mode not in ("noise", "music") or strength not in PRESETS:
        raise HTTPException(status_code=400, detail="Select a valid mode and strength.")
    if mode == "music" and not capabilities()["music_available"]:
        raise HTTPException(status_code=503, detail=capabilities()["music_reason"])
    if bool(file) == bool(project_id):
        raise HTTPException(status_code=400, detail="Choose one upload or one existing project.")
    source = None
    if project_id:
        project = db.get(Project, project_id)
        if not project or not project.video:
            raise HTTPException(status_code=404, detail="Project source video not found.")
        source = Path(project.video.file_path)
        if not source.resolve().is_relative_to(settings.DATA_DIR.resolve()) or not source.is_file():
            raise HTTPException(status_code=400, detail="Project source file is not available.")
    filename = Path(file.filename or "") .name if file else source.name
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported audio or video extension.")
    task_id = str(uuid.uuid4())
    root = get_toolkit_task_dir(task_id)
    folder = root / "input"
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / f"source{suffix}"
    maximum = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def copy_bounded() -> None:
        if shutil.disk_usage(folder).free < maximum + 100_000_000:
            raise HTTPException(status_code=507, detail="Not enough free disk space for upload.")
        reader = file.file if file else source.open("rb")
        total = 0
        try:
            with destination.open("xb") as output:
                while chunk := reader.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit.")
                    output.write(chunk)
            if not total:
                raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        finally:
            if not file:
                reader.close()

    try:
        await run_in_threadpool(copy_bounded)
        with SUBMIT_LOCK:
            active = db.query(ToolkitTask).filter(
                ToolkitTask.tool_type == "audio_cleaning",
                ToolkitTask.status.in_(["pending", "processing", "cancelling"]),
            ).count()
            if active >= 3:
                raise HTTPException(status_code=429, detail="The cleanup queue is full. Please wait for a task to finish.")
            task = ToolkitTask(
                id=task_id, tool_type="audio_cleaning", source_type="project" if source else "upload",
                source_project_id=project_id, source_filename=filename,
                source_file_path=str(destination), target_format="wav", status="pending",
                source_media_metadata=json.dumps({"mode": mode, "strength": strength}),
                output_media_metadata=json.dumps({"phase": "Queued", "mode": mode, "strength": strength}),
            )
            db.add(task)
            db.commit()
        background_tasks.add_task(process_cleaning, task_id)
        return _serialize_task(task)
    except Exception:
        db.rollback()
        shutil.rmtree(root)
        raise
    finally:
        if file:
            await file.close()


@router.post("/{task_id}/cancel")
def cancel_cleaning(task_id: str, db: Session = Depends(get_db)):
    task = get_task(task_id, db)
    db.query(ToolkitTask).filter(
        ToolkitTask.id == task_id, ToolkitTask.status.in_(["pending", "processing"]),
    ).update({ToolkitTask.status: "cancelling"}, synchronize_session="fetch")
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.api_route("/{task_id}/files/{kind}", methods=["GET", "HEAD"])
@router.api_route("/{task_id}/file/{kind}", methods=["GET", "HEAD"], include_in_schema=False)
def cleaning_file(task_id: str, kind: str, download: bool = False,
                  db: Session = Depends(get_db)):
    task = get_task(task_id, db)
    files = {"original": ("original.wav", "audio/wav"),
             "wav": ("cleaned.wav", "audio/wav"), "mp3": ("cleaned.mp3", "audio/mpeg"),
             "background": ("background.wav", "audio/wav"),
             "video": ("cleaned.mp4", "video/mp4")}
    if kind not in files:
        raise HTTPException(status_code=404, detail="Output type not found.")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="Outputs are available only after successful verification.")
    name, mime = files[kind]
    root = get_toolkit_task_dir(task_id).resolve()
    path = root / "output" / name
    if not path.resolve().is_relative_to(root) or not path.is_file() or not path.stat().st_size:
        raise HTTPException(status_code=404, detail="This output is not available for the selected input.")
    return FileResponse(path, media_type=mime, filename=name,
                        content_disposition_type="attachment" if download else "inline")
