import json
import logging

from fastapi.testclient import TestClient

from app.main import create_app


def _audit_records(caplog) -> list[dict]:
    records = []
    for r in caplog.records:
        if r.name.startswith("llm"):
            try:
                records.append(json.loads(r.getMessage()))
            except json.JSONDecodeError:
                pass
    return records


def _events(caplog, event: str) -> list[dict]:
    return [r for r in _audit_records(caplog) if r.get("event") == event]


# ── AuditLogMiddleware ─────────────────────────────────────────────────────────

def test_request_event_emitted_on_successful_get(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    events = _events(caplog, "request")
    assert len(events) == 1


def test_request_event_has_all_required_fields(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    for field in ("method", "path", "status", "duration_ms", "request_id", "client_ip", "key_prefix"):
        assert field in ev, f"missing field: {field}"


def test_request_event_records_correct_method_and_path(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    assert ev["method"] == "GET"
    assert ev["path"] == "/health"


def test_request_event_records_correct_status(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    assert ev["status"] == 200


def test_request_event_duration_is_positive_float(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    assert isinstance(ev["duration_ms"], float)
    assert ev["duration_ms"] > 0


def test_request_event_captures_custom_request_id(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health", headers={"x-request-id": "trace-abc"})

    ev = _events(caplog, "request")[0]
    assert ev["request_id"] == "trace-abc"


def test_request_event_generates_request_id_when_absent(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    assert ev["request_id"] is not None
    assert len(ev["request_id"]) > 0


def test_request_event_key_prefix_none_when_no_key(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    ev = _events(caplog, "request")[0]
    assert ev["key_prefix"] is None


def test_request_event_key_prefix_truncated_not_full_key(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "full-secret-key-here")
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health", headers={"x-api-key": "full-secret-key-here"})

    ev = _events(caplog, "request")[0]
    assert ev["key_prefix"] == "full-sec..."
    assert "full-secret-key-here" not in str(ev["key_prefix"])


def test_request_event_key_prefix_from_bearer_token(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health", headers={"authorization": "Bearer mytoken123"})

    ev = _events(caplog, "request")[0]
    assert ev["key_prefix"] == "mytoken1..."


def test_request_event_is_valid_json_string(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")

    json_records = [
        r for r in caplog.records
        if r.name.startswith("llm") and r.levelno == logging.INFO
    ]
    assert len(json_records) >= 1
    for r in json_records:
        parsed = json.loads(r.getMessage())
        assert isinstance(parsed, dict)


def test_request_event_emitted_for_post_endpoint(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    ev = _events(caplog, "request")[0]
    assert ev["method"] == "POST"
    assert ev["path"] == "/v1/completions"


def test_one_request_event_per_http_call(caplog):
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="llm"):
        client.get("/health")
        client.get("/version")

    events = _events(caplog, "request")
    assert len(events) == 2


# ── ApiKeyAuthMiddleware: auth_failed ─────────────────────────────────────────

def test_auth_failed_logged_when_no_key_provided(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "secret")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    assert len(_events(caplog, "auth_failed")) == 1


def test_auth_failed_logged_when_wrong_key_provided(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "correct-key")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", headers={"x-api-key": "wrong-key"}, json={"prompt": "hello"})

    assert len(_events(caplog, "auth_failed")) == 1


def test_auth_failed_log_has_correct_path(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "secret")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    ev = _events(caplog, "auth_failed")[0]
    assert ev["path"] == "/v1/completions"


def test_auth_failed_log_has_client_ip_field(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "secret")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    ev = _events(caplog, "auth_failed")[0]
    assert "client_ip" in ev


def test_auth_failed_log_request_id_field_present(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "secret")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    ev = _events(caplog, "auth_failed")[0]
    assert "request_id" in ev


def test_auth_failed_log_is_warning_level(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "secret")
    client = TestClient(create_app())
    with caplog.at_level(logging.DEBUG, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    warning_records = [
        r for r in caplog.records
        if r.name.startswith("llm") and r.levelno == logging.WARNING
    ]
    events = [json.loads(r.getMessage()) for r in warning_records if _is_json(r.getMessage())]
    auth_fails = [e for e in events if e.get("event") == "auth_failed"]
    assert len(auth_fails) == 1


def test_no_auth_failed_log_on_correct_key(monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEYS", "correct-key")
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", headers={"x-api-key": "correct-key"}, json={"prompt": "hello"})

    assert len(_events(caplog, "auth_failed")) == 0


def test_no_auth_failed_log_when_endpoint_is_open(caplog):
    client = TestClient(create_app())  # no LLM_API_KEYS set
    with caplog.at_level(logging.WARNING, logger="llm"):
        client.post("/v1/completions", json={"prompt": "hello"})

    assert len(_events(caplog, "auth_failed")) == 0


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False
