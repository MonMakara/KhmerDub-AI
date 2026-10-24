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
