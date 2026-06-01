from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_inference import router as inference_router
from app.core.errors import AppError
from app.core.settings import get_settings
from app.mcp_server import create_mcp_server
from app.middleware import (
    ApiKeyAuthMiddleware,
    AuditLogMiddleware,
    BodySizeLimitMiddleware,
    InMemoryRateLimitMiddleware,
    OriginValidationMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)


def create_app() -> FastAPI:
    settings = get_settings()
    mcp_app = None
    if settings.mcp_enabled:
        mcp_app = create_mcp_server(settings).http_app(path="/")

    app = FastAPI(
        title="ThaiLLM Backend API",
        version=settings.api_version,
        lifespan=mcp_app.lifespan if mcp_app else None,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        ApiKeyAuthMiddleware,
        api_keys=settings.api_keys,
        protected_prefixes=("/v1", "/mcp"),
    )
    app.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=settings.allowed_origins,
        protected_prefixes=("/mcp",),
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.request_body_limit_bytes)
    app.add_middleware(InMemoryRateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["authorization", "content-type", "x-api-key", "x-request-id"],
        )
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "detail": exc.detail,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "request validation failed",
                    "detail": _safe_validation_errors(exc),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    app.include_router(health_router)
    app.include_router(inference_router)
    if mcp_app:
        app.mount("/mcp", mcp_app)
    return app


app = create_app()


def _safe_validation_errors(exc: RequestValidationError) -> list[dict]:
    errors = []
    for error in exc.errors():
        clean = dict(error)
        clean.pop("input", None)
        errors.append(clean)
    return errors
