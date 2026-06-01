import pytest

from app.core.settings import get_settings
from app.dependencies import get_inference_service


@pytest.fixture(autouse=True)
def clear_cached_dependencies(monkeypatch):
    # Isolate tests from local .env — always start with fake backend.
    # Tests that need a different backend override via their own monkeypatch.setenv.
    monkeypatch.setenv("THAILLM_BACKEND", "fake")
    get_settings.cache_clear()
    get_inference_service.cache_clear()
    yield
    get_settings.cache_clear()
    get_inference_service.cache_clear()
