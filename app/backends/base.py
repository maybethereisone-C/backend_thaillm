from abc import ABC, abstractmethod

from app.schemas.health import BackendHealth
from app.schemas.inference import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionRequest,
    CompletionResponse,
)


class InferenceBackend(ABC):
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse: ...

    @abstractmethod
    async def health(self) -> BackendHealth: ...
