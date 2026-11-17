import uuid
from datetime import timedelta
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import get_cambodia_now_naive
from app.database.session import get_db
from app.main import app
from app.models.toolkit import ToolkitTask
from app.services.storage_manager import (
    clean_storage,
    count_files,
    format_bytes,
    get_dir_size,
    get_storage_usage,
)


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(-5) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024) == "1.00 MB"
    assert format_bytes(1024 * 1024 * 1024 * 2) == "2.00 GB"


def test_get_dir_size_and_count_files(tmp_path: Path):
    d = tmp_path / "test_dir"
    d.mkdir()
    f1 = d / "file1.txt"
    f1.write_bytes(b"A" * 100)
    sub = d / "subdir"
    sub.mkdir()
    f2 = sub / "file2.txt"
    f2.write_bytes(b"B" * 200)

    assert get_dir_size(d) == 300
    assert count_files(d) == 2


def test_get_storage_usage(db_session: Session):
    usage = get_storage_usage(db=db_session)

    assert usage.disk.total_bytes > 0
    assert usage.disk.free_bytes > 0
    assert "model_cache" in usage.categories
    assert "projects" in usage.categories
    assert "toolkit" in usage.categories
    assert "temp" in usage.categories
    assert "logs" in usage.categories
    assert "database" in usage.categories

    # AI Model Cache must be protected
    assert usage.categories["model_cache"].is_protected is True
    assert usage.categories["model_cache"].cleanable is False

    # Projects must be protected from automatic cache clearing
    assert usage.categories["projects"].is_protected is True
    assert usage.categories["projects"].cleanable is False


def test_clean_storage_temp_caches(db_session: Session):
    raw_cache_dir = settings.TEMP_DIR / "tts_raw_cache"
    raw_cache_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = raw_cache_dir / f"test_cache_{uuid.uuid4().hex[:8]}.wav"
    dummy_file.write_bytes(b"test audio data" * 100)

    assert dummy_file.exists()

    res = clean_storage(targets=["temp_caches"], db=db_session)
    assert res.success is True
    assert "temp_caches" in res.targets_processed
    assert not dummy_file.exists()
    assert res.freed_bytes >= 1500


def test_clean_storage_old_toolkit_tasks(db_session: Session):
    toolkit_dir = settings.DATA_DIR / "toolkit"
    toolkit_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create completed old task (eligible)
    old_task_id = str(uuid.uuid4())
    old_task_folder = toolkit_dir / old_task_id
    old_task_folder.mkdir(parents=True, exist_ok=True)
    dummy_out = old_task_folder / "output.wav"
    dummy_out.write_bytes(b"x" * 500)

    ten_days_ago = get_cambodia_now_naive() - timedelta(days=10)
    task1 = ToolkitTask(
        id=old_task_id,
        tool_type="transcript_to_audio",
        source_type="direct_text",
        source_filename="test.txt",
        source_file_path=str(old_task_folder / "test.txt"),
        target_format="mp3",
        status="completed",
        created_at=ten_days_ago,
        updated_at=ten_days_ago,
    )
    db_session.add(task1)

    # 2. Create pending old task (NOT eligible, must be preserved!)
    pending_task_id = str(uuid.uuid4())
    pending_task_folder = toolkit_dir / pending_task_id
    pending_task_folder.mkdir(parents=True, exist_ok=True)
    task2 = ToolkitTask(
        id=pending_task_id,
        tool_type="transcript_to_audio",
        source_type="direct_text",
        source_filename="test2.txt",
        source_file_path=str(pending_task_folder / "test2.txt"),
        target_format="mp3",
        status="pending",
        created_at=ten_days_ago,
        updated_at=ten_days_ago,
    )
    db_session.add(task2)
    db_session.commit()

    # Clean old tasks older than 7 days
    res = clean_storage(targets=["old_toolkit_tasks"], older_than_days=7, db=db_session)
    assert res.success is True
    assert "old_toolkit_tasks" in res.targets_processed

    # Completed old task must be deleted
    assert not old_task_folder.exists()
    assert db_session.query(ToolkitTask).filter(ToolkitTask.id == old_task_id).first() is None

    # Pending task must be intact
    assert pending_task_folder.exists()
    assert db_session.query(ToolkitTask).filter(ToolkitTask.id == pending_task_id).first() is not None

    # Cleanup pending dummy task
    db_session.delete(task2)
    db_session.commit()
    if pending_task_folder.exists():
        import shutil
        shutil.rmtree(pending_task_folder, ignore_errors=True)


def test_clean_storage_vacuum_db(db_session: Session):
    res = clean_storage(targets=["vacuum_db"], db=db_session)
    assert res.success is True
    assert "vacuum_db" in res.targets_processed
    assert res.details["vacuum_db"]["vacuum_executed"] is True


def test_api_storage_endpoints():
    client = TestClient(app)

    # 1. GET /api/system/storage
    resp = client.get("/api/system/storage")
    assert resp.status_code == 200
    data = resp.json()
    assert "disk" in data
    assert "categories" in data
    assert data["categories"]["model_cache"]["is_protected"] is True

    # 2. POST /api/system/storage/clean
    clean_resp = client.post(
        "/api/system/storage/clean",
        json={"targets": ["temp_caches"], "older_than_days": 7},
    )
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["success"] is True
    assert "temp_caches" in clean_data["targets_processed"]
    assert "storage" in clean_data


def test_protection_model_cache_and_projects(db_session: Session):
    # Ensure attempting to target model_cache or projects is cleanly ignored
    model_dir = settings.DATA_DIR / "model_cache"
    projects_dir = settings.DATA_DIR / "projects"

    res = clean_storage(targets=["model_cache", "projects", "temp_caches"], db=db_session)
    assert res.success is True
    # Only temp_caches should be in processed targets
    assert "model_cache" not in res.targets_processed
    assert "projects" not in res.targets_processed
    assert model_dir.exists()
    assert projects_dir.exists()


def test_purge_all_user_data(db_session: Session):
    from app.services.storage_manager import purge_all_user_data
    res = purge_all_user_data(db=db_session, keep_models=True, keep_voice_profiles=True)
    assert res.success is True
    assert "all_user_data" in res.targets_processed
    assert (settings.DATA_DIR / "model_cache").exists()
    assert (settings.DATA_DIR / "voice_profiles").exists()
