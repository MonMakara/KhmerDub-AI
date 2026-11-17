import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    get_project_base_dir,
    get_project_original_dir,
    delete_project_storage,
    sanitize_project_id,
)
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)


def test_rename_project_success(client: TestClient):
    # 1. Create project
    create_res = client.post("/api/projects", json={"title": "Original Project Title"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Rename project
    new_title = "Renamed Project Title"
    patch_res = client.patch(f"/api/projects/{project_id}", json={"title": new_title})
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["title"] == new_title
    assert updated_data["id"] == project_id

    # 3. Verify get project reflects new name
    get_res = client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == new_title


def test_rename_project_empty_or_whitespace(client: TestClient):
    create_res = client.post("/api/projects", json={"title": "Valid Initial Title"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Empty string
    patch_empty = client.patch(f"/api/projects/{project_id}", json={"title": ""})
    assert patch_empty.status_code == 422

    # Whitespace only
    patch_ws = client.patch(f"/api/projects/{project_id}", json={"title": "    \t \n  "})
    assert patch_ws.status_code == 422


def test_rename_project_too_long(client: TestClient):
    create_res = client.post("/api/projects", json={"title": "Short Title"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    too_long = "A" * 256
    patch_res = client.patch(f"/api/projects/{project_id}", json={"title": too_long})
    assert patch_res.status_code == 422


def test_rename_project_nonexistent(client: TestClient):
    patch_res = client.patch("/api/projects/non-existent-uuid", json={"title": "Any Title"})
    assert patch_res.status_code == 404
    assert patch_res.json()["detail"] == "Project not found"


def test_delete_project_success(client: TestClient, db_session: Session):
    # 1. Create project
    create_res = client.post("/api/projects", json={"title": "Project To Delete"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Add child database records
    video = Video(
        project_id=project_id,
        filename="test.mp4",
        file_path="/app/data/uploads/dummy.mp4",
        file_size_bytes=1024,
    )
    transcript_seg = TranscriptSegment(
        project_id=project_id,
        segment_order=1,
        start_time=0.0,
        end_time=2.0,
        text="Hello world",
    )
    db_session.add(video)
    db_session.add(transcript_seg)
    db_session.commit()

    trans_seg = TranslationSegment(
        project_id=project_id,
        transcript_segment_id=transcript_seg.id,
        segment_order=1,
        khmer_text="សួស្តីពិភពលោក",
    )
    db_session.add(trans_seg)
    db_session.commit()

    gen_audio = GeneratedAudio(
        project_id=project_id,
        translation_segment_id=trans_seg.id,
        audio_path="/app/data/projects/dummy.mp3",
    )
    job = ProcessingJob(
        project_id=project_id,
        job_type="extract_audio",
        status=JobStatus.COMPLETED,
    )
    db_session.add(gen_audio)
    db_session.add(job)
    db_session.commit()

    # 3. Create real dummy files in project storage
    base_dir = get_project_base_dir(project_id)
    orig_dir = get_project_original_dir(project_id)
    test_file = orig_dir / "sample.txt"
    test_file.write_text("dummy media content")
    assert test_file.exists()

    # Uploads dir
    upload_dir = settings.UPLOADS_DIR / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_file = upload_dir / "video.mp4"
    upload_file.write_text("video dummy")
    assert upload_file.exists()

    # 4. Delete project
    del_res = client.delete(f"/api/projects/{project_id}")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["id"] == project_id
    assert "successfully deleted" in del_data["message"].lower()

    # 5. Verify database records are completely gone
    assert db_session.query(Project).filter(Project.id == project_id).first() is None
    assert db_session.query(Video).filter(Video.project_id == project_id).first() is None
    assert db_session.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).first() is None
    assert db_session.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).first() is None
    assert db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).first() is None
    assert db_session.query(ProcessingJob).filter(ProcessingJob.project_id == project_id).first() is None

    # 6. Verify files on disk are removed
    assert not base_dir.exists()
    assert not upload_dir.exists()


def test_delete_project_nonexistent(client: TestClient):
    del_res = client.delete("/api/projects/non-existent-uuid")
    assert del_res.status_code == 404
    assert del_res.json()["detail"] == "Project not found"


def test_delete_project_with_active_job_conflict(client: TestClient, db_session: Session):
    create_res = client.post("/api/projects", json={"title": "Active Job Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Add active running job
    job = ProcessingJob(
        project_id=project_id,
        job_type="transcribe",
        status=JobStatus.RUNNING,
        progress_percentage=45,
    )
    db_session.add(job)
    db_session.commit()

    # Attempt delete
    del_res = client.delete(f"/api/projects/{project_id}")
    assert del_res.status_code == 409
    assert "active background processing jobs" in del_res.json()["detail"]

    # Verify project still exists
    assert db_session.query(Project).filter(Project.id == project_id).first() is not None


def test_delete_project_with_active_status_conflict(client: TestClient, db_session: Session):
    create_res = client.post("/api/projects", json={"title": "Active Status Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Update project status to TRANSLATING
    proj = db_session.query(Project).filter(Project.id == project_id).first()
    proj.status = ProjectStatus.TRANSLATING
    db_session.commit()

    # Attempt delete
    del_res = client.delete(f"/api/projects/{project_id}")
    assert del_res.status_code == 409
    assert "active background processing jobs" in del_res.json()["detail"]

    # Verify project still exists
    assert db_session.query(Project).filter(Project.id == project_id).first() is not None


def test_delete_project_preserves_other_projects(client: TestClient, db_session: Session):
    # Create Project A
    res_a = client.post("/api/projects", json={"title": "Project A"})
    id_a = res_a.json()["id"]
    dir_a = get_project_base_dir(id_a)
    (dir_a / "file_a.txt").write_text("data a")

    # Create Project B
    res_b = client.post("/api/projects", json={"title": "Project B"})
    id_b = res_b.json()["id"]
    dir_b = get_project_base_dir(id_b)
    (dir_b / "file_b.txt").write_text("data b")

    try:
        # Delete Project A
        del_a = client.delete(f"/api/projects/{id_a}")
        assert del_a.status_code == 200

        # Verify Project A gone
        assert not dir_a.exists()
        assert db_session.query(Project).filter(Project.id == id_a).first() is None

        # Verify Project B completely untouched!
        assert dir_b.exists()
        assert (dir_b / "file_b.txt").read_text() == "data b"
        assert db_session.query(Project).filter(Project.id == id_b).first() is not None
    finally:
        # Clean up Project B
        client.delete(f"/api/projects/{id_b}")


def test_delete_project_path_traversal_prevention():
    # Attempt path traversal
    with pytest.raises(ValueError):
        sanitize_project_id("../../../etc")

    with pytest.raises(ValueError):
        sanitize_project_id("..")

    with pytest.raises(ValueError):
        delete_project_storage("../../../etc")


def test_duplicate_delete_returns_404(client: TestClient):
    create_res = client.post("/api/projects", json={"title": "Delete Twice Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # First delete
    first_del = client.delete(f"/api/projects/{project_id}")
    assert first_del.status_code == 200

    # Second delete
    second_del = client.delete(f"/api/projects/{project_id}")
    assert second_del.status_code == 404
    assert second_del.json()["detail"] == "Project not found"


def test_mutations_on_deleting_project_rejected(client: TestClient, db_session: Session):
    create_res = client.post("/api/projects", json={"title": "Deleting Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Mark as DELETING
    proj = db_session.query(Project).filter(Project.id == project_id).first()
    proj.status = ProjectStatus.DELETING
    db_session.commit()

    # Attempt rename
    rename_res = client.patch(f"/api/projects/{project_id}", json={"title": "New Title"})
    assert rename_res.status_code == 409

    # Attempt extract-audio
    extract_res = client.post(f"/api/projects/{project_id}/extract-audio")
    assert extract_res.status_code == 409


def test_dashboard_projects_listing_after_deletion(client: TestClient):
    # Initial count
    initial_res = client.get("/api/projects")
    assert initial_res.status_code == 200
    initial_count = len(initial_res.json())

    # Create new project
    c_res = client.post("/api/projects", json={"title": "To Be Deleted From Dashboard"})
    assert c_res.status_code == 201
    pid = c_res.json()["id"]

    # List again -> count increased by 1
    after_create_res = client.get("/api/projects")
    assert len(after_create_res.json()) == initial_count + 1

    # Delete project
    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 200

    # List again -> count back to initial_count
    after_del_res = client.get("/api/projects")
    assert len(after_del_res.json()) == initial_count
    assert not any(p["id"] == pid for p in after_del_res.json())

