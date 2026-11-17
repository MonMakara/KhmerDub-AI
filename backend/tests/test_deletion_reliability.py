import shutil
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    delete_project_storage,
    get_project_base_dir,
)
from app.core.recovery import recover_interrupted_deletions
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    JobStatus,
    ProjectStatus,
)


def test_startup_recovery_cleans_stuck_deleting_project(db_session: Session):
    """Verify that a backend restart recovers projects left in DELETING status."""
    # 1. Create a project directly in DB and set status to DELETING
    project = Project(
        title="Interrupted Deletion Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.DELETING,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    pid = project.id

    # Create related entities
    video = Video(
        project_id=pid,
        filename="test.mp4",
        file_path=str(settings.DATA_DIR / "uploads" / pid / "test.mp4"),
        file_size_bytes=1024,
        duration_seconds=5.0,
    )
    transcript = TranscriptSegment(
        project_id=pid,
        segment_order=0,
        start_time=0.0,
        end_time=2.0,
        text="Hello world",
    )
    translation = TranslationSegment(
        project_id=pid,
        segment_order=0,
        khmer_text="សួស្តីពិភពលោក",
        style="natural",
    )
    audio = GeneratedAudio(
        project_id=pid,
        translation_segment_id=translation.id,
        audio_path=str(settings.DATA_DIR / "projects" / pid / "generated_audio" / "segment_1.mp3"),
        duration_seconds=1.8,
    )
    job = ProcessingJob(
        project_id=pid,
        job_type="tts",
        status=JobStatus.COMPLETED,
    )
    db_session.add_all([video, transcript, translation, audio, job])
    db_session.commit()

    # Create dummy storage files
    proj_dir = get_project_base_dir(pid)
    (proj_dir / "dummy.txt").write_text("dummy project data")
    upload_dir = settings.UPLOADS_DIR / pid
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "test.mp4").write_text("dummy upload")

    assert proj_dir.exists()
    assert upload_dir.exists()

    # 2. Simulate startup recovery
    recovered_count = recover_interrupted_deletions(db_session)
    assert recovered_count == 1

    # 3. Verify project and all child DB records are completely gone
    assert db_session.query(Project).filter(Project.id == pid).first() is None
    assert db_session.query(Video).filter(Video.project_id == pid).first() is None
    assert db_session.query(TranscriptSegment).filter(TranscriptSegment.project_id == pid).first() is None
    assert db_session.query(TranslationSegment).filter(TranslationSegment.project_id == pid).first() is None
    assert db_session.query(GeneratedAudio).filter(GeneratedAudio.project_id == pid).first() is None
    assert db_session.query(ProcessingJob).filter(ProcessingJob.project_id == pid).first() is None

    # 4. Verify storage is deleted
    assert not proj_dir.exists()
    assert not upload_dir.exists()

    # 5. Subsequent run is idempotent
    second_run = recover_interrupted_deletions(db_session)
    assert second_run == 0


def test_resuming_interrupted_deletion_via_api(client: TestClient, db_session: Session):
    """Verify that retrying DELETE on a project already in DELETING safely finishes Stage 2."""
    create_res = client.post("/api/projects", json={"title": "Retry Deletion Project"})
    assert create_res.status_code == 201
    pid = create_res.json()["id"]

    # Create dummy files
    proj_dir = get_project_base_dir(pid)
    (proj_dir / "data.bin").write_text("some audio bytes")

    # Simulate Stage 1 was marked DELETING before an interruption/timeout
    proj = db_session.query(Project).filter(Project.id == pid).first()
    proj.status = ProjectStatus.DELETING
    db_session.commit()

    # Retrying DELETE should resume Stage 2 and succeed with 200 OK (not 409!)
    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 200
    assert del_res.json()["id"] == pid

    # Project and files are gone
    assert not proj_dir.exists()
    assert db_session.query(Project).filter(Project.id == pid).first() is None

    # Subsequent DELETE returns 404
    retry_res = client.delete(f"/api/projects/{pid}")
    assert retry_res.status_code == 404


def test_cleanup_idempotency_and_missing_files():
    """Verify delete_project_storage handles missing files and repeated calls safely."""
    non_existent_id = "proj-non-existent-12345"
    # Call 1: Directory does not exist
    res1 = delete_project_storage(non_existent_id)
    assert res1["deleted_count"] == 0
    assert res1["deleted_paths"] == []

    # Call 2: Repeat call is idempotent
    res2 = delete_project_storage(non_existent_id)
    assert res2["deleted_count"] == 0

    # Call 3: Partially created directory
    partial_dir = settings.DATA_DIR / "projects" / non_existent_id / "original"
    partial_dir.mkdir(parents=True, exist_ok=True)
    assert (settings.DATA_DIR / "projects" / non_existent_id).exists()

    res3 = delete_project_storage(non_existent_id)
    assert res3["deleted_count"] >= 1
    assert not (settings.DATA_DIR / "projects" / non_existent_id).exists()

    # Call 4: Again after deletion
    res4 = delete_project_storage(non_existent_id)
    assert res4["deleted_count"] == 0


def test_active_job_check_and_deletion_lockdown(client: TestClient, db_session: Session):
    """Verify active jobs prevent deletion, and DELETING status locks down all project mutations."""
    # 1. Project with active background job cannot be deleted
    create_res = client.post("/api/projects", json={"title": "Active Job Project"})
    assert create_res.status_code == 201
    pid = create_res.json()["id"]

    job = ProcessingJob(
        project_id=pid,
        job_type="translate",
        status=JobStatus.RUNNING,
    )
    db_session.add(job)
    db_session.commit()

    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 409
    assert "active background processing jobs" in del_res.json()["detail"]

    # Mark job as failed to unlock
    job.status = JobStatus.FAILED
    db_session.commit()

    # 2. Deletion lockdown: Once status is DELETING, new operations are rejected with 409
    proj = db_session.query(Project).filter(Project.id == pid).first()
    proj.status = ProjectStatus.DELETING
    db_session.commit()

    assert client.get(f"/api/projects/{pid}").status_code == 409
    assert client.patch(f"/api/projects/{pid}", json={"title": "Rename Attempt"}).status_code == 409
    assert client.patch(f"/api/projects/{pid}/voice", json={"tts_provider": "google", "tts_voice": "default"}).status_code == 409
    assert client.patch(f"/api/projects/{pid}/translation-settings", json={"translation_provider": "nllb", "translation_style": "natural"}).status_code == 409
    assert client.post(f"/api/projects/{pid}/extract-audio").status_code == 409
    assert client.post(f"/api/projects/{pid}/transcribe").status_code == 409
    assert client.post(f"/api/projects/{pid}/translate").status_code == 409
    assert client.post(f"/api/projects/{pid}/tts").status_code == 409
    assert client.post(f"/api/projects/{pid}/export").status_code == 409

    # Clean up project
    client.delete(f"/api/projects/{pid}")


def test_symlink_safety_outside_project_directories():
    """Verify that symlinks inside or as project directories never delete external files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        external_secret = tmp_path / "secret_document.txt"
        external_secret.write_text("SUPER_SECRET_PAYLOAD")

        external_folder = tmp_path / "external_folder"
        external_folder.mkdir()
        (external_folder / "file.txt").write_text("in_folder")

        test_pid = "symlink_test_project_99"
        proj_dir = settings.DATA_DIR / "projects" / test_pid
        proj_dir.mkdir(parents=True, exist_ok=True)

        # 1. Symlink inside project pointing to external file
        symlink_to_file = proj_dir / "link_to_secret.txt"
        symlink_to_file.symlink_to(external_secret)

        # 2. Symlink inside project pointing to external directory
        symlink_to_dir = proj_dir / "link_to_folder"
        symlink_to_dir.symlink_to(external_folder)

        # 3. Symlink in temp directory pointing to external file
        temp_dir = settings.TEMP_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_symlink = temp_dir / f"tts_{test_pid}_external_link.mp3"
        temp_symlink.symlink_to(external_secret)

        try:
            # Delete project storage
            delete_info = delete_project_storage(test_pid)
            assert delete_info["deleted_count"] >= 1

            # Verify project directory was removed
            assert not proj_dir.exists()

            # CRITICAL VERIFICATION: External files and directories MUST REMAIN UNTOUCHED
            assert external_secret.exists(), "External secret file was deleted by project cleanup!"
            assert external_secret.read_text() == "SUPER_SECRET_PAYLOAD"
            assert external_folder.exists(), "External folder was deleted by project cleanup!"
            assert (external_folder / "file.txt").exists()
            assert not temp_symlink.exists(), "Temp symlink was not removed"

        finally:
            if proj_dir.exists():
                shutil.rmtree(proj_dir, ignore_errors=True)
            if temp_symlink.exists():
                temp_symlink.unlink(missing_ok=True)


def test_symlink_as_project_root_safety():
    """Verify that if a project root itself is a symlink, only the symlink is removed, not target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        target_dir = tmp_path / "target_dir_to_preserve"
        target_dir.mkdir()
        (target_dir / "preserve_me.txt").write_text("important data")

        test_pid = "root_symlink_test_pid"
        link_path = settings.DATA_DIR / "projects" / test_pid

        if link_path.exists() or link_path.is_symlink():
            if link_path.is_symlink():
                link_path.unlink()
            else:
                shutil.rmtree(link_path)

        link_path.symlink_to(target_dir)
        assert link_path.is_symlink()

        try:
            delete_info = delete_project_storage(test_pid)
            assert str(link_path) in delete_info["deleted_paths"]

            # Symlink must be removed
            assert not link_path.is_symlink()
            assert not link_path.exists()

            # Target directory and its contents must remain completely intact!
            assert target_dir.exists()
            assert (target_dir / "preserve_me.txt").exists()
            assert (target_dir / "preserve_me.txt").read_text() == "important data"

        finally:
            if link_path.is_symlink():
                link_path.unlink()


def test_shared_resources_and_unrelated_projects_preserved(client: TestClient, db_session: Session):
    """Verify shared system files, model cache volume, credentials, and other projects are untouched."""
    # Create Project 1 (to delete)
    p1_res = client.post("/api/projects", json={"title": "Project to Delete"})
    p1_id = p1_res.json()["id"]
    p1_dir = get_project_base_dir(p1_id)
    (p1_dir / "p1_asset.txt").write_text("p1 assets")

    # Create Project 2 (sibling to preserve)
    p2_res = client.post("/api/projects", json={"title": "Project to Keep"})
    p2_id = p2_res.json()["id"]
    p2_dir = get_project_base_dir(p2_id)
    (p2_dir / "p2_asset.txt").write_text("p2 assets")

    # Verify shared files exist or are simulated
    secrets_dir = settings.DATA_DIR / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    dummy_secret = secrets_dir / "dummy_keep.enc"
    dummy_secret.write_text("KEEP_THIS_SECRET")

    try:
        # Delete Project 1
        del_res = client.delete(f"/api/projects/{p1_id}")
        assert del_res.status_code == 200

        # Project 1 is gone
        assert not p1_dir.exists()
        assert db_session.query(Project).filter(Project.id == p1_id).first() is None

        # Project 2 is 100% intact
        assert p2_dir.exists()
        assert (p2_dir / "p2_asset.txt").read_text() == "p2 assets"
        assert db_session.query(Project).filter(Project.id == p2_id).first() is not None

        # Shared files are 100% intact
        assert dummy_secret.exists()
        assert dummy_secret.read_text() == "KEEP_THIS_SECRET"

        # Database file exists and is intact
        db_file = settings.DATA_DIR / "khmerdub.db"
        assert db_file.exists()

    finally:
        client.delete(f"/api/projects/{p2_id}")
        if dummy_secret.exists():
            dummy_secret.unlink()
