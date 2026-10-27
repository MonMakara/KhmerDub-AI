from fastapi.testclient import TestClient


def test_create_and_list_project(client: TestClient):
    # 1. Create a project
    payload = {
        "title": "Sample English Video",
        "original_language": "en",
        "target_language": "km",
    }
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201
    created_data = response.json()
    assert created_data["title"] == "Sample English Video"
    assert created_data["status"] == "created"
    assert "id" in created_data
    project_id = created_data["id"]

    # 2. List projects
    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    projects = list_response.json()
    assert len(projects) == 1
    assert projects[0]["id"] == project_id

    # 3. Get single project
    get_response = client.get(f"/api/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == project_id


def test_get_nonexistent_project(client: TestClient):
    response = client.get("/api/projects/non-existent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_get_project_with_dubbing_units(client: TestClient, db_session):
    from app.models.project import Project, TranslationSegment, ProjectStatus
    proj = Project(
        id="test-proj-dub-units",
        title="Dubbing Units Test",
        original_language="en",
        target_language="km",
        pipeline_version="v2.3",
        status=ProjectStatus.TRANSLATED,
    )
    db_session.add(proj)

    u1 = TranslationSegment(
        id="u1-test",
        project_id="test-proj-dub-units",
        segment_order=1,
        khmer_text="សួស្តី",
        source_segment_ids='["seg_1", "seg_2"]',
        source_text="Hello world.",
        start_time=0.0,
        end_time=3.5,
    )
    db_session.add(u1)
    db_session.commit()

    try:
        response = client.get("/api/projects/test-proj-dub-units")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-proj-dub-units"
        assert len(data["translation_segments"]) == 1
        seg0 = data["translation_segments"][0]
        assert seg0["source_segment_ids"] == ["seg_1", "seg_2"]
        assert seg0["source_text"] == "Hello world."
    finally:
        db_session.query(TranslationSegment).filter(TranslationSegment.project_id == "test-proj-dub-units").delete()
        db_session.query(Project).filter(Project.id == "test-proj-dub-units").delete()
        db_session.commit()
