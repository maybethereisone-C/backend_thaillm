from app.backends.base import InferenceBackend
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


class FakeBackend(InferenceBackend):
    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        text = f"[fake:{self._model_id}] {request.prompt}"
        return CompletionResponse(
            model=request.model,
            choices=[CompletionChoice(index=0, text=text, finish_reason="stop")],
            usage=Usage(prompt_tokens=len(request.prompt.split()), completion_tokens=len(text.split())),
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        latest_user = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        content = f"[fake:{self._model_id}] {latest_user}"
        return ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=len(latest_user.split()), completion_tokens=len(content.split())),
        )

    async def health(self) -> BackendHealth:
        return BackendHealth(backend="fake", model=self._model_id, ready=True)
