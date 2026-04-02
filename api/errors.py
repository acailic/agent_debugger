"""Centralized error handling and HTTP exception helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class APIError(HTTPException):
    """Base exception for API errors with consistent structure."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str | None = None,
        **extra_data: Any,
    ) -> None:
        """Initialize an API error with consistent structure.

        Args:
            status_code: HTTP status code
            detail: Human-readable error message
            error_code: Machine-readable error code for client handling
            **extra_data: Additional fields to include in error response
        """
        self.error_code = error_code
        self.extra_data = extra_data
        super().__init__(status_code=status_code, detail=detail)


def not_found(resource: str, identifier: str) -> APIError:
    """Create a 404 not found error.

    Args:
        resource: Type of resource (e.g., "Session", "API key")
        identifier: ID or identifier of the resource

    Returns:
        APIError with 404 status
    """
    return APIError(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} {identifier!r} not found",
        error_code="NOT_FOUND",
        resource=resource,
        identifier=identifier,
    )


def unauthorized(detail: str = "Invalid credentials") -> APIError:
    """Create a 401 unauthorized error.

    Args:
        detail: Human-readable error message

    Returns:
        APIError with 401 status
    """
    return APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        error_code="UNAUTHORIZED",
    )


def forbidden(detail: str = "Access denied") -> APIError:
    """Create a 403 forbidden error.

    Args:
        detail: Human-readable error message

    Returns:
        APIError with 403 status
    """
    return APIError(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
        error_code="FORBIDDEN",
    )


def bad_request(detail: str, error_code: str = "BAD_REQUEST", **extra: Any) -> APIError:
    """Create a 400 bad request error.

    Args:
        detail: Human-readable error message
        error_code: Machine-readable error code
        **extra: Additional fields to include in error response

    Returns:
        APIError with 400 status
    """
    return APIError(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
        error_code=error_code,
        **extra,
    )


def internal_error(detail: str = "An internal error occurred") -> APIError:
    """Create a 500 internal server error.

    Args:
        detail: Human-readable error message

    Returns:
        APIError with 500 status
    """
    return APIError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
        error_code="INTERNAL_ERROR",
    )


def conflict(resource: str, identifier: str, reason: str = "Already exists") -> APIError:
    """Create a 409 conflict error.

    Args:
        resource: Type of resource (e.g., "Session", "API key")
        identifier: ID or identifier of the resource
        reason: Reason for the conflict

    Returns:
        APIError with 409 status
    """
    return APIError(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"{resource} {identifier!r}: {reason}",
        error_code="CONFLICT",
        resource=resource,
        identifier=identifier,
    )
