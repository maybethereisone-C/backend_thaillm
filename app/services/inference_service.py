import asyncio

from app.backends.base import InferenceBackend
from app.core.errors import BackendUnavailableError, RequestPolicyError
from app.core.security import OutputGuard, PromptInjectionGuard
from app.core.settings import Settings
from app.schemas.health import BackendHealth
from app.schemas.inference import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionRequest,
    CompletionResponse,
)


class InferenceService:
    def __init__(self, backend: InferenceBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings
        self._prompt_guard = PromptInjectionGuard()
        self._output_guard = OutputGuard()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        request = request.model_copy(update=self._default_updates(request.model, request.max_tokens))
        self._enforce_prompt_guard([request.prompt])
        response = await self._call_with_timeout(self._backend.complete(request))
        self._enforce_response_limits([choice.text for choice in response.choices])
        return response

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        request = request.model_copy(update=self._default_updates(request.model, request.max_tokens))
        self._enforce_prompt_guard([message.content for message in request.messages])
        response = await self._call_with_timeout(self._backend.chat(request))
        self._enforce_response_limits([choice.message.content for choice in response.choices])
        return response

    async def health(self) -> BackendHealth:
        return await self._backend.health()

    def _default_updates(self, model: str | None, max_tokens: int | None) -> dict:
        return {
            "model": model or self._settings.model_id,
            "max_tokens": max_tokens or self._settings.max_tokens_default,
        }

    def _enforce_prompt_guard(self, values: list[str]) -> None:
        if not self._settings.prompt_guard_enabled:
            return
        for value in values:
            self._prompt_guard.enforce_text(value)

    async def _call_with_timeout(self, call):
        try:
            return await asyncio.wait_for(call, timeout=self._settings.request_timeout_seconds)
        except TimeoutError as exc:
            raise BackendUnavailableError("inference backend timeout") from exc

    def _enforce_response_limits(self, values: list[str]) -> None:
        for value in values:
            try:
                self._output_guard.enforce_text(value)
            except RequestPolicyError as exc:
                raise BackendUnavailableError(exc.message) from exc
