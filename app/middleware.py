import json
import re
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.audit import audit_logger

_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw = request.headers.get("x-request-id", "")
        request_id = raw if _REQUEST_ID_RE.match(raw) else str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "no-referrer")
        response.headers.setdefault("cache-control", "no-store")
        return response



class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            audit_logger.info(json.dumps({
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": duration_ms,
                "request_id": getattr(request.state, "request_id", None),
                "client_ip": request.client.host if request.client else None,
                "key_prefix": _key_prefix(request),
            }))


def _key_prefix(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:]
    if key:
        return key[:8] + "..."
    return None
