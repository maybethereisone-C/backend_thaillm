from fastapi import APIRouter, Depends

from app.core.settings import Settings, get_settings
from app.dependencies import get_inference_service
from app.schemas.health import HealthResponse, VersionResponse
from app.services.inference_service import InferenceService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(service: InferenceService = Depends(get_inference_service)) -> HealthResponse:
    backend_health = await service.health()
    return HealthResponse(status="ok" if backend_health.ready else "degraded", backend=backend_health)


@router.get("/version", response_model=VersionResponse)
async def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(
        api_version=settings.api_version,
        backend=settings.backend,
        model=settings.model_id,
    )
