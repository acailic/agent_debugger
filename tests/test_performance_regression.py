"""Performance regression benchmarks for the test suite.

These tests measure wall-clock time for critical operations and fail
if they exceed configured thresholds. They run in CI as a smoke test
for performance regressions.

Run standalone: pytest tests/test_performance_regression.py -v --timeout=60
"""

from __future__ import annotations

import time

import pytest

from api.main import create_app


class TestAppStartupPerformance:
    """Ensure app creation doesn't slow down."""

    MAX_APP_CREATE_MS = 500  # App factory should be sub-500ms

    def test_create_app_latency(self) -> None:
        # The factory's real cost is its config work (middleware, ~20 routers,
        # exception handlers) — not the one-time module import, which depends on
        # the environment and dwarfs the factory logic on a cold call. Warm up so
        # import cost is excluded, then take the min of several runs: the floor is
        # the stable regression signal and is immune to the CPU-scheduling jitter
        # that makes a single wall-clock sample flaky under parallel suite load.
        create_app()  # warm up: force lazy imports so they are not measured

        samples_ms: list[float] = []
        for _ in range(5):
            start = time.perf_counter()
            app = create_app()
            samples_ms.append((time.perf_counter() - start) * 1000)

        elapsed_ms = min(samples_ms)
        assert app is not None
        assert elapsed_ms < self.MAX_APP_CREATE_MS, (
            f"create_app() took {elapsed_ms:.1f}ms (min of {len(samples_ms)} runs; "
            f"threshold: {self.MAX_APP_CREATE_MS}ms)"
        )


class TestSchemaSerializationPerformance:
    """Ensure schema serialization doesn't regress."""

    MAX_SESSION_SERIALIZATION_MS = 50  # 50 sessions in <50ms

    def test_session_schema_batch_serialization(self) -> None:
        from datetime import datetime, timezone

        from api.schemas_core import SessionSchema

        sessions = [
            SessionSchema(
                id=f"sess-{i}",
                agent_name="test-agent",
                framework="langchain",
                started_at=datetime.now(timezone.utc),
                ended_at=None,
                status="running",
                total_tokens=100,
                total_cost_usd=0.01,
                tool_calls=5,
                llm_calls=10,
                errors=0,
                replay_value=0.5,
                config={},
                tags=[],
            )
            for i in range(50)
        ]

        start = time.perf_counter()
        for s in sessions:
            s.model_dump_json()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < self.MAX_SESSION_SERIALIZATION_MS, (
            f"Serializing 50 sessions took {elapsed_ms:.1f}ms (threshold: {self.MAX_SESSION_SERIALIZATION_MS}ms)"
        )


class TestEventIndexingPerformance:
    """Ensure database queries benefit from indexes."""

    MAX_LIST_SESSIONS_MS = 200

    @pytest.mark.asyncio
    async def test_list_sessions_with_index(self, shared_app, db_session) -> None:
        """Listing sessions should be fast with the composite index."""
        from storage.repositories.session_repo import SessionRepository

        repo = SessionRepository(db_session)

        start = time.perf_counter()
        await repo.list_sessions(limit=10)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Even with 0 sessions, the query should be fast
        assert elapsed_ms < self.MAX_LIST_SESSIONS_MS, (
            f"list_sessions() took {elapsed_ms:.1f}ms (threshold: {self.MAX_LIST_SESSIONS_MS}ms)"
        )
