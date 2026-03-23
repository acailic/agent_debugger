"""Tests for API key authentication."""

from auth.api_keys import generate_api_key, hash_key, verify_key


def test_generate_api_key_format():
    """API keys should have ad_live_ or ad_test_ prefix."""
    key = generate_api_key(environment="live")
    assert key.startswith("ad_live_")
    assert len(key) > 20


def test_generate_test_key():
    key = generate_api_key(environment="test")
    assert key.startswith("ad_test_")


def test_hash_and_verify():
    key = generate_api_key(environment="live")
    hashed = hash_key(key)
    assert hashed != key
    assert verify_key(key, hashed) is True
    assert verify_key("wrong_key", hashed) is False
