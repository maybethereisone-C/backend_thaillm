from fastapi import APIRouter, Depends

from app.dependencies import get_inference_service
from app.schemas.inference import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionRequest,
    CompletionResponse,
)
from app.services.inference_service import InferenceService

router = APIRouter(prefix="/v1", tags=["inference"])


@router.post("/completions", response_model=CompletionResponse)
async def completions(
    request: CompletionRequest,
    service: InferenceService = Depends(get_inference_service),
) -> CompletionResponse:
    return await service.complete(request)


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    service: InferenceService = Depends(get_inference_service),
) -> ChatCompletionResponse:
    return await service.chat(request)
