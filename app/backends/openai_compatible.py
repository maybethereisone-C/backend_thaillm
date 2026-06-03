import httpx
from collections.abc import Callable

from app.backends.base import InferenceBackend
from app.core.errors import BackendUnavailableError
from app.core.settings import Settings
from app.schemas.health import BackendHealth
from app.schemas.inference import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
    Usage,
)


class OpenAICompatibleBackend(InferenceBackend):
    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        if settings.upstream_base_url is None:
            raise ValueError("upstream_base_url is required")
        self._base_url = str(settings.upstream_base_url).rstrip("/")
        self._client_factory = client_factory

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = await self._post(
            "/completions",
            {
                "model": request.model,
                "prompt": request.prompt,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        )
        choices = [
            CompletionChoice(
                index=choice.get("index", index),
                text=str(choice.get("text", "")),
                finish_reason=choice.get("finish_reason"),
            )
            for index, choice in enumerate(payload.get("choices", []))
            if isinstance(choice, dict)
        ]
        return CompletionResponse(
            model=str(payload.get("model", request.model)),
            choices=choices,
            usage=self._usage(payload.get("usage")),
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = await self._post(
            "/chat/completions",
            {
                "model": request.model,
                "messages": [message.model_dump() for message in request.messages],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        )
        choices = [
            ChatChoice(
                index=choice.get("index", index),
                message=self._message(choice.get("message")),
                finish_reason=choice.get("finish_reason"),
            )
            for index, choice in enumerate(payload.get("choices", []))
            if isinstance(choice, dict)
        ]
        return ChatCompletionResponse(
            model=str(payload.get("model", request.model)),
            choices=choices,
            usage=self._usage(payload.get("usage")),
        )

    async def health(self) -> BackendHealth:
        try:
            async with self._client_factory(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.get(f"{self._base_url}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError:
            # Do not surface str(exc); it contains the upstream URL on the public /health.
            return BackendHealth(
                backend="openai_compatible",
                model=self._settings.model_id,
                ready=False,
                detail="upstream unreachable",
            )

        return BackendHealth(backend="openai_compatible", model=self._settings.model_id, ready=True)

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with self._client_factory(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(f"{self._base_url}{path}", headers=self._headers(), json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError("inference backend timeout") from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("inference backend request failed") from exc

        data = response.json()
        if not isinstance(data, dict):
            raise BackendUnavailableError("inference backend returned invalid response")
        return data

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._settings.upstream_api_key:
            headers["Authorization"] = f"Bearer {self._settings.upstream_api_key.get_secret_value()}"
        return headers

    def _message(self, value: object) -> ChatMessage:
        if isinstance(value, dict):
            role = value.get("role", "assistant")
            content = value.get("content", "")
            if role in {"system", "user", "assistant"}:
                return ChatMessage(role=role, content=str(content) or " ")
        return ChatMessage(role="assistant", content=" ")

    def _usage(self, value: object) -> Usage:
        if not isinstance(value, dict):
            return Usage()
        return Usage(
            prompt_tokens=int(value.get("prompt_tokens", 0) or 0),
            completion_tokens=int(value.get("completion_tokens", 0) or 0),
        )
