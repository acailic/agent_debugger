"""API key generation, hashing, and verification."""

from __future__ import annotations

import secrets

import bcrypt


def generate_api_key(environment: str = "live") -> str:
    """Generate a new API key with the specified environment prefix.

    Args:
        environment: Either "live" or "test"

    Returns:
        A new API key string with format ad_{environment}_{random}
    """
    prefix = f"ad_{environment}_"
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}{random_part}"


def hash_key(raw_key: str) -> str:
    """Hash an API key using bcrypt.

    Args:
        raw_key: The raw API key to hash

    Returns:
        A bcrypt hash of the key
    """
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()


def verify_key(raw_key: str, hashed: str) -> bool:
    """Verify a raw API key against its hash.

    Args:
        raw_key: The raw API key to verify
        hashed: The stored hash to compare against

    Returns:
        True if the key matches the hash, False otherwise
    """
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())
