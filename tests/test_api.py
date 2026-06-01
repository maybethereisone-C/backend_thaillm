from fastapi.testclient import TestClient

from app.main import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["backend"]["backend"] == "fake"
    assert body["backend"]["ready"] is True


def test_version() -> None:
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "0.1.0"
    assert body["backend"] == "fake"


def test_chat_completion_accepts_thai() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "สวัสดี อธิบาย LLM แบบสั้นๆ"}
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert "สวัสดี" in body["choices"][0]["message"]["content"]


def test_completion_accepts_prompt() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/completions",
        json={"prompt": "Python OOP คืออะไร"},
    )

    assert response.status_code == 200
    assert "Python OOP" in response.json()["choices"][0]["text"]
