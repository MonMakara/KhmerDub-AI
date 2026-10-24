from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "KhmerDub AI" in data["message"]
    assert "version" in data


def test_health_check_endpoint(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "KhmerDub AI"
    assert "version" in data
    assert "system_info" in data
    assert "ffmpeg_available" in data["system_info"]
