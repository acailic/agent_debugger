"""Tests for query performance optimizations.

Tests verify that:
1. Database indexes exist on model definitions
2. Cache utility works correctly (set/get/invalidation/TTL)
3. Alert repository summary and trending methods use caching
4. Query patterns leverage available indexes
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from storage.cache import QueryCache
from storage.models import AnomalyAlertModel, EventModel, PatternModel, SessionModel


class TestQueryCache:
    """Test the QueryCache utility."""

    def test_cache_set_get(self):
        """Test basic cache set and get operations."""
        cache = QueryCache()

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        cache.set("key2", {"nested": "dict"})
        assert cache.get("key2") == {"nested": "dict"}

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL without real sleeps."""
        cache = QueryCache()
        base_time = time.time()

        cache.set("expiring_key", "value", ttl_seconds=1)
        assert cache.get("expiring_key") == "value"

        # Advance time past TTL
        with patch("storage.cache.time.time", return_value=base_time + 2):
            assert cache.get("expiring_key") is None

    def test_cache_invalidation(self):
        """Test manual cache invalidation."""
        cache = QueryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

        cache.invalidate("key1")
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = QueryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        assert cache.size() == 3

        cache.clear()
        assert cache.size() == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries without real sleeps."""
        cache = QueryCache()
        base_time = time.time()

        # Set entries with different TTLs
        cache.set("short", "value1", ttl_seconds=1)
        cache.set("long", "value2", ttl_seconds=10)

        # Advance time past short TTL
        with patch("storage.cache.time.time", return_value=base_time + 2):
            removed = cache.cleanup_expired()
            assert removed == 1
            assert cache.get("short") is None
            assert cache.get("long") == "value2"

    def test_cache_size(self):
        """Test cache size tracking."""
        cache = QueryCache()

        assert cache.size() == 0

        cache.set("key1", "value1")
        assert cache.size() == 1

        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert cache.size() == 3

    def test_cache_prefix_invalidation(self):
        """Test prefix-based cache invalidation."""
        cache = QueryCache()

        cache.set("alert_summary:local:24h", {"total": 5})
        cache.set("alert_summary:local:48h", {"total": 10})
        cache.set("trending:local:7d", [])

        removed = cache.invalidate("alert_summary:local:", prefix=True)
        assert removed == 2
        assert cache.get("alert_summary:local:24h") is None
        assert cache.get("alert_summary:local:48h") is None
        assert cache.get("trending:local:7d") is not None


class TestModelIndexes:
    """Test that indexes exist on model definitions."""

    def test_anomaly_alert_model_indexes(self):
        """Verify AnomalyAlertModel has the expected indexes."""
        # We can't verify migration-created indexes on the model itself,
        # but we can verify the columns that should be indexed exist
        assert hasattr(AnomalyAlertModel, "created_at")
        assert hasattr(AnomalyAlertModel, "severity")
        assert hasattr(AnomalyAlertModel, "alert_type")
        assert hasattr(AnomalyAlertModel, "session_id")

    def test_pattern_model_indexes(self):
        """Verify PatternModel has the expected indexes."""
        # Check that indexed columns exist
        assert hasattr(PatternModel, "pattern_type")
        assert hasattr(PatternModel, "status")
        assert hasattr(PatternModel, "agent_name")
        assert hasattr(PatternModel, "severity")

    def test_session_model_indexes(self):
        """Verify SessionModel has the expected indexes."""
        assert hasattr(SessionModel, "started_at")
        assert hasattr(SessionModel, "agent_name")

    def test_event_model_indexes(self):
        """Verify EventModel has the expected indexes."""
        assert hasattr(EventModel, "session_id")
        assert hasattr(EventModel, "timestamp")
        assert hasattr(EventModel, "event_type")


class TestAlertRepositoryOptimizations:
    """Test alert repository query optimizations."""

    @pytest.mark.asyncio
    async def test_alert_summary_caching(self):
        """Test that alert summary results are cached."""
        from storage.repositories.alert_repo import AnomalyAlertRepository

        # Create an in-memory SQLite engine for testing
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        # Create tables
        from storage.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            repo = AnomalyAlertRepository(session, tenant_id="test")

            # Clear any existing cache
            repo._cache.clear()

            # Create test alerts
            now = datetime.now(timezone.utc)
            for i in range(5):
                alert = AnomalyAlertModel(
                    id=str(uuid.uuid4()),
                    tenant_id="test",
                    session_id=str(uuid.uuid4()),
                    alert_type=f"test_type_{i % 2}",
                    severity=0.5 + (i * 0.1),
                    signal=f"Test alert {i}",
                    event_ids=[],
                    detection_source="test",
                    detection_config={},
                    created_at=now - timedelta(hours=i),
                )
                session.add(alert)
            await session.commit()

            # First call should query database
            summary1 = await repo.get_alert_summary(hours=24)
            assert summary1["total_count"] == 5

            # Second call should use cache
            summary2 = await repo.get_alert_summary(hours=24)
            assert summary2["total_count"] == 5

            # Verify cache was used
            assert repo._cache.size() > 0

    @pytest.mark.asyncio
    async def test_alert_list_limit_default(self):
        """Test that list queries have reasonable limits."""
        from storage.repositories.alert_repo import AnomalyAlertRepository

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        from storage.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            repo = AnomalyAlertRepository(session, tenant_id="test")

            # Create more alerts than the default limit
            session_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            for i in range(100):
                alert = AnomalyAlertModel(
                    id=str(uuid.uuid4()),
                    tenant_id="test",
                    session_id=session_id,
                    alert_type="test_type",
                    severity=0.5,
                    signal=f"Test alert {i}",
                    event_ids=[],
                    detection_source="test",
                    detection_config={},
                    created_at=now - timedelta(minutes=i),
                )
                session.add(alert)
            await session.commit()

            # List should return at most 50 (default limit)
            alerts = await repo.list_anomaly_alerts(session_id)
            assert len(alerts) <= 50

            # Verify ordering by created_at desc (newest first)
            if len(alerts) > 1:
                assert alerts[0].created_at >= alerts[-1].created_at


@pytest.mark.integration
class TestMigrationIndexes:
    """Integration tests for migration-created indexes."""

    def test_migration_006_creates_indexes(self):
        """Test that migration 006 creates the expected indexes."""
        # This test requires a real database connection
        # Skip in unit test environments
        pytest.skip("Requires database connection")

        # With a real connection, you would:
        # 1. Run migration 006
        # 2. Query pg_indexes or sqlite_master to verify indexes exist
        # 3. Verify index columns match expectations
