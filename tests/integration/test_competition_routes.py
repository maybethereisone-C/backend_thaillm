import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_AUDIT_TRAIL_DIR", str(tmp_path / "audit_trails"))
    monkeypatch.setenv("LLM_AGENT_DB_PATH", "/nonexistent/db.db")
    monkeypatch.setenv("LLM_AGENT_SRC_PATH", "/nonexistent/src")
    monkeypatch.setenv("LLM_THAILLM_BASE_URL", "http://fake-thaillm.example.com/v1")
    monkeypatch.setenv("LLM_THAILLM_MODEL_ID", "thai-model")
    return TestClient(create_app())


def _mock_run_agent():
    trace = json.dumps([{"step": 0, "action": "sql"}, {"step": 1, "action": "final"}])
    return AsyncMock(return_value=("ตอบ 45900 บาท", 128, trace))


def test_agent_thaillm_returns_competition_shape(client):
    with patch("app.api.routes_competition._run_agent", _mock_run_agent()):
        r = client.post("/agent/thaillm", json={"question": "test question"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"id", "answer", "total_output_token_count"}
    assert body["answer"] == "ตอบ 45900 บาท"
    assert body["total_output_token_count"] == 128


def test_agent_thaillm_writes_audit_trail(client, tmp_path, monkeypatch):
    audit_dir = tmp_path / "audit_trails"
    monkeypatch.setenv("LLM_AUDIT_TRAIL_DIR", str(audit_dir))
    with patch("app.api.routes_competition._run_agent", _mock_run_agent()):
        r = client.post("/agent/thaillm", json={"question": "test"})
    assert (audit_dir / f"{r.json()['id']}.txt").exists()


def test_agent_thaillm_rejects_empty_question(client):
    r = client.post("/agent/thaillm", json={"question": ""})
    assert r.status_code == 422


def test_agent_thaillm_rejects_oversized_question(client):
    r = client.post("/agent/thaillm", json={"question": "x" * 4097})
    assert r.status_code == 422


def test_competition_endpoint_bypasses_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", '["secret-key"]')
    monkeypatch.setenv("LLM_AUDIT_TRAIL_DIR", str(tmp_path / "audit_trails"))
    monkeypatch.setenv("LLM_AGENT_DB_PATH", "/nonexistent/db.db")
    monkeypatch.setenv("LLM_AGENT_SRC_PATH", "/nonexistent/src")
    monkeypatch.setenv("LLM_THAILLM_BASE_URL", "http://fake.internal/v1")
    monkeypatch.setenv("LLM_THAILLM_MODEL_ID", "model")
    c = TestClient(create_app())
    with patch("app.api.routes_competition._run_agent", _mock_run_agent()):
        r = c.post("/agent/thaillm", json={"question": "test"})
    assert r.status_code == 200
