"""Simple in-memory query cache with TTL support."""

from __future__ import annotations

import threading
import time
from typing import Any


class QueryCache:
    """Thread-safe in-memory cache with time-based expiration.

    Simple caching utility for query results that don't change frequently.
    Uses a dictionary-based storage with per-entry TTL support.
    """

    def __init__(self) -> None:
        """Initialize the cache with storage and lock."""
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Retrieve a value from the cache if it exists and hasn't expired.

        Args:
            key: Cache key to look up

        Returns:
            Cached value if found and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            value, expiry = entry
            if time.time() > expiry:
                # Expired, remove from cache
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        """Store a value in the cache with a TTL.

        Args:
            key: Cache key to store under
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (default: 60)
        """
        expiry = time.time() + ttl_seconds
        with self._lock:
            self._cache[key] = (value, expiry)

    def invalidate(self, key: str, *, prefix: bool = False) -> int:
        """Remove cache entries by exact key or by key prefix.

        Args:
            key: Exact cache key to invalidate, or prefix when ``prefix=True``
            prefix: When True, remove all entries whose keys start with ``key``

        Returns:
            Number of entries removed
        """
        with self._lock:
            if not prefix:
                return 1 if self._cache.pop(key, None) is not None else 0

            keys_to_remove = [k for k in self._cache if k.startswith(key)]
            for k in keys_to_remove:
                del self._cache[k]
            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        now = time.time()
        with self._lock:
            expired_keys = [k for k, (_, expiry) in self._cache.items() if now > expiry]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def size(self) -> int:
        """Return the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)
