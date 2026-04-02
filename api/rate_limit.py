"""Rate limiting middleware for API endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


@dataclass
class RateLimitStats:
    """Track rate limit statistics for a client."""

    count: int = 0
    reset_time: float = field(default_factory=lambda: time.time() + 60)

    def is_expired(self) -> bool:
        """Check if the rate limit window has expired."""
        return time.time() >= self.reset_time

    def increment(self) -> int:
        """Increment counter and return new count."""
        self.count += 1
        return self.count

    def reset(self, window_seconds: int) -> None:
        """Reset counter and set new expiration."""
        self.count = 1
        self.reset_time = time.time() + window_seconds


class InMemoryRateLimiter:
    """In-memory rate limiter using sliding window.

    This is a simple implementation suitable for single-instance deployments.
    For multi-instance deployments, use Redis or another distributed cache.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        """Initialize the rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute per client
            requests_per_hour: Maximum requests per hour per client
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._minute_limits: dict[str, RateLimitStats] = defaultdict(
            lambda: RateLimitStats(reset_time=time.time() + 60)
        )
        self._hour_limits: dict[str, RateLimitStats] = defaultdict(
            lambda: RateLimitStats(reset_time=time.time() + 3600)
        )
        self._lock = asyncio.Lock()

    async def check_rate_limit(
        self, client_id: str
    ) -> tuple[bool, dict[str, int | str]]:
        """Check if a client has exceeded rate limits.

        Args:
            client_id: Unique identifier for the client (e.g., IP address or API key)

        Returns:
            Tuple of (allowed, info_dict) where info_dict contains:
                - remaining: Remaining requests in current window
                - reset: Unix timestamp when window resets
                - limit: Request limit for current window
        """
        async with self._lock:
            # Check minute limit
            minute_stats = self._minute_limits[client_id]
            if minute_stats.is_expired():
                minute_stats.reset(60)
            elif minute_stats.count >= self.requests_per_minute:
                return False, {
                    "remaining": 0,
                    "reset": int(minute_stats.reset_time),
                    "limit": self.requests_per_minute,
                }

            # Check hour limit
            hour_stats = self._hour_limits[client_id]
            if hour_stats.is_expired():
                hour_stats.reset(3600)
            elif hour_stats.count >= self.requests_per_hour:
                return False, {
                    "remaining": 0,
                    "reset": int(hour_stats.reset_time),
                    "limit": self.requests_per_hour,
                }

            # Increment both counters
            minute_stats.increment()
            hour_stats.increment()

            # Return info based on which limit is more restrictive
            remaining = min(
                self.requests_per_minute - minute_stats.count,
                self.requests_per_hour - hour_stats.count,
            )

            return True, {
                "remaining": remaining,
                "reset": int(minute_stats.reset_time),
                "limit": self.requests_per_minute,
            }

    async def cleanup_expired(self) -> None:
        """Remove expired entries to prevent memory leaks."""
        async with self._lock:
            self._minute_limits = {
                k: v for k, v in self._minute_limits.items() if not v.is_expired()
            }
            self._hour_limits = {
                k: v for k, v in self._hour_limits.items() if not v.is_expired()
            }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to API requests."""

    # Paths that bypass rate limiting
    EXEMPT_PATHS = {
        "/health",
        "/ready",
        "/live",
        "/ui",
        "/docs",
        "/openapi.json",
    }

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        """Initialize the rate limiting middleware.

        Args:
            app: ASGI application
            requests_per_minute: Maximum requests per minute per client
            requests_per_hour: Maximum requests per hour per client
        """
        super().__init__(app)
        self.rate_limiter = InMemoryRateLimiter(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limits before processing request."""
        # Skip rate limiting for exempt paths
        if any(request.url.path.startswith(path) for path in self.EXEMPT_PATHS):
            return await call_next(request)

        # Get client identifier
        client_id = self._get_client_id(request)

        # Check rate limits
        allowed, info = await self.rate_limiter.check_rate_limit(client_id)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset"]),
                    "Retry-After": str(info["reset"] - int(time.time())),
                },
            )

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get a unique identifier for the client.

        Uses API key if available, otherwise falls back to client IP.

        Args:
            request: The incoming request

        Returns:
            A string identifier for the client
        """
        # Try to get API key from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Use first 12 characters of the API key as identifier
            api_key = auth_header[7:].strip()
            if len(api_key) > 12:
                return api_key[:12]

        # Fall back to client IP
        return request.client.host if request.client else "unknown"
