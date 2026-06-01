import time
from collections import defaultdict, deque
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
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": {"code": "authentication_failed", "message": "valid API key required"}},
                )
        return await call_next(request)

    def _requires_auth(self, path: str) -> bool:
        return bool(self._api_keys) and any(path.startswith(prefix) for prefix in self._protected_prefixes)


class OriginValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, allowed_origins: list[str], protected_prefixes: tuple[str, ...]) -> None:
        super().__init__(app)
        self._allowed_origins = set(allowed_origins)
        self._protected_prefixes = protected_prefixes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")
        if origin and self._requires_origin_check(request.url.path) and origin not in self._allowed_origins:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": {"code": "origin_not_allowed", "message": "origin not allowed"}},
            )
        return await call_next(request)

    def _requires_origin_check(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self._protected_prefixes)


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        audit_logger.info(
            "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            getattr(request.state, "request_id", None),
        )
        return response


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, requests_per_minute: int) -> None:
        super().__init__(app)
        self._requests_per_minute = requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._requests_per_minute <= 0 or request.url.path in {"/health", "/version"}:
            return await call_next(request)

        now = time.monotonic()
        key = self._client_key(request)
        window = self._hits[key]
        while window and now - window[0] >= 60:
            window.popleft()

        if len(window) >= self._requests_per_minute:
            return Response(
                content='{"error":{"code":"rate_limit_exceeded","message":"rate limit exceeded"}}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

        window.append(now)
        return await call_next(request)

    def _client_key(self, request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"api-key:{api_key}"
        if request.client:
            return f"ip:{request.client.host}"
        return "unknown"
