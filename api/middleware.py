"""Custom middleware for request tracking and logging."""

from __future__ import annotations

import logging
import uuid
from time import perf_counter
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add a unique request ID to each request for tracing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add X-Request-ID header to request and response."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log request and response details for debugging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request details and timing."""
        start_time = perf_counter()
        request_id = getattr(request.state, "request_id", "unknown")

        # Log incoming request
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "client": request.client.host if request.client else None,
            },
        )

        # Process request
        try:
            response = await call_next(request)
            duration = perf_counter() - start_time

            # Log response
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

            return response
        except Exception as e:
            duration = perf_counter() - start_time
            logger.error(
                "Request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "url": str(request.url),
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise


class ContentTypeValidationMiddleware(BaseHTTPMiddleware):
    """Validate Content-Type and Accept headers for API endpoints.

    - Rejects POST/PUT requests to JSON endpoints without application/json Content-Type
    - Validates Accept header for SSE endpoints requires text/event-stream
    """

    # Paths that require JSON Content-Type for POST/PUT
    JSON_ENDPOINTS = {
        "/api/sessions/{session_id}",
        "/api/checkpoints/{checkpoint_id}/restore",
        "/api/sessions/{session_id}/fix-note",
        "/api/auth/keys",
    }

    # SSE endpoints that require text/event-stream Accept header
    SSE_ENDPOINTS = {
        "/api/sessions/{session_id}/stream",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate headers before processing the request."""
        path = request.url.path

        # Check JSON endpoints for POST/PUT methods
        if request.method in ("POST", "PUT"):
            # Match path patterns (handle path parameters)
            for endpoint in self.JSON_ENDPOINTS:
                if self._path_matches(path, endpoint):
                    content_type = request.headers.get("content-type", "")
                    if not content_type.startswith("application/json"):
                        from fastapi import HTTPException

                        logger.warning(
                            "Invalid Content-Type for JSON endpoint",
                            extra={
                                "path": path,
                                "method": request.method,
                                "content_type": content_type,
                            },
                        )
                        raise HTTPException(
                            status_code=415,
                            detail=f"Content-Type must be application/json for {request.method} {path}",
                        )
                    break

        # Check SSE endpoints for proper Accept header
        for endpoint in self.SSE_ENDPOINTS:
            if self._path_matches(path, endpoint):
                accept = request.headers.get("accept", "")
                # Accept header is optional for SSE, but warn if it's explicitly wrong
                if accept and "text/event-stream" not in accept and "*/*" not in accept:
                    logger.warning(
                        "SSE endpoint called without text/event-stream in Accept header",
                        extra={
                            "path": path,
                            "accept": accept,
                        },
                    )
                break

        return await call_next(request)

    def _path_matches(self, actual_path: str, pattern: str) -> bool:
        """Check if actual path matches a pattern with {parameters}."""
        # Simple pattern matching: split by / and compare segments
        actual_parts = actual_path.rstrip("/").split("/")
        pattern_parts = pattern.rstrip("/").split("/")

        if len(actual_parts) != len(pattern_parts):
            return False

        for actual, pattern_part in zip(actual_parts, pattern_parts):
            # Pattern segments in {} are wildcards
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                continue
            if actual != pattern_part:
                return False

        return True
