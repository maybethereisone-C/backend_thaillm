import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_openai_compatible_backend_requires_upstream_base_url() -> None:
    with pytest.raises(ValidationError, match="LLM_UPSTREAM_BASE_URL"):
        Settings(backend="openai_compatible", upstream_base_url=None)


def test_fake_backend_does_not_require_upstream_base_url() -> None:
    settings = Settings(backend="fake", upstream_base_url=None)

    assert settings.upstream_base_url is None
