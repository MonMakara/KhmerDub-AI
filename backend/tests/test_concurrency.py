import concurrent.futures
import threading
import time
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.session import SessionLocal, engine
from app.core.ai_guard import acquire_ai_inference_slot, get_active_ai_models, get_active_ai_model
from app.models.toolkit import ToolkitTask

client = TestClient(app)


def test_sqlite_wal_mode_and_timeout():
    """Verify that SQLite Write-Ahead Logging (WAL) and 30s busy timeout are active."""
    with SessionLocal() as db:
        journal_mode = db.execute(text("PRAGMA journal_mode;")).scalar()
        busy_timeout = db.execute(text("PRAGMA busy_timeout;")).scalar()
        synchronous = db.execute(text("PRAGMA synchronous;")).scalar()

    assert str(journal_mode).lower() == "wal", f"Expected WAL mode, got {journal_mode}"
    assert busy_timeout >= 30000, f"Expected busy_timeout >= 30000ms, got {busy_timeout}"
    assert synchronous in (1, "1", "NORMAL", "normal"), f"Expected synchronous NORMAL, got {synchronous}"


def test_concurrent_database_writes():
    """Verify that multiple concurrent threads can write and read from SQLite simultaneously without lock errors."""
    def write_worker(worker_id: int):
        with SessionLocal() as db:
            task = ToolkitTask(
                id=f"concurrent-test-task-{worker_id}-{int(time.time()*1000)}",
                tool_type="video_to_audio",
                source_type="upload",
                source_filename=f"video_{worker_id}.mp4",
                source_file_path=f"/tmp/video_{worker_id}.mp4",
                target_format="mp3",
                status="completed",
                progress_percentage=100,
            )
            db.add(task)
            db.commit()
            task_id = task.id

        with SessionLocal() as db:
            fetched = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
            assert fetched is not None
            db.delete(fetched)
            db.commit()

        return worker_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(write_worker, i) for i in range(16)]
        results = [f.result() for f in futures]

    assert len(results) == 16


def test_ai_inference_guard_concurrency_slots():
    """Verify that the AI guard permits concurrent acquisition of slots up to the configured limit."""
    barrier = threading.Barrier(2)
    acquired_models = []
    lock = threading.Lock()

    def run_slot(name: str):
        with acquire_ai_inference_slot(name, timeout=5.0):
            with lock:
                acquired_models.append(name)
            barrier.wait(timeout=5.0)
            time.sleep(0.05)

    t1 = threading.Thread(target=run_slot, args=("Model_A",))
    t2 = threading.Thread(target=run_slot, args=("Model_B",))

    t1.start()
    t2.start()

    t1.join(timeout=6.0)
    t2.join(timeout=6.0)

    assert "Model_A" in acquired_models
    assert "Model_B" in acquired_models
    assert get_active_ai_model() is None
