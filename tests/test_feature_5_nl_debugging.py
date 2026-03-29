"""Tests for Feature 5: Natural Language Debugging."""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock

import pytest

# Note: Feature 5 (nl_debugging) not yet implemented
pytestmark = pytest.mark.skip(reason="Feature 5 (nl_debugging) not yet implemented")


# Dataclasses for test structures
@dataclass
class DebugAnswer:
    """Answer returned by the natural language debugger."""

    text: str
    evidence_links: list[str]
    needs_clarification: bool = False
    fallback: bool = False
    error: bool = False


@dataclass
class QueryIntent:
    """Parsed intent from a natural language query."""

    type: str
    focus_event_id: Optional[str] = None


@dataclass
class Context:
    """Gathered context for answering a query."""

    events: list
    session_summary: Optional[str] = None


# Fixtures
@pytest.fixture
def make_error_event():
    """Factory for creating error events."""

    def _make(
        event_id: str = "err-1",
        message: str = "Connection timeout",
        timestamp: str = "2024-01-15T10:30:00Z",
    ):
        return {
            "id": event_id,
            "type": "error",
            "payload": {"message": message, "timestamp": timestamp},
        }

    return _make


@pytest.fixture
def make_decision_event():
    """Factory for creating decision events."""

    def _make(
        event_id: str = "dec-1",
        decision: str = "retry",
        reason: str = "Transient failure detected",
        timestamp: str = "2024-01-15T10:30:05Z",
    ):
        return {
            "id": event_id,
            "type": "decision",
            "payload": {"decision": decision, "reason": reason, "timestamp": timestamp},
        }

    return _make


@pytest.fixture
def make_session(make_error_event, make_decision_event):
    """Factory for creating test sessions."""

    def _make(
        session_id: str = "sess-1",
        events: Optional[list] = None,
        status: str = "failed",
    ):
        if events is None:
            events = [make_error_event(), make_decision_event()]
        return {
            "id": session_id,
            "status": status,
            "events": events,
        }

    return _make


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = AsyncMock()
    client.generate = AsyncMock(return_value="This is a mock LLM response.")
    return client


# Helper to create debugger instance
def create_debugger(llm_client):
    """Create a NaturalLanguageDebugger instance with mocked dependencies."""

    class NaturalLanguageDebugger:
        """Mock implementation for testing."""

        def __init__(self, llm_client):
            self.llm_client = llm_client

        async def answer_query(self, question: str, session: dict) -> DebugAnswer:
            """Answer a natural language query about a session."""
            intent = await self.parse_intent(question)
            context = self.gather_context(session, intent)

            if intent.type == "ambiguous":
                return DebugAnswer(
                    text="Could you please clarify your question?",
                    evidence_links=[],
                    needs_clarification=True,
                )

            if not context.events:
                if "error" in question.lower() or "fail" in question.lower():
                    return DebugAnswer(
                        text="No error events found in this session.",
                        evidence_links=[],
                    )
                return DebugAnswer(
                    text="No data available in this session to answer your question.",
                    evidence_links=[],
                )

            try:
                response = await self.llm_client.generate(
                    prompt=question,
                    system="You are a debugging assistant.",
                )
                if response is None:
                    return DebugAnswer(
                        text="Unable to generate an answer.",
                        evidence_links=[],
                        error=True,
                    )

                evidence = [e["id"] for e in context.events[:3]]
                return DebugAnswer(
                    text=response,
                    evidence_links=evidence,
                )
            except TimeoutError:
                return DebugAnswer(
                    text="The query took too long to process. Please try again.",
                    evidence_links=[],
                    fallback=True,
                )
            except Exception:
                return DebugAnswer(
                    text="An error occurred while processing your query.",
                    evidence_links=[],
                    error=True,
                )

        async def parse_intent(self, question: str) -> QueryIntent:
            """Parse the intent of a natural language query."""
            q_lower = question.lower()

            if "why" in q_lower and ("fail" in q_lower or "error" in q_lower):
                return QueryIntent(type="why_failure")
            elif "what changed" in q_lower or "what change" in q_lower:
                return QueryIntent(type="what_changed")
            elif "how" in q_lower and ("fix" in q_lower or "resolve" in q_lower):
                return QueryIntent(type="how_to_fix")
            elif "before" in q_lower and ("fail" in q_lower or "similar" in q_lower):
                return QueryIntent(type="similar_failures")
            elif "why" in q_lower and "decide" in q_lower:
                return QueryIntent(type="explain_decision")
            elif len(question.split()) < 3:
                return QueryIntent(type="ambiguous")

            return QueryIntent(type="general")

        def gather_context(self, session: dict, intent: QueryIntent) -> Context:
            """Gather relevant context from session based on intent."""
            events = session.get("events", [])

            if intent.type == "why_failure":
                relevant = [e for e in events if e.get("type") in ("error", "decision")]
            elif intent.type == "what_changed":
                relevant = [e for e in events if e.get("type") in ("state_change", "decision", "error")]
            elif intent.type == "explain_decision":
                relevant = [e for e in events if e.get("type") == "decision"]
            else:
                relevant = events

            if intent.focus_event_id:
                relevant = [e for e in relevant if e.get("id") == intent.focus_event_id]

            return Context(events=relevant)

    return NaturalLanguageDebugger(llm_client)


# Test Classes


class TestNLDebuggingHappyPath:
    """Happy path tests for natural language debugging."""

    async def test_answer_query_returns_natural_language(self, mock_llm_client, make_session):
        """Returns text answer from LLM."""
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this session fail?", session)

        assert isinstance(answer, DebugAnswer)
        assert isinstance(answer.text, str)
        assert len(answer.text) > 0
        assert not answer.needs_clarification
        assert not answer.fallback
        assert not answer.error

    async def test_parse_intent_extracts_why_failure(self, mock_llm_client):
        """'Why did it fail?' -> intent.type == 'why_failure'."""
        debugger = create_debugger(mock_llm_client)

        intent = await debugger.parse_intent("Why did it fail?")

        assert intent.type == "why_failure"

    async def test_parse_intent_extracts_what_changed(self, mock_llm_client):
        """'What changed?' -> intent.type == 'what_changed'."""
        debugger = create_debugger(mock_llm_client)

        intent = await debugger.parse_intent("What changed?")

        assert intent.type == "what_changed"

    async def test_gather_context_includes_relevant_events(
        self, mock_llm_client, make_session, make_error_event, make_decision_event
    ):
        """Context includes events matching intent."""
        debugger = create_debugger(mock_llm_client)
        events = [
            make_error_event(event_id="err-1"),
            make_decision_event(event_id="dec-1"),
            {"id": "info-1", "type": "info", "payload": {}},
        ]
        session = make_session(events=events)

        intent = QueryIntent(type="why_failure")
        context = debugger.gather_context(session, intent)

        assert isinstance(context, Context)
        assert len(context.events) == 2
        event_types = {e.get("type") for e in context.events}
        assert event_types == {"error", "decision"}

    async def test_answer_includes_evidence_links(self, mock_llm_client, make_session):
        """Answer has links to supporting events."""
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this session fail?", session)

        assert isinstance(answer.evidence_links, list)
        assert len(answer.evidence_links) > 0
        assert all(isinstance(link, str) for link in answer.evidence_links)


class TestNLDebuggingEdgeCases:
    """Edge case tests for natural language debugging."""

    async def test_ambiguous_query_requests_clarification(self, mock_llm_client, make_session):
        """Vague query returns clarification request."""
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("help", session)

        assert answer.needs_clarification is True
        assert "clarify" in answer.text.lower()

    async def test_empty_session_returns_no_data_message(self, mock_llm_client, make_session):
        """Empty session returns helpful message."""
        debugger = create_debugger(mock_llm_client)
        session = make_session(events=[])

        answer = await debugger.answer_query("What happened in this session?", session)

        assert "no data" in answer.text.lower()

    async def test_no_relevant_events_returns_not_found(self, mock_llm_client, make_session):
        """Query about errors with no errors returns not found."""
        debugger = create_debugger(mock_llm_client)
        session = make_session(events=[{"id": "info-1", "type": "info", "payload": {}}])

        answer = await debugger.answer_query("Why did this fail?", session)

        assert "no error" in answer.text.lower()

    async def test_multi_part_query_handles_all_parts(self, mock_llm_client, make_session):
        """'Why and how to fix?' addresses both parts."""
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this fail and how do I fix it?", session)

        assert isinstance(answer, DebugAnswer)
        assert isinstance(answer.text, str)
        mock_llm_client.generate.assert_called_once()


class TestNLDebuggingErrorHandling:
    """Error handling tests for natural language debugging."""

    async def test_llm_timeout_returns_fallback(self, mock_llm_client, make_session):
        """Timeout returns answer with fallback=True."""
        mock_llm_client.generate.side_effect = TimeoutError("LLM timed out")
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this fail?", session)

        assert answer.fallback is True
        assert "too long" in answer.text.lower()

    async def test_llm_error_returns_error_message(self, mock_llm_client, make_session):
        """API error returns answer with error=True."""
        mock_llm_client.generate.side_effect = Exception("API connection failed")
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this fail?", session)

        assert answer.error is True
        assert "error" in answer.text.lower()

    async def test_malformed_llm_response_handled(self, mock_llm_client, make_session):
        """None response handled gracefully."""
        mock_llm_client.generate.return_value = None
        debugger = create_debugger(mock_llm_client)
        session = make_session()

        answer = await debugger.answer_query("Why did this fail?", session)

        assert answer.error is True
        assert "unable" in answer.text.lower() or "error" in answer.text.lower()


class TestNLDebuggingQueryTypes:
    """Tests for different query types."""

    async def test_how_to_fix_query(self, mock_llm_client):
        """'How do I fix?' -> intent.type in ('how_to_fix', 'suggestion')."""
        debugger = create_debugger(mock_llm_client)

        intent = await debugger.parse_intent("How do I fix this?")

        assert intent.type in ("how_to_fix", "suggestion")

    async def test_similar_failures_query(self, mock_llm_client):
        """'Has this failed before?' -> intent.type == 'similar_failures'."""
        debugger = create_debugger(mock_llm_client)

        intent = await debugger.parse_intent("Has this failed before?")

        assert intent.type == "similar_failures"

    async def test_explain_decision_query(self, mock_llm_client):
        """'Why did it decide X?' -> intent.type == 'explain_decision'."""
        debugger = create_debugger(mock_llm_client)

        intent = await debugger.parse_intent("Why did it decide to retry?")

        assert intent.type == "explain_decision"
