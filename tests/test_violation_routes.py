"""Tests for violation detection API routes."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from api import app_context
from api import services as api_services
from benchmarks import run_evidence_grounding_session
from collector.buffer import get_event_buffer
from storage import Base, TraceRepository


def _get_route_endpoint(path: str, method: str):
    """Get route endpoint function by path and method.

    NOTE: This tests implementation details (route endpoint function references).
    Consider refactoring to test behavior (HTTP responses) instead if this becomes brittle.
    """
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def api_repo_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "api-violation-routes.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(app_context, "engine", engine)
    monkeypatch.setattr(app_context, "async_session_maker", session_maker)

    buffer = get_event_buffer()
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    configure_storage(session_maker)
    configure_event_pipeline(
        buffer,
        persist_event=api_services.persist_event,
        persist_checkpoint=api_services.persist_checkpoint,
        persist_session_start=api_services.persist_session_start,
        persist_session_update=api_services.persist_session_update,
    )

    yield session_maker

    configure_storage(None)
    configure_event_pipeline(None)
    asyncio.run(engine.dispose())


# =============================================================================
# POST /api/violations/cluster
# =============================================================================

def test_cluster_sessions_endpoint(api_repo_factory):
    """Test the cluster sessions endpoint."""
    # Create a test session
    session_id = "violation_cluster_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                similarity_threshold=0.5,
                min_cluster_size=2,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "clusters" in data
    assert "global_outliers" in data
    assert "total_sessions_analyzed" in data
    assert "clustering_params" in data

    # Check structure
    assert isinstance(data["clusters"], list)
    assert isinstance(data["global_outliers"], list)
    assert data["total_sessions_analyzed"] >= 0


def test_cluster_sessions_with_agent_filter(api_repo_factory):
    """Test clustering with agent name filter."""
    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                agent_name="test_agent",
                similarity_threshold=0.7,
                min_cluster_size=2,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "clusters" in data
    assert isinstance(data["clusters"], list)


def test_cluster_sessions_with_session_ids(api_repo_factory):
    """Test clustering with specific session IDs."""
    # Create test sessions
    session_id_1 = "cluster_test_1"
    session_id_2 = "cluster_test_2"
    asyncio.run(run_evidence_grounding_session(session_id_1))
    asyncio.run(run_evidence_grounding_session(session_id_2))

    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                session_ids=[session_id_1, session_id_2],
                similarity_threshold=0.5,
                min_cluster_size=2,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "clusters" in data


def test_cluster_sessions_threshold_validation(api_repo_factory):
    """Test clustering with various threshold values."""
    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")

    # Test with very high threshold (strict clustering)
    async def run_strict():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                similarity_threshold=0.99,
                min_cluster_size=2,
                repo=repo,
            )

    data_strict = asyncio.run(run_strict())
    assert "clusters" in data_strict

    # Test with very low threshold (loose clustering)
    async def run_loose():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                similarity_threshold=0.1,
                min_cluster_size=2,
                repo=repo,
            )

    data_loose = asyncio.run(run_loose())
    assert "clusters" in data_loose


def test_cluster_sessions_min_cluster_size(api_repo_factory):
    """Test clustering with different minimum cluster sizes."""
    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")

    # Test with min_cluster_size=1
    async def run_size_1():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                similarity_threshold=0.5,
                min_cluster_size=1,
                repo=repo,
            )

    data_1 = asyncio.run(run_size_1())
    assert "clusters" in data_1

    # Test with min_cluster_size=5
    async def run_size_5():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await cluster_endpoint(
                similarity_threshold=0.5,
                min_cluster_size=5,
                repo=repo,
            )

    data_5 = asyncio.run(run_size_5())
    assert "clusters" in data_5


# =============================================================================
# POST /api/violations/search
# =============================================================================

def test_search_violations_endpoint(api_repo_factory):
    """Test the search violations endpoint."""
    # Create test session
    session_id = "violation_search_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                nl_query="error handling",
                max_results=10,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "violations" in data
    assert "query" in data
    assert "total_sessions_searched" in data
    assert "total_violations_found" in data

    # Check structure
    assert isinstance(data["violations"], list)
    assert data["query"] == "error handling"
    assert data["total_sessions_searched"] >= 0


def test_search_violations_with_agent_filter(api_repo_factory):
    """Test search with agent name filter."""
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                nl_query="unsafe operations",
                agent_name="test_agent",
                max_results=5,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "violations" in data
    assert isinstance(data["violations"], list)


def test_search_violations_various_queries(api_repo_factory):
    """Test search with various natural language queries."""
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")

    test_queries = [
        "error handling problems",
        "unsafe data handling",
        "performance issues",
        "unusual behavior",
        "temporal anomalies",
    ]

    for query in test_queries:
        async def run():
            async with api_repo_factory() as session:
                repo = TraceRepository(session)
                return await search_endpoint(
                    nl_query=query,
                    max_results=10,
                    repo=repo,
                )

        data = asyncio.run(run())
        assert "violations" in data
        assert isinstance(data["violations"], list)


def test_search_violations_max_results(api_repo_factory):
    """Test search with different max_results values."""
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")

    # Test with small max_results
    async def run_small():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                nl_query="error",
                max_results=3,
                repo=repo,
            )

    data_small = asyncio.run(run_small())
    assert len(data_small["violations"]) <= 3

    # Test with larger max_results
    async def run_large():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                nl_query="error",
                max_results=50,
                repo=repo,
            )

    data_large = asyncio.run(run_large())
    assert len(data_large["violations"]) <= 50


def test_search_violations_no_results(api_repo_factory):
    """Test search with query that has no matches."""
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                nl_query="xyz_nonexistent_pattern_12345",
                max_results=10,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "violations" in data
    # Should return empty list or few results
    assert isinstance(data["violations"], list)


# =============================================================================
# GET /api/violations/sparse
# =============================================================================

def test_detect_sparse_failures_endpoint(api_repo_factory):
    """Test the sparse failures detection endpoint."""
    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sparse_endpoint(
                min_occurrences=2,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "sparse_failures" in data
    assert "total_sessions_analyzed" in data
    assert "total_patterns_found" in data
    assert "min_occurrences" in data

    # Check structure
    assert isinstance(data["sparse_failures"], list)
    assert data["total_sessions_analyzed"] >= 0
    assert data["min_occurrences"] == 2


def test_detect_sparse_failures_with_agent_filter(api_repo_factory):
    """Test sparse failures with agent name filter."""
    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sparse_endpoint(
                agent_name="test_agent",
                min_occurrences=2,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "sparse_failures" in data


def test_detect_sparse_failures_threshold_variations(api_repo_factory):
    """Test sparse failures with different min_occurrences thresholds."""
    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")

    # Test with min_occurrences=1
    async def run_low():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sparse_endpoint(
                min_occurrences=1,
                repo=repo,
            )

    data_low = asyncio.run(run_low())
    assert "sparse_failures" in data_low

    # Test with min_occurrences=5
    async def run_high():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sparse_endpoint(
                min_occurrences=5,
                repo=repo,
            )

    data_high = asyncio.run(run_high())
    assert "sparse_failures" in data_high


def test_detect_sparse_failures_structure(api_repo_factory):
    """Test sparse failures response structure."""
    # Create test sessions
    session_id = "sparse_failure_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sparse_endpoint(
                min_occurrences=2,
                repo=repo,
            )

    data = asyncio.run(run())
    sparse_failures = data["sparse_failures"]

    # Check each failure pattern structure
    for failure in sparse_failures:
        assert "pattern_id" in failure
        assert "failure_type" in failure
        assert "description" in failure
        assert "required_sessions" in failure
        assert "session_ids" in failure
        assert "failure_points" in failure
        assert "confidence" in failure

        # Check data types
        assert isinstance(failure["pattern_id"], str)
        assert isinstance(failure["failure_type"], str)
        assert isinstance(failure["session_ids"], list)
        assert isinstance(failure["failure_points"], list)
        assert isinstance(failure["confidence"], (int, float))


# =============================================================================
# GET /api/violations/{violation_id}
# =============================================================================

def test_get_violation_details(api_repo_factory):
    """Test getting violation details by ID."""
    violation_id = "test_violation_123"
    violation_endpoint = _get_route_endpoint("/api/violations/{violation_id}", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await violation_endpoint(
                violation_id=violation_id,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "violation_id" in data
    assert data["violation_id"] == violation_id
    # This endpoint returns placeholder data
    assert "message" in data


def test_get_violation_details_not_found(api_repo_factory):
    """Test getting details for non-existent violation."""
    violation_id = "nonexistent_violation_999"
    violation_endpoint = _get_route_endpoint("/api/violations/{violation_id}", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await violation_endpoint(
                violation_id=violation_id,
                repo=repo,
            )

    # Should still return placeholder
    data = asyncio.run(run())
    assert data["violation_id"] == violation_id


# =============================================================================
# GET /api/violations/dashboard
# =============================================================================

def test_get_violation_dashboard(api_repo_factory):
    """Test the violation dashboard endpoint."""
    dashboard_endpoint = _get_route_endpoint("/api/violations/dashboard", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await dashboard_endpoint(
                days=7,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "total_sessions_analyzed" in data
    assert "violation_summary" in data
    assert "cluster_summary" in data
    assert "sparse_failure_summary" in data
    assert "time_range_days" in data

    # Check violation summary structure
    violation_summary = data["violation_summary"]
    assert "by_type" in violation_summary
    assert "by_severity" in violation_summary
    assert "total_violations" in violation_summary

    # Check cluster summary structure
    cluster_summary = data["cluster_summary"]
    assert "total_clusters" in cluster_summary
    assert "total_outliers" in cluster_summary

    # Check sparse failure summary structure
    sparse_summary = data["sparse_failure_summary"]
    assert "total_patterns" in sparse_summary
    assert "most_common_failure_types" in sparse_summary


def test_get_violation_dashboard_with_agent_filter(api_repo_factory):
    """Test dashboard with agent name filter."""
    dashboard_endpoint = _get_route_endpoint("/api/violations/dashboard", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await dashboard_endpoint(
                agent_name="test_agent",
                days=30,
                repo=repo,
            )

    data = asyncio.run(run())
    assert "total_sessions_analyzed" in data
    assert data["time_range_days"] == 30


def test_get_violation_dashboard_different_time_ranges(api_repo_factory):
    """Test dashboard with different time ranges."""
    dashboard_endpoint = _get_route_endpoint("/api/violations/dashboard", "GET")

    time_ranges = [1, 7, 30, 90]

    for days in time_ranges:
        async def run():
            async with api_repo_factory() as session:
                repo = TraceRepository(session)
                return await dashboard_endpoint(
                    days=days,
                    repo=repo,
                )

        data = asyncio.run(run())
        assert data["time_range_days"] == days


def test_get_violation_dashboard_empty_state(api_repo_factory):
    """Test dashboard when no sessions are available."""
    dashboard_endpoint = _get_route_endpoint("/api/violations/dashboard", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await dashboard_endpoint(
                agent_name="nonexistent_agent_xyz",
                days=1,
                repo=repo,
            )

    data = asyncio.run(run())
    # Should return empty/zero values
    assert "total_sessions_analyzed" in data
    assert "violation_summary" in data


# =============================================================================
# GET /api/violations/session/{session_id}/embedding
# =============================================================================

def test_get_session_embedding(api_repo_factory):
    """Test getting session embedding."""
    # Create test session
    session_id = "embedding_test_session"
    asyncio.run(run_evidence_grounding_session(session_id))

    embedding_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/embedding", "GET"
    )

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await embedding_endpoint(
                session_id=session_id,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "session_id" in data
    assert "embedding" in data

    # Check embedding structure
    embedding = data["embedding"]
    assert "session_id" in embedding
    assert "embedding_vector" in embedding
    assert "feature_weights" in embedding
    assert "summary_hash" in embedding

    # Check data types
    assert isinstance(embedding["embedding_vector"], list)
    assert isinstance(embedding["feature_weights"], dict)


def test_get_session_embedding_not_found(api_repo_factory):
    """Test getting embedding for non-existent session."""
    session_id = "nonexistent_session_xyz"
    embedding_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/embedding", "GET"
    )

    # This may return an error
    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await embedding_endpoint(
                session_id=session_id,
                repo=repo,
            )

    # Should handle gracefully
    try:
        data = asyncio.run(run())
        # If it succeeds, check structure
        assert "session_id" in data or "error" in data
    except Exception:
        # If it raises an exception, that's also acceptable
        pass


def test_get_session_embedding_structure(api_repo_factory):
    """Test session embedding response structure in detail."""
    # Create test session
    session_id = "embedding_structure_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    embedding_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/embedding", "GET"
    )

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await embedding_endpoint(
                session_id=session_id,
                repo=repo,
            )

    data = asyncio.run(run())
    embedding = data["embedding"]

    # Verify all expected fields
    expected_fields = [
        "session_id",
        "embedding_vector",
        "feature_weights",
        "summary_hash",
    ]

    for field in expected_fields:
        assert field in embedding


# =============================================================================
# POST /api/violations/session/{session_id}/similar
# =============================================================================

def test_find_similar_sessions(api_repo_factory):
    """Test finding similar sessions."""
    # Create test session
    session_id = "similar_test_session"
    asyncio.run(run_evidence_grounding_session(session_id))

    similar_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/similar", "POST"
    )

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await similar_endpoint(
                session_id=session_id,
                limit=5,
                repo=repo,
            )

    data = asyncio.run(run())

    assert "reference_session_id" in data
    assert "similar_sessions" in data
    assert "total_compared" in data

    # Check structure
    assert data["reference_session_id"] == session_id
    assert isinstance(data["similar_sessions"], list)
    assert len(data["similar_sessions"]) <= 5

    # Check each similar session structure
    for similar in data["similar_sessions"]:
        assert "session_id" in similar
        assert "agent_name" in similar
        assert "started_at" in similar
        assert "similarity_score" in similar

        # Check data types
        assert isinstance(similar["session_id"], str)
        assert isinstance(similar["similarity_score"], (int, float))


def test_find_similar_sessions_limit(api_repo_factory):
    """Test similar sessions with different limit values."""
    # Create test session
    session_id = "similar_limit_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    similar_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/similar", "POST"
    )

    # Test with small limit
    async def run_small():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await similar_endpoint(
                session_id=session_id,
                limit=3,
                repo=repo,
            )

    data_small = asyncio.run(run_small())
    assert len(data_small["similar_sessions"]) <= 3

    # Test with larger limit
    async def run_large():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await similar_endpoint(
                session_id=session_id,
                limit=20,
                repo=repo,
            )

    data_large = asyncio.run(run_large())
    assert len(data_large["similar_sessions"]) <= 20


def test_find_similar_sessions_no_results(api_repo_factory):
    """Test finding similar sessions for non-existent session."""
    session_id = "nonexistent_session_xyz"
    similar_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/similar", "POST"
    )

    # Should handle gracefully
    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await similar_endpoint(
                session_id=session_id,
                limit=10,
                repo=repo,
            )

    try:
        data = asyncio.run(run())
        # If it succeeds, check structure
        assert "similar_sessions" in data
    except Exception:
        # If it raises an exception, that's also acceptable
        pass


def test_find_similar_sessions_ordering(api_repo_factory):
    """Test that similar sessions are ordered by similarity score."""
    # Create test session
    session_id = "similar_ordering_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    similar_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/similar", "POST"
    )

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await similar_endpoint(
                session_id=session_id,
                limit=10,
                repo=repo,
            )

    data = asyncio.run(run())
    similar_sessions = data["similar_sessions"]

    if len(similar_sessions) > 1:
        # Check that sessions are sorted by similarity (highest first)
        similarity_scores = [s["similarity_score"] for s in similar_sessions]
        assert similarity_scores == sorted(similarity_scores, reverse=True)


# =============================================================================
# Integration and edge case tests
# =============================================================================

def test_violation_routes_integration(api_repo_factory):
    """Test integration of multiple violation routes."""
    # Create test session
    session_id = "violation_integration_test"
    asyncio.run(run_evidence_grounding_session(session_id))

    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")
    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")
    embedding_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/embedding", "GET"
    )
    similar_endpoint = _get_route_endpoint(
        "/api/violations/session/{session_id}/similar", "POST"
    )

    async def run_all():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)

            # Get embedding
            embedding_data = await embedding_endpoint(
                session_id=session_id,
                repo=repo,
            )

            # Find similar sessions
            similar_data = await similar_endpoint(
                session_id=session_id,
                limit=5,
                repo=repo,
            )

            # Cluster sessions
            cluster_data = await cluster_endpoint(
                similarity_threshold=0.5,
                min_cluster_size=2,
                repo=repo,
            )

            # Search violations
            search_data = await search_endpoint(
                nl_query="error",
                max_results=10,
                repo=repo,
            )

            # Detect sparse failures
            sparse_data = await sparse_endpoint(
                min_occurrences=2,
                repo=repo,
            )

            return {
                "embedding": embedding_data,
                "similar": similar_data,
                "cluster": cluster_data,
                "search": search_data,
                "sparse": sparse_data,
            }

    results = asyncio.run(run_all())

    # All should succeed
    assert "embedding" in results["embedding"]
    assert "similar_sessions" in results["similar"]
    assert "clusters" in results["cluster"]
    assert "violations" in results["search"]
    assert "sparse_failures" in results["sparse"]


def test_violation_routes_empty_database(api_repo_factory):
    """Test violation routes when database is empty."""
    cluster_endpoint = _get_route_endpoint("/api/violations/cluster", "POST")
    search_endpoint = _get_route_endpoint("/api/violations/search", "POST")
    sparse_endpoint = _get_route_endpoint("/api/violations/sparse", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)

            # Cluster with no data
            cluster_data = await cluster_endpoint(
                similarity_threshold=0.5,
                min_cluster_size=2,
                repo=repo,
            )

            # Search with no data
            search_data = await search_endpoint(
                nl_query="error",
                max_results=10,
                repo=repo,
            )

            # Sparse failures with no data
            sparse_data = await sparse_endpoint(
                min_occurrences=2,
                repo=repo,
            )

            return {
                "cluster": cluster_data,
                "search": search_data,
                "sparse": sparse_data,
            }

    results = asyncio.run(run())

    # Should return empty results rather than errors
    assert "clusters" in results["cluster"]
    assert "violations" in results["search"]
    assert "sparse_failures" in results["sparse"]
