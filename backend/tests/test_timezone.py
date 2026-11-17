"""Unit and integration tests for Cambodia Timezone (Asia/Phnom_Penh, UTC+7)."""
from fastapi.testclient import TestClient

from app.main import app
from app.core.timezone import get_cambodia_now, get_cambodia_now_naive
from app.models.project import Project, ProjectStatus
from app.models.toolkit import ToolkitTask


client = TestClient(app)


def test_cambodia_timezone_core_utilities():
    """Verify core timezone utilities generate accurate UTC+7 datetimes."""
    aware = get_cambodia_now()
    naive = get_cambodia_now_naive()

    # Timezone check
    assert aware.tzinfo is not None
    assert aware.utcoffset().total_seconds() == 7 * 3600  # UTC+7: 25200 seconds

    # Naive check
    assert naive.tzinfo is None
    # Hour difference between aware and naive should be identical minute/hour
    assert aware.hour == naive.hour
    assert aware.minute == naive.minute


def test_health_endpoint_timezone_info():
    """Verify /api/health returns configured timezone and current Cambodia timestamp."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    sys_info = data.get("system_info", {})
    assert sys_info.get("timezone") == "Asia/Phnom_Penh"

    curr_time_str = sys_info.get("current_time")
    assert curr_time_str is not None
    # Must end with +07:00
    assert "+07:00" in curr_time_str


def test_models_use_cambodia_timestamps(db_session):
    """Verify that Project and ToolkitTask entities store timestamps matching Cambodia local time."""
    now_naive = get_cambodia_now_naive()

    # Create project
    proj = Project(
        title="Timezone Test Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.CREATED,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    # Stored created_at should match current Cambodia hour
    assert proj.created_at is not None
    assert abs((proj.created_at - now_naive).total_seconds()) < 10

    # Create toolkit task
    task = ToolkitTask(
        tool_type="video_to_audio",
        source_filename="sample.mp4",
        source_file_path="/app/data/uploads/sample.mp4",
        status="pending",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.created_at is not None
    assert abs((task.created_at - now_naive).total_seconds()) < 10

    # Cleanup
    db_session.delete(proj)
    db_session.delete(task)
    db_session.commit()
