"""FastAPI middleware for production hardening."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


_REQUEST_ID_HEADER = "x-request-id"
_SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}
_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB — protects against huge payloads

# Conservative control-character stripper, used as a defensive sanitiser for
# free-form text fields. Allow normal printable unicode + common whitespace.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
logger = logging.getLogger("salesforce_ai_engineer.access")


def sanitize_text(value: str, *, max_len: int = 10_000) -> str:
    """Strip control chars and truncate. Use for untrusted free-form strings."""

    if not isinstance(value, str):
        return value  # type: ignore[return-value]
    cleaned = _CONTROL_CHARS.sub("", value)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned.strip()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and emit structured access logs."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        # Stash on request.state for downstream handlers / routes
        request.state.request_id = request_id

        start = time.perf_counter()
        # FIX: use None sentinel so the logged status accurately reflects
        # whether a response was actually produced or the handler raised.
        status_code: int | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        except Exception:  # noqa: BLE001 — re-raised after logging
            logger.exception(
                "request_failed",
                extra={"request_id": request_id},
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self._log_access(request, status_code, duration_ms, request_id)

    @staticmethod
    def _log_access(
        request: Request,
        status_code: int | None,
        duration_ms: float,
        request_id: str,
    ) -> None:
        # Only log the path, not the full query string (may carry secrets).
        # FIX: redact sensitive headers using _SENSITIVE_HEADERS.
        try:
            logged_headers = {
                k: ("***" if k.lower() in _SENSITIVE_HEADERS else v)
                for k, v in request.headers.items()
            }
            log_obj = {
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": status_code,  # None means the handler raised
                "duration_ms": round(duration_ms, 2),
                "request_id": request_id,
                "client": request.client.host if request.client else None,
                "headers": logged_headers,
            }
            logger.info(json.dumps(log_obj, separators=(",", ":")))
        except Exception:  # noqa: BLE001 — never let logging break a request
            logger.warning("access_log_failed", exc_info=True)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies early."""

    def __init__(self, app, max_bytes: int = _MAX_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # FIX: check Content-Length header first (fast path) ...
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    return JSONResponse(
                        {"detail": "Request body too large"},
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length"},
                    status_code=400,
                )

        # FIX: ... then also stream-read the body to catch clients that omit
        # Content-Length entirely (chunked transfer, raw streams, etc.).
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > self.max_bytes:
                return JSONResponse(
                    {"detail": "Request body too large"},
                    status_code=413,
                )

        # Re-inject the body so downstream handlers can still read it.
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a small set of defensive response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response