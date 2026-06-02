import json
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.audit import audit_logger
from app.core.security import verify_api_key


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self._max_bytes:
            audit_logger.warning(json.dumps({
                "event": "request_too_large",
                "path": request.url.path,
                "content_length": int(content_length),
                "client_ip": request.client.host if request.client else None,
                "request_id": getattr(request.state, "request_id", None),
            }))
            return Response(
                content='{"error":{"code":"request_body_too_large","message":"request body too large"}}',
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                media_type="application/json",
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "no-referrer")
        response.headers.setdefault("cache-control", "no-store")
        return response


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, api_keys: list[str], protected_prefixes: tuple[str, ...]) -> None:
        super().__init__(app)
        self._api_keys = api_keys
        self._protected_prefixes = protected_prefixes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._requires_auth(request.url.path):
            try:
                verify_api_key(request, self._api_keys)
            except Exception:
                audit_logger.warning(json.dumps({
                    "event": "auth_failed",
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else None,
                    "request_id": getattr(request.state, "request_id", None),
                }))
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": {"code": "authentication_failed", "message": "valid API key required"}},
                )
        return await call_next(request)

    def _requires_auth(self, path: str) -> bool:
        return bool(self._api_keys) and any(path.startswith(prefix) for prefix in self._protected_prefixes)


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        audit_logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "request_id": getattr(request.state, "request_id", None),
            "client_ip": request.client.host if request.client else None,
            "key_prefix": _key_prefix(request),
        }))
        return response


def _key_prefix(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:]
    if key:
        return key[:8] + "..."
    return None
