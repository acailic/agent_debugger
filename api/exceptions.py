"""Application exception hierarchy for structured error handling."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class AppError(HTTPException):
    """Base exception for application errors.

    Extends HTTPException so FastAPI handles it natively and existing
    tests that catch HTTPException continue to work.
    """

    def __init__(self, detail: str, *, status_code: int = 500, error: str = "internal_error") -> None:
        self.error = error
        super().__init__(status_code=status_code, detail=detail)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to a dictionary for JSON responses."""
        return {
            "detail": self.detail,
            "error": self.error,
        }


class NotFoundError(AppError):
    """Resource not found error (404)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=404, error="not_found")


class ValidationError(AppError):
    """Request validation error (422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=422, error="validation_error")


class ConflictError(AppError):
    """Resource conflict error (409)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=409, error="conflict")


class RateLimitError(AppError):
    """Rate limit exceeded error (429)."""

    def __init__(self, detail: str, retry_after: int | None = None) -> None:
        super().__init__(detail, status_code=429, error="rate_limit_exceeded")
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to a dictionary for JSON responses."""
        d = super().to_dict()
        if self.retry_after is not None:
            d["retry_after"] = self.retry_after
        return d
