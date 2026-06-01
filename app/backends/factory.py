from app.backends import FakeBackend, InferenceBackend, OpenAICompatibleBackend
from app.core.settings import Settings


def build_backend(settings: Settings) -> InferenceBackend:
    if settings.backend == "fake":
        return FakeBackend(settings.model_id)
    if settings.backend == "openai_compatible":
        return OpenAICompatibleBackend(settings)
    raise ValueError(f"Backend not implemented yet: {settings.backend}")
