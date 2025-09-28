from fastapi.testclient import TestClient

from neuralmonitor.api.app import create_app


def test_api_default_session_health_diagnostics_and_close(tmp_path):
    client = TestClient(create_app(str(tmp_path / "api.db")))

    session_response = client.post("/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    health_response = client.post(
        f"/sessions/{session_id}/health",
        json={"battery_percent": 10, "buffer_depth": 7000},
    )
    assert health_response.status_code == 200

    diagnostics = client.get(f"/sessions/{session_id}/diagnostics").json()
    assert diagnostics["recorder_status"] == "degraded"
    assert diagnostics["open_alert_count"] == 2

    end_response = client.post(f"/sessions/{session_id}/end")
    assert end_response.status_code == 200
    assert end_response.json()["status"] == "ended"

    assert client.post(f"/sessions/{session_id}/simulate").status_code == 409


def test_api_rejects_invalid_base64_frame(tmp_path):
    client = TestClient(create_app(str(tmp_path / "api.db")))
    session_id = client.post("/sessions").json()["id"]

    response = client.post(f"/sessions/{session_id}/frames", json={"frame_b64": "not base64"})

    assert response.status_code == 422
    assert "valid base64" in response.json()["detail"]
