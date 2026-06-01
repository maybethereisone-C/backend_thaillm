import pytest

from app.backends.factory import build_backend
from app.backends.fake import FakeBackend
from app.backends.openai_compatible import OpenAICompatibleBackend
from app.core.settings import Settings


def test_backend_factory_builds_fake_backend() -> None:
    backend = build_backend(Settings(backend="fake"))

    assert isinstance(backend, FakeBackend)


def test_backend_factory_builds_openai_compatible_backend() -> None:
    backend = build_backend(Settings(backend="openai_compatible", upstream_base_url="http://api.local/v1"))

    assert isinstance(backend, OpenAICompatibleBackend)


def test_backend_factory_rejects_unimplemented_backend() -> None:
    with pytest.raises(ValueError, match="Backend not implemented yet"):
        build_backend(Settings.model_construct(backend="unsupported"))
