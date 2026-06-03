from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_competition import router as competition_router
from app.core.audit import configure_logging
from app.core.errors import AppError
from app.core.settings import get_settings
from app.middleware import (
    AuditLogMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="LLM Inference Gateway", version=settings.api_version)
    # add_middleware prepends; last added runs outermost (first inbound).
    # Order: RequestId (outermost) -> AuditLog -> SecurityHeaders (innermost).
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type", "x-request-id"],
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
    app.include_router(competition_router)
    return app


app = create_app()


def _safe_validation_errors(exc: RequestValidationError) -> list[dict]:
    errors = []
    for error in exc.errors():
        clean = dict(error)
        clean.pop("input", None)
        errors.append(clean)
    return errors
