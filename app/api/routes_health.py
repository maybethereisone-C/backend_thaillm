from fastapi import APIRouter, Depends

from app.core.settings import Settings, get_settings
from app.schemas.health import HealthResponse, VersionResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
async def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(
        api_version=settings.api_version,
        model=settings.thaillm_model_id,
    )
