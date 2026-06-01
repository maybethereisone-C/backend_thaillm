import httpx
import pytest

from app.backends.openai_compatible import OpenAICompatibleBackend
from app.core.errors import BackendUnavailableError
from app.core.settings import Settings
from app.schemas.inference import ChatCompletionRequest, ChatMessage, CompletionRequest


@pytest.mark.anyio
async def test_openai_compatible_completion_maps_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/completions"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"index": 0, "text": "hello", "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    backend = OpenAICompatibleBackend(
        Settings(backend="openai_compatible", model_id="test-model", upstream_base_url="http://api.local/v1"),
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await backend.complete(CompletionRequest(model="test-model", prompt="hi"))

    assert response.model == "test-model"
    assert response.choices[0].text == "hello"
    assert response.usage.total_tokens == 2


@pytest.mark.anyio
async def test_openai_compatible_chat_maps_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "สวัสดี"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    backend = OpenAICompatibleBackend(
        Settings(backend="openai_compatible", model_id="test-model", upstream_base_url="http://api.local/v1"),
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await backend.chat(
        ChatCompletionRequest(model="test-model", messages=[ChatMessage(role="user", content="hi")])
    )

    assert response.choices[0].message.content == "สวัสดี"


@pytest.mark.anyio
async def test_openai_compatible_errors_are_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    backend = OpenAICompatibleBackend(
        Settings(backend="openai_compatible", upstream_base_url="http://api.local/v1"),
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(BackendUnavailableError, match="request failed"):
        await backend.complete(CompletionRequest(prompt="hi"))
