"""API validation tests for schemas, exceptions, and redaction patterns.

Tests cover:
1. SessionUpdateRequest validators (ended_at >= started_at)
2. SECRET_PATTERNS matching real tokens (AWS keys, GitHub tokens, JWT, bearer tokens, private keys, generic API keys)
3. Error hierarchy and status codes (AppError, NotFoundError, ValidationError, ConflictError, RateLimitError)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events import SessionStatus
from api.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from api.schemas import SessionUpdateRequest
from redaction.patterns import (
    SECRET_PATTERNS,
    SECRET_REPLACEMENT_MAP,
)

# =============================================================================
# SessionUpdateRequest Validator Tests
# =============================================================================


class TestSessionUpdateRequestValidation:
    """Tests for SessionUpdateRequest cross-field validators."""

    def test_ended_at_after_started_at_passes(self):
        """Test validation passes when ended_at > started_at."""
        started = datetime.now(timezone.utc)
        ended = started + timedelta(hours=1)

        request = SessionUpdateRequest(
            started_at=started,
            ended_at=ended,
        )

        assert request.started_at == started
        assert request.ended_at == ended

    def test_ended_at_equal_to_started_at_passes(self):
        """Test validation passes when ended_at == started_at."""
        now = datetime.now(timezone.utc)

        request = SessionUpdateRequest(
            started_at=now,
            ended_at=now,
        )

        assert request.started_at == now
        assert request.ended_at == now

    def test_ended_at_before_started_at_raises_error(self):
        """Test validation raises ValueError when ended_at < started_at."""
        started = datetime.now(timezone.utc)
        ended = started - timedelta(hours=1)

        with pytest.raises(ValueError, match="ended_at must be greater than or equal to started_at"):
            SessionUpdateRequest(
                started_at=started,
                ended_at=ended,
            )

    def test_only_started_at_provided_passes(self):
        """Test validation passes when only started_at is provided."""
        started = datetime.now(timezone.utc)

        request = SessionUpdateRequest(started_at=started)

        assert request.started_at == started
        assert request.ended_at is None

    def test_only_ended_at_provided_passes(self):
        """Test validation passes when only ended_at is provided."""
        ended = datetime.now(timezone.utc)

        request = SessionUpdateRequest(ended_at=ended)

        assert request.started_at is None
        assert request.ended_at == ended

    def test_neither_datetime_provided_passes(self):
        """Test validation passes when neither started_at nor ended_at is provided."""
        request = SessionUpdateRequest()

        assert request.started_at is None
        assert request.ended_at is None

    def test_all_fields_valid(self):
        """Test a valid request with all fields."""
        started = datetime.now(timezone.utc)
        ended = started + timedelta(hours=1)

        request = SessionUpdateRequest(
            agent_name="test-agent",
            framework="test-framework",
            started_at=started,
            ended_at=ended,
            status=SessionStatus.COMPLETED,
            total_tokens=1000,
            total_cost_usd=0.05,
            tool_calls=10,
            llm_calls=5,
            errors=0,
            replay_value=0.8,
            config={"model": "gpt-4"},
            tags=["test", "validation"],
            fix_note="Test fix note",
        )

        assert request.agent_name == "test-agent"
        assert request.framework == "test-framework"
        assert request.status == SessionStatus.COMPLETED


# =============================================================================
# SECRET_PATTERNS Tests
# =============================================================================


class TestSecretPatterns:
    """Tests for SECRET_PATTERNS matching real token formats."""

    def test_aws_access_key_pattern_matches_valid_key(self):
        """Test AWS Access Key ID pattern matches valid keys."""
        pattern = SECRET_PATTERNS["aws_access_key"]
        valid_key = "AKIAIOSFODNN7EXAMPLE"

        match = pattern.search(valid_key)
        assert match is not None
        assert match.group() == "AKIAIOSFODNN7EXAMPLE"

    def test_aws_access_key_pattern_rejects_invalid_key(self):
        """Test AWS Access Key ID pattern rejects invalid keys."""
        pattern = SECRET_PATTERNS["aws_access_key"]
        invalid_keys = [
            "AKIAIOSFODNN7EXAMPL",  # Too short (15 chars)
            "AKIAIOSFODNN7EXAMPLEE",  # Too long (18 chars)
            "BKIAIOSFODNN7EXAMPLE",  # Wrong prefix
            "AKIAIOSFODNN7EXAM BLE",  # Contains space
            "akiaiosfodnn7example",  # Lowercase
        ]

        for invalid_key in invalid_keys:
            match = pattern.search(invalid_key)
            assert match is None, f"Should not match invalid key: {invalid_key}"

    def test_aws_secret_key_pattern_matches_valid_key(self):
        """Test AWS Secret Access Key pattern matches valid keys."""
        pattern = SECRET_PATTERNS["aws_secret_key"]
        valid_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        match = pattern.search(valid_key)
        assert match is not None

    def test_github_token_pattern_matches_classic_tokens(self):
        """Test GitHub token pattern matches classic PAT formats."""
        pattern = SECRET_PATTERNS["github_token"]

        # Test all classic token prefixes (exactly 36 chars after prefix: [A-Za-z0-9_]{36})
        # Use repeated chars to ensure exact length
        valid_tokens = [
            "ghp_" + "a" * 36,  # ghp_ prefix + 36 chars
            "gho_" + "b" * 36,  # gho_ prefix + 36 chars
            "ghu_" + "c" * 36,  # ghu_ prefix + 36 chars
            "ghs_" + "d" * 36,  # ghs_ prefix + 36 chars
            "ghr_" + "e" * 36,  # ghr_ prefix + 36 chars
        ]

        for token in valid_tokens:
            match = pattern.search(token)
            assert match is not None, f"Should match token: {token}"

    def test_github_pat_pattern_matches_fine_grained_tokens(self):
        """Test GitHub PAT pattern matches fine-grained tokens."""
        pattern = SECRET_PATTERNS["github_pat"]
        # github_pat_ prefix + exactly 82 chars ([0-9a-zA-Z_]{82})
        valid_pat = "github_pat_" + "a" * 82

        match = pattern.search(valid_pat)
        assert match is not None

    def test_bearer_token_pattern_matches_valid_tokens(self):
        """Test bearer token pattern matches Authorization header values."""
        pattern = SECRET_PATTERNS["bearer_token"]

        # Test various bearer token formats
        valid_tokens = [
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "Bearer my-token-12345",
            "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Case insensitive
            "BEARER TOKEN12345678901234567890",
        ]

        for token in valid_tokens:
            match = pattern.search(token)
            assert match is not None, f"Should match bearer token: {token}"

    def test_jwt_pattern_matches_valid_jwt(self):
        """Test JWT pattern matches valid JWT tokens."""
        pattern = SECRET_PATTERNS["jwt"]

        # Valid JWT format (header.payload.signature)
        valid_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

        match = pattern.search(valid_jwt)
        assert match is not None
        assert match.group() == valid_jwt

    def test_private_key_pattern_matches_rsa_keys(self):
        """Test private key pattern matches RSA private key headers."""
        pattern = SECRET_PATTERNS["private_key"]

        # The pattern matches "-----BEGIN [A-Z]+ PRIVATE KEY-----"
        # It requires uppercase letters between BEGIN and PRIVATE KEY
        # Test formats that match the actual pattern
        valid_headers = [
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN DSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
        ]

        for header in valid_headers:
            match = pattern.search(header)
            assert match is not None, f"Should match private key header: {header}"

        # Test that generic "PRIVATE KEY" doesn't match (needs key type)
        generic_header = "-----BEGIN PRIVATE KEY-----"
        match = pattern.search(generic_header)
        assert match is None, f"Should not match generic header without key type: {generic_header}"

    def test_generic_api_key_pattern_matches_various_formats(self):
        """Test generic API key pattern matches various common formats."""
        pattern = SECRET_PATTERNS["generic_api_key"]

        # Test various API key formats
        # Pattern: (?:api[_-]?key|apikey|key|token|secret)[=:\s]+['\"]?[A-Za-z0-9_\-]{20,}['\"]?
        valid_keys = [
            "api_key=sk-1234567890abcdefghijklmnopqrst",
            "apikey=sk-1234567890abcdefghijklmnopqrst",
            "key=sk-1234567890abcdefghijklmnopqrst",
            "token=sk-1234567890abcdefghijklmnopqrst",
            "secret=sk-1234567890abcdefghijklmnopqrst",
            "api-key: sk-1234567890abcdefghijklmnopqrst",
            "Authorization: Key ABCDEF1234567890abcdefghijklmnopqrst",
        ]

        for key in valid_keys:
            match = pattern.search(key)
            assert match is not None, f"Should match API key format: {key}"

        # Test that quoted strings with only 19 chars don't match (pattern requires 20+)
        short_key = "'sk-1234567890abcde'"  # Only 19 chars
        match = pattern.search(short_key)
        assert match is None, f"Should not match short key: {short_key}"

    def test_secret_replacement_map_has_all_patterns(self):
        """Test SECRET_REPLACEMENT_MAP has entries for all SECRET_PATTERNS."""
        for pattern_name in SECRET_PATTERNS:
            assert pattern_name in SECRET_REPLACEMENT_MAP, f"Missing replacement for {pattern_name}"


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestExceptionHierarchy:
    """Tests for exception hierarchy and status codes."""

    def test_app_error_base_exception(self):
        """Test AppError base exception properties."""
        error = AppError("Something went wrong")

        assert error.detail == "Something went wrong"
        assert error.status_code == 500
        assert error.error == "internal_error"
        assert str(error) == "Something went wrong"

    def test_app_error_custom_status_code(self):
        """Test AppError with custom status code."""
        error = AppError("Custom error", status_code=418, error="custom_error")

        assert error.detail == "Custom error"
        assert error.status_code == 418
        assert error.error == "custom_error"

    def test_app_error_to_dict(self):
        """Test AppError.to_dict() returns correct structure."""
        error = AppError("Test error", status_code=400, error="bad_request")

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Test error",
            "error": "bad_request",
        }

    def test_not_found_error_inheritance(self):
        """Test NotFoundError inherits from AppError."""
        error = NotFoundError("Resource not found")

        assert isinstance(error, AppError)
        assert error.status_code == 404
        assert error.error == "not_found"
        assert error.detail == "Resource not found"

    def test_not_found_error_to_dict(self):
        """Test NotFoundError.to_dict() returns correct structure."""
        error = NotFoundError("Session not found")

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Session not found",
            "error": "not_found",
        }

    def test_validation_error_inheritance(self):
        """Test ValidationError inherits from AppError."""
        error = ValidationError("Invalid input")

        assert isinstance(error, AppError)
        assert error.status_code == 422
        assert error.error == "validation_error"
        assert error.detail == "Invalid input"

    def test_validation_error_to_dict(self):
        """Test ValidationError.to_dict() returns correct structure."""
        error = ValidationError("Field 'email' is required")

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Field 'email' is required",
            "error": "validation_error",
        }

    def test_conflict_error_inheritance(self):
        """Test ConflictError inherits from AppError."""
        error = ConflictError("Resource already exists")

        assert isinstance(error, AppError)
        assert error.status_code == 409
        assert error.error == "conflict"
        assert error.detail == "Resource already exists"

    def test_conflict_error_to_dict(self):
        """Test ConflictError.to_dict() returns correct structure."""
        error = ConflictError("Session ID conflict")

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Session ID conflict",
            "error": "conflict",
        }

    def test_rate_limit_error_inheritance(self):
        """Test RateLimitError inherits from AppError."""
        error = RateLimitError("Too many requests")

        assert isinstance(error, AppError)
        assert error.status_code == 429
        assert error.error == "rate_limit_exceeded"
        assert error.detail == "Too many requests"

    def test_rate_limit_error_with_retry_after(self):
        """Test RateLimitError with retry_after parameter."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)

        assert error.retry_after == 60

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Rate limit exceeded",
            "error": "rate_limit_exceeded",
            "retry_after": 60,
        }

    def test_rate_limit_error_without_retry_after(self):
        """Test RateLimitError without retry_after parameter."""
        error = RateLimitError("Rate limit exceeded")

        assert error.retry_after is None

        error_dict = error.to_dict()

        assert error_dict == {
            "detail": "Rate limit exceeded",
            "error": "rate_limit_exceeded",
        }

    def test_all_exceptions_have_correct_status_codes(self):
        """Test all exception types have their documented status codes."""
        not_found = NotFoundError("test")
        validation = ValidationError("test")
        conflict = ConflictError("test")
        rate_limit = RateLimitError("test")

        assert not_found.status_code == 404
        assert validation.status_code == 422
        assert conflict.status_code == 409
        assert rate_limit.status_code == 429

    def test_all_exceptions_convert_to_dict(self):
        """Test all exception types have working to_dict() methods."""
        exceptions = [
            AppError("test", status_code=500, error="internal_error"),
            NotFoundError("test"),
            ValidationError("test"),
            ConflictError("test"),
            RateLimitError("test"),
            RateLimitError("test", retry_after=30),
        ]

        for exc in exceptions:
            error_dict = exc.to_dict()
            assert "detail" in error_dict
            assert "error" in error_dict
            assert error_dict["detail"] == "test"
