from pydantic import BaseModel


class BackendHealth(BaseModel):
    backend: str
    model: str
    ready: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    backend: BackendHealth


class VersionResponse(BaseModel):
    api_version: str
    backend: str
    model: str
