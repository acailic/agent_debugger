"""Tests for pattern detection functionality."""

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events import Session, SessionStatus
from collector.patterns import Pattern, PatternDetector
from collector.patterns.health_report import generate_health_report


def _make_session(
    session_id: str = "session-1",
    agent_name: str = "agent",
    started_at: datetime | None = None,
    errors: int = 0,
    tool_calls: int = 0,
    replay_value: float = 0.8,
) -> Session:
    """Create a test session."""
    if started_at is None:
        started_at = datetime.now(timezone.utc)

    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=started_at,
        status=SessionStatus.COMPLETED if errors == 0 else SessionStatus.ERROR,
        total_tokens=1000,
        total_cost_usd=0.5,
        tool_calls=tool_calls,
        llm_calls=10,
        errors=errors,
        replay_value=replay_value,
        config={"mode": "test"},
        tags=["test"],
    )


# =============================================================================
# Test PatternDetector
# =============================================================================


class TestPatternDetector:
    """Test suite for PatternDetector class."""

    def test_detector_initialization(self):
        """Test that PatternDetector initializes with default thresholds."""
        detector = PatternDetector()

        assert detector.error_rate_threshold == 0.5
        assert detector.tool_failure_threshold == 0.5
        assert detector.confidence_drop_threshold == 0.2
        assert detector.recent_window_days == 1
        assert detector.baseline_window_days == 7

    def test_detector_custom_thresholds(self):
        """Test that PatternDetector accepts custom thresholds."""
        detector = PatternDetector(
            error_rate_threshold=0.3,
            tool_failure_threshold=0.4,
            confidence_drop_threshold=0.1,
        )

        assert detector.error_rate_threshold == 0.3
        assert detector.tool_failure_threshold == 0.4
        assert detector.confidence_drop_threshold == 0.1

    def test_detect_all_patterns_empty_sessions(self):
        """Test pattern detection with empty session list."""
        detector = PatternDetector()
        patterns = detector.detect_all_patterns([])

        assert patterns == []

    def test_detect_all_patterns_groups_by_agent(self):
        """Test that patterns are grouped by agent name."""
        detector = PatternDetector()

        # Create sessions for different agents
        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        sessions = [
            # Agent A - baseline (no errors)
            _make_session("s1", "agent-a", baseline_time, errors=0),
            _make_session("s2", "agent-a", baseline_time, errors=0),
            _make_session("s3", "agent-a", baseline_time, errors=0),
            # Agent A - recent (with errors)
            _make_session("s4", "agent-a", recent_time, errors=5, tool_calls=10),
            _make_session("s5", "agent-a", recent_time, errors=3, tool_calls=10),
            # Agent B - baseline (no errors)
            _make_session("s6", "agent-b", baseline_time, errors=0),
            _make_session("s7", "agent-b", baseline_time, errors=0),
            _make_session("s8", "agent-b", baseline_time, errors=0),
            # Agent B - recent (no errors, no pattern)
            _make_session("s9", "agent-b", recent_time, errors=0),
        ]

        patterns = detector.detect_all_patterns(sessions)

        # Should detect patterns for agent-a but not agent-b
        agent_a_patterns = [p for p in patterns if p.agent_name == "agent-a"]
        agent_b_patterns = [p for p in patterns if p.agent_name == "agent-b"]

        assert len(agent_a_patterns) > 0
        assert len(agent_b_patterns) == 0


class TestErrorRateTrendDetection:
    """Test suite for error rate trend detection."""

    def test_detect_error_rate_increase(self):
        """Test detection of increasing error rates."""
        detector = PatternDetector(error_rate_threshold=0.5)

        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        # Baseline: 0% error rate
        baseline_sessions = [
            _make_session("b1", "agent", baseline_time, errors=0),
            _make_session("b2", "agent", baseline_time, errors=0),
            _make_session("b3", "agent", baseline_time, errors=0),
        ]

        # Recent: 100% error rate (all sessions have errors)
        recent_sessions = [
            _make_session("r1", "agent", recent_time, errors=5),
            _make_session("r2", "agent", recent_time, errors=3),
        ]

        patterns = detector.detect_error_rate_trends("agent", baseline_sessions, recent_sessions)

        assert len(patterns) == 1
        pattern = patterns[0]

        assert pattern.pattern_type == "error_trend"
        assert pattern.agent_name == "agent"
        assert pattern.severity in ["warning", "critical"]
        assert pattern.change_percent is not None
        assert pattern.change_percent > 0.5  # Should exceed threshold
        assert len(pattern.affected_sessions) > 0

    def test_no_error_rate_trend_when_stable(self):
        """Test that no pattern is detected when error rate is stable."""
        detector = PatternDetector()

        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        # Both baseline and recent have similar error rates
        baseline_sessions = [
            _make_session("b1", "agent", baseline_time, errors=1),
            _make_session("b2", "agent", baseline_time, errors=0),
            _make_session("b3", "agent", baseline_time, errors=0),
        ]

        recent_sessions = [
            _make_session("r1", "agent", recent_time, errors=1),
            _make_session("r2", "agent", recent_time, errors=0),
        ]

        patterns = detector.detect_error_rate_trends("agent", baseline_sessions, recent_sessions)

        assert len(patterns) == 0


class TestToolFailureDetection:
    """Test suite for tool failure frequency detection."""

    def test_detect_tool_failure_increase(self):
        """Test detection of increasing tool failure rates."""
        detector = PatternDetector(tool_failure_threshold=0.5)

        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        # Baseline: low failure rate
        baseline_sessions = [
            _make_session("b1", "agent", baseline_time, errors=1, tool_calls=10),
            _make_session("b2", "agent", baseline_time, errors=0, tool_calls=10),
            _make_session("b3", "agent", baseline_time, errors=1, tool_calls=10),
        ]

        # Recent: high failure rate
        recent_sessions = [
            _make_session("r1", "agent", recent_time, errors=8, tool_calls=10),
            _make_session("r2", "agent", recent_time, errors=5, tool_calls=10),
        ]

        patterns = detector.detect_tool_failure_frequency("agent", baseline_sessions, recent_sessions)

        assert len(patterns) == 1
        pattern = patterns[0]

        assert pattern.pattern_type == "tool_failure"
        assert pattern.agent_name == "agent"
        assert pattern.change_percent is not None
        assert pattern.change_percent > 0.5


class TestConfidenceDropDetection:
    """Test suite for confidence drop detection."""

    def test_detect_confidence_drop(self):
        """Test detection of confidence drops using replay_value as proxy."""
        detector = PatternDetector(confidence_drop_threshold=0.2)

        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        # Baseline: high replay value
        baseline_sessions = [
            _make_session("b1", "agent", baseline_time, replay_value=0.9),
            _make_session("b2", "agent", baseline_time, replay_value=0.8),
            _make_session("b3", "agent", baseline_time, replay_value=0.85),
        ]

        # Recent: low replay value (drop > 20%)
        recent_sessions = [
            _make_session("r1", "agent", recent_time, replay_value=0.5),
            _make_session("r2", "agent", recent_time, replay_value=0.6),
        ]

        patterns = detector.detect_confidence_drops("agent", baseline_sessions, recent_sessions)

        assert len(patterns) == 1
        pattern = patterns[0]

        assert pattern.pattern_type == "confidence_drop"
        assert pattern.change_percent is not None
        assert pattern.change_percent < -0.2  # Should exceed threshold


class TestNewFailureModeDetection:
    """Test suite for new failure mode detection."""

    def test_detect_new_failure_mode(self):
        """Test detection of new failure modes."""
        detector = PatternDetector()

        now = datetime.now(timezone.utc)
        baseline_time = now - timedelta(days=5)
        recent_time = now - timedelta(hours=1)

        # Baseline: few error sessions
        baseline_sessions = [
            _make_session("b1", "agent", baseline_time, errors=0),
            _make_session("b2", "agent", baseline_time, errors=0),
            _make_session("b3", "agent", baseline_time, errors=1),  # Only 1 error session
        ]

        # Recent: many error sessions (2x increase)
        recent_sessions = [
            _make_session("r1", "agent", recent_time, errors=5),
            _make_session("r2", "agent", recent_time, errors=3),
            _make_session("r3", "agent", recent_time, errors=2),
        ]

        patterns = detector.detect_new_failure_modes("agent", baseline_sessions, recent_sessions)

        assert len(patterns) == 1
        pattern = patterns[0]

        assert pattern.pattern_type == "new_failure_mode"
        assert len(pattern.affected_sessions) > 0


# =============================================================================
# Test Health Report Generation
# =============================================================================


class TestHealthReportGeneration:
    """Test suite for health report generation."""

    def test_generate_health_report_no_patterns(self):
        """Test health report with no detected patterns."""
        patterns = []

        report = generate_health_report(patterns, total_sessions=100, total_agents=5)

        assert report.overall_health_score == 100.0
        assert report.agent_summary == "HEALTHY: No significant patterns detected"
        assert report.total_patterns == 0
        assert len(report.critical_patterns) == 0
        assert len(report.top_issues) == 0
        assert len(report.affected_agents) == 0

    def test_generate_health_report_with_warnings(self):
        """Test health report with warning patterns."""
        now = datetime.now(timezone.utc)

        patterns = [
            Pattern(
                pattern_type="error_trend",
                agent_name="agent-a",
                severity="warning",
                description="Error rate increased",
                affected_sessions=["s1", "s2"],
                detected_at=now,
                change_percent=0.6,
            ),
            Pattern(
                pattern_type="tool_failure",
                agent_name="agent-b",
                severity="warning",
                description="Tool failures increased",
                affected_sessions=["s3"],
                detected_at=now,
                change_percent=0.7,
            ),
        ]

        report = generate_health_report(patterns, total_sessions=50, total_agents=2)

        # Health score should be reduced (2 warnings * 5 = 10 points)
        assert report.overall_health_score == 90.0
        # With only 2 warnings, the summary says "minor issues" not "warning"
        assert "minor issues" in report.agent_summary.lower()
        assert report.total_patterns == 2
        assert report.patterns_by_severity["warning"] == 2
        assert report.patterns_by_severity["critical"] == 0
        assert len(report.critical_patterns) == 0
        assert len(report.top_issues) == 2
        # Recommendations are generated for each pattern type
        assert len(report.recommendations) == 2

    def test_generate_health_report_with_critical(self):
        """Test health report with critical patterns."""
        now = datetime.now(timezone.utc)

        patterns = [
            Pattern(
                pattern_type="error_trend",
                agent_name="agent-a",
                severity="critical",
                description="Critical error rate increase",
                affected_sessions=["s1", "s2", "s3"],
                detected_at=now,
                change_percent=1.5,
            ),
        ]

        report = generate_health_report(patterns, total_sessions=30, total_agents=1)

        # Health score should be significantly reduced
        assert report.overall_health_score == 85.0  # 100 - 15 for critical
        assert "critical" in report.agent_summary.lower()
        assert len(report.critical_patterns) == 1
        assert report.patterns_by_severity["critical"] == 1

    def test_health_report_includes_recommendations(self):
        """Test that health report includes actionable recommendations."""
        now = datetime.now(timezone.utc)

        patterns = [
            Pattern(
                pattern_type="error_trend",
                agent_name="agent-a",
                severity="warning",
                description="Error rate increased",
                affected_sessions=["s1"],
                detected_at=now,
                change_percent=0.6,
            ),
        ]

        report = generate_health_report(patterns)

        assert len(report.recommendations) > 0
        # Check that recommendations are strings
        for rec in report.recommendations:
            assert isinstance(rec, str)

    def test_health_report_top_issues_ranking(self):
        """Test that top issues are properly ranked."""
        now = datetime.now(timezone.utc)

        patterns = [
            Pattern(
                pattern_type="error_trend",
                agent_name="agent-a",
                severity="warning",
                description="Minor error trend",
                affected_sessions=["s1"],
                detected_at=now,
                change_percent=0.3,
            ),
            Pattern(
                pattern_type="tool_failure",
                agent_name="agent-b",
                severity="critical",
                description="Critical tool failure",
                affected_sessions=["s2", "s3", "s4"],
                detected_at=now,
                change_percent=1.2,
            ),
        ]

        report = generate_health_report(patterns)

        assert len(report.top_issues) == 2
        # Critical pattern should be ranked first
        assert report.top_issues[0]["severity"] == "critical"
        assert report.top_issues[1]["severity"] == "warning"


# =============================================================================
# Test Pattern Repository Database Operations
# =============================================================================


class TestPatternRepositoryDB:
    """Test suite for PatternRepository database operations."""

    @pytest.mark.asyncio
    async def test_create_pattern(self, db_session):
        """Test creating a new pattern."""
        from storage.repositories.pattern_repo import PatternRepository as PatternRepo

        repo = PatternRepo(db_session, tenant_id="test-tenant")

        pattern = await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="test-agent",
            severity="warning",
            description="Test pattern",
            affected_sessions=["s1", "s2"],
            baseline_value=0.1,
            current_value=0.2,
            threshold=0.5,
            change_percent=1.0,
        )

        await repo.commit()

        assert pattern.id is not None
        assert pattern.pattern_type == "error_trend"
        assert pattern.agent_name == "test-agent"
        assert pattern.severity == "warning"
        assert pattern.status == "active"
        assert len(pattern.affected_sessions) == 2

    @pytest.mark.asyncio
    async def test_get_pattern_by_agent(self, db_session):
        """Test retrieving patterns by agent name."""
        from storage.repositories.pattern_repo import PatternRepository as PatternRepo

        repo = PatternRepo(db_session, tenant_id="test-tenant")

        # Create patterns for different agents
        await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="agent-a",
            severity="warning",
            description="Pattern A",
            affected_sessions=["s1"],
        )

        await repo.create_pattern(
            pattern_type="tool_failure",
            agent_name="agent-b",
            severity="critical",
            description="Pattern B",
            affected_sessions=["s2"],
        )

        await repo.create_pattern(
            pattern_type="confidence_drop",
            agent_name="agent-a",
            severity="warning",
            description="Pattern C",
            affected_sessions=["s3"],
        )

        await repo.commit()

        patterns = await repo.get_patterns_by_agent("agent-a")

        assert len(patterns) == 2
        assert all(p.agent_name == "agent-a" for p in patterns)

    @pytest.mark.asyncio
    async def test_get_recent_patterns(self, db_session):
        """Test retrieving recent patterns."""
        from storage.repositories.pattern_repo import PatternRepository as PatternRepo

        repo = PatternRepo(db_session, tenant_id="test-tenant")

        # Create patterns
        await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="agent-a",
            severity="warning",
            description="Pattern 1",
            affected_sessions=["s1"],
        )

        await repo.create_pattern(
            pattern_type="tool_failure",
            agent_name="agent-b",
            severity="critical",
            description="Pattern 2",
            affected_sessions=["s2"],
        )

        await repo.commit()

        patterns = await repo.get_recent_patterns(limit=10)

        assert len(patterns) >= 2

    @pytest.mark.asyncio
    async def test_update_pattern_status(self, db_session):
        """Test updating pattern status."""
        from storage.repositories.pattern_repo import PatternRepository as PatternRepo

        repo = PatternRepo(db_session, tenant_id="test-tenant")

        pattern = await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="agent-a",
            severity="warning",
            description="Test pattern",
            affected_sessions=["s1"],
        )

        await repo.commit()

        # Update status to resolved
        updated = await repo.update_pattern_status(pattern.id, "resolved", resolved_by="user-123")

        await repo.commit()

        assert updated.status == "resolved"
        assert updated.resolved_at is not None
        assert updated.resolved_by == "user-123"

    @pytest.mark.asyncio
    async def test_count_patterns_by_type(self, db_session):
        """Test counting patterns by type."""
        from storage.repositories.pattern_repo import PatternRepository as PatternRepo

        repo = PatternRepo(db_session, tenant_id="test-tenant")

        await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="agent-a",
            severity="warning",
            description="Pattern 1",
            affected_sessions=["s1"],
        )

        await repo.create_pattern(
            pattern_type="error_trend",
            agent_name="agent-b",
            severity="warning",
            description="Pattern 2",
            affected_sessions=["s2"],
        )

        await repo.create_pattern(
            pattern_type="tool_failure",
            agent_name="agent-a",
            severity="critical",
            description="Pattern 3",
            affected_sessions=["s3"],
        )

        await repo.commit()

        counts = await repo.count_patterns_by_type()

        assert counts["error_trend"] == 2
        assert counts["tool_failure"] == 1


# =============================================================================
# Test API Endpoints
# =============================================================================


class TestPatternAPIEndpoints:
    """Test suite for pattern detection API endpoints."""

    def test_patterns_endpoint_exists(self):
        """Test that patterns endpoint is registered."""
        from api.main import create_app

        app = create_app()

        # Verify the endpoint exists
        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/api/analytics/patterns" in route_paths

    def test_health_report_endpoint_exists(self):
        """Test that health report endpoint is registered."""
        from api.main import create_app

        app = create_app()

        # Verify the endpoint exists
        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/api/analytics/health-report" in route_paths
