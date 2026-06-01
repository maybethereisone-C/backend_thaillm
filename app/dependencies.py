from functools import lru_cache

from app.backends import InferenceBackend
from app.backends.factory import build_backend
from app.core.settings import Settings, get_settings
from app.services.inference_service import InferenceService


@lru_cache
def get_inference_service() -> InferenceService:
    settings = get_settings()
    return InferenceService(backend=build_backend(settings), settings=settings)
