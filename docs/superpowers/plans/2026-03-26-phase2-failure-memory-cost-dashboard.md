# Phase 2: Failure Memory + Cost Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic failure memory search (find similar past sessions, annotate fixes) and cost visibility (per-session and aggregate cost dashboard) to the debugger.

**Architecture:** Two independent subsystems sharing no state. Failure Memory adds a `session_embeddings` table and `fix_notes` column to sessions, with cosine-similarity search. Cost Dashboard adds aggregation queries to the existing `sessions` table using `total_cost_usd` already tracked per session. Both expose new API routes and frontend components.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy (async), SQLite (default), React + TypeScript + Vite

---

## File Structure

### New files
- `storage/embedding.py` — text embedding helpers (bag-of-words, cosine similarity)
- `api/cost_routes.py` — cost aggregation API routes
- `api/search_routes.py` — failure memory search API routes
- `tests/test_cost_api.py` — cost endpoint tests
- `tests/test_search_api.py` — search endpoint tests
- `tests/test_embedding.py` — embedding utility tests
- `frontend/src/components/CostPanel.tsx` — per-session cost breakdown
- `frontend/src/components/CostSummary.tsx` — aggregate cost dashboard widget
- `frontend/src/components/SearchBar.tsx` — failure memory search input + results
- `frontend/src/components/FixAnnotation.tsx` — fix note editor on sessions

### Modified files
- `storage/models.py:20-48` — add `fix_note` column to `SessionModel`
- `storage/repository.py` — add `search_sessions()`, `add_fix_note()`, `get_cost_summary()` methods
- `api/main.py` — register new routers
- `api/schemas.py` — add cost and search response schemas
- `frontend/src/api/client.ts` — add `getCostSummary()`, `getSessionCost()`, `searchSessions()`, `addFixNote()` functions
- `frontend/src/types/index.ts` — add `CostSummary`, `SearchResult`, `FixNote` types
- `frontend/src/App.tsx` — integrate new components into layout

---

## Task 1: Embedding Utility

**Files:**
- Create: `storage/embedding.py`
- Test: `tests/test_embedding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embedding.py
"""Tests for text embedding and cosine similarity."""

import pytest

from storage.embedding import text_to_vector, cosine_similarity, tokenize


class TestTokenize:
    def test_lowercase_and_splits(self):
        tokens = tokenize("Tool Call: search_web")
        assert "tool" in tokens
        assert "call" in tokens
        assert "search_web" in tokens

    def test_empty_string(self):
        tokens = tokenize("")
        assert tokens == []

    def test_deduplicates(self):
        tokens = tokenize("error error error")
        assert tokens == ["error"]


class TestTextToVector:
    def test_known_output(self):
        vec = text_to_vector("error tool_call retry")
        # Same input always produces same output
        assert text_to_vector("error tool_call retry") == vec

    def test_empty_input(self):
        vec = text_to_vector("")
        assert vec == {}

    def test_single_term(self):
        vec = text_to_vector("error")
        assert vec == {"error": 1.0}

    def test_ignores_common_stopwords(self):
        vec = text_to_vector("the agent did a tool call")
        assert "the" not in vec
        assert "a" not in vec
        assert "did" not in vec
        assert "agent" in vec
        assert "tool" in vec
        assert "call" in vec


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = {"a": 1.0, "b": 2.0}
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity({"a": 1.0}, {"b": 1.0}) == pytest.approx(0.0)

    def test_empty_vectors(self):
        assert cosine_similarity({}, {}) == 0.0

    def test_one_empty_vector(self):
        assert cosine_similarity({"a": 1.0}, {}) == 0.0

    def test_similar_vectors(self):
        a = {"error": 1.0, "timeout": 1.0}
        b = {"error": 1.0, "timeout": 0.5, "retry": 0.5}
        sim = cosine_similarity(a, b)
        assert 0.5 < sim < 1.0


class TestBuildSessionEmbedding:
    def test_from_events(self):
        events = [
            {"event_type": "error", "name": "timeout", "data": {"error_type": "TimeoutError"}},
            {"event_type": "tool_call", "name": "search_web", "data": {}},
        ]
        embedding = text_to_vector("error timeout TimeoutError tool_call search_web")
        # build_session_embedding should produce the same kind of vector
        from storage.embedding import build_session_embedding
        result = build_session_embedding(events)
        assert isinstance(result, dict)
        # The event types and names should be in the embedding
        assert "error" in result
        assert "tool_call" in result

    def test_empty_events(self):
        from storage.embedding import build_session_embedding
        result = build_session_embedding([])
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_embedding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.embedding'`

- [ ] **Step 3: Write minimal implementation**

```python
# storage/embedding.py
"""Text embedding utilities for session similarity search.

Uses bag-of-words with TF-IDF-like normalization and cosine similarity.
No external dependencies — works with SQLite out of the box.
"""

from __future__ import annotations

import math
from typing import Any

# Stopwords to filter out for cleaner embeddings
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "and", "but", "or", "if", "it", "its",
    "this", "that", "these", "those", "he", "she", "we", "they", "me",
    "him", "her", "us", "them", "my", "your", "his", "our", "their",
    "what", "which", "who", "whom",
})


def tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, filtering stopwords and deduplicating."""
    raw = text.lower().split()
    seen: set[str] = set()
    tokens: list[str] = []
    for token in raw:
        cleaned = token.strip(".,;:!?()[]{}\"'").replace("_", " ")
        for part in cleaned.split():
            if part and part not in _STOPWORDS and part not in seen:
                seen.add(part)
                tokens.append(part)
    return tokens


def text_to_vector(text: str) -> dict[str, float]:
    """Convert text to a sparse bag-of-words vector with TF normalization.

    Args:
        text: Input text to embed

    Returns:
        Dict mapping terms to weights
    """
    tokens = tokenize(text)
    if not tokens:
        return {}
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = sum(tf.values())
    return {term: count / total for term, count in tf.items()}


def build_session_embedding(events: list[dict[str, Any]]) -> dict[str, float]:
    """Build an embedding vector from a list of event dicts.

    Concatenates event_type, name, error_type, error_message, and tool_name
    from each event to form a text representation, then embeds it.

    Args:
        events: List of event dicts with keys like event_type, name, data

    Returns:
        Sparse vector dict
    """
    parts: list[str] = []
    for ev in events:
        parts.append(str(ev.get("event_type", "")))
        parts.append(str(ev.get("name", "")))
        data = ev.get("data", {}) or {}
        if isinstance(data, dict):
            for key in ("error_type", "error_message", "tool_name"):
                if data.get(key):
                    parts.append(str(data[key]))
            for key in ("model", "tool"):
                if data.get(key):
                    parts.append(str(data[key]))
    combined = " ".join(parts)
    return text_to_vector(combined)


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors.

    Args:
        a: First sparse vector
        b: Second sparse vector

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not a or not b:
        return 0.0
    common_keys = set(a) & set(b)
    if not common_keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in common_keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_embedding.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/embedding.py tests/test_embedding.py
git commit -m "feat: add bag-of-words embedding utility for session similarity"
```

---

## Task 2: Session Fix Notes (DB + Repository)

**Files:**
- Modify: `storage/models.py:44` — add `fix_note` column to `SessionModel`
- Modify: `storage/repository.py` — add `add_fix_note()` and `update_session` valid fields
- Test: `tests/test_fix_notes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fix_notes.py
"""Tests for session fix note persistence."""

import pytest

from agent_debugger_sdk.core.events import Session, SessionStatus


@pytest.fixture
async def repo(db_session):
    from storage import TraceRepository
    return TraceRepository(db_session)


async def test_add_fix_note_to_session(repo):
    session = Session(
        id="sess-1",
        agent_name="test-agent",
        framework="pydantic-ai",
        status=SessionStatus.ERROR,
    )
    await repo.create_session(session)
    await repo.commit()

    updated = await repo.add_fix_note("sess-1", "Added retry timeout")
    assert updated is not None
    assert updated.fix_note == "Added retry timeout"

    # Verify it persists via get_session
    fetched = await repo.get_session("sess-1")
    assert fetched is not None
    assert fetched.fix_note == "Added retry timeout"


async def test_add_fix_note_nonexistent_session(repo):
    updated = await repo.add_fix_note("nonexistent", "some note")
    assert updated is None


async def test_update_fix_note_overwrites(repo):
    session = Session(
        id="sess-2",
        agent_name="test-agent",
        framework="pydantic-ai",
        status=SessionStatus.ERROR,
    )
    await repo.create_session(session)
    await repo.commit()

    await repo.add_fix_note("sess-2", "First fix")
    updated = await repo.add_fix_note("sess-2", "Better fix")
    assert updated.fix_note == "Better fix"


async def test_add_fix_note_scoped_to_tenant(repo):
    # Create session with default tenant
    session = Session(
        id="sess-3",
        agent_name="test-agent",
        framework="pydantic-ai",
        status=SessionStatus.ERROR,
    )
    await repo.create_session(session)
    await repo.commit()

    # Different tenant should not find it
    other_repo = repo.__class__(repo.session, tenant_id="other-tenant")
    updated = await other_repo.add_fix_note("sess-3", "sneaky")
    assert updated is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_fix_notes.py -v`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'fix_note'`

- [ ] **Step 3: Add fix_note to Session model**

Add the `fix_note` field to the Session dataclass. Check `agent_debugger_sdk/core/events/session.py`:

```python
# In agent_debugger_sdk/core/events/session.py, add fix_note field to the Session dataclass:
#    fix_note: str | None = None
```

Then add the column to the ORM model. In `storage/models.py`, after line 39 (`tags`), add:

```python
    fix_note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Make sure `Text` is imported at the top of `storage/models.py` (it should already be).

- [ ] **Step 4: Update repository — add valid field and add_fix_note method**

In `storage/repository.py`, add `"fix_note"` to the `valid_fields` set in `update_session()` (around line 160):

```python
    valid_fields = {
        "agent_name",
        "framework",
        "ended_at",
        "status",
        "total_tokens",
        "total_cost_usd",
        "tool_calls",
        "llm_calls",
        "errors",
        "replay_value",
        "config",
        "tags",
        "fix_note",
    }
```

Add the `add_fix_note` method to `TraceRepository` (before the anomaly alert section, around line 557):

```python
    async def add_fix_note(self, session_id: str, note: str) -> Session | None:
        """Add or update a fix note on a session.

        Args:
            session_id: Session to annotate
            note: Fix description text

        Returns:
            Updated Session if found, None otherwise
        """
        return await self.update_session(session_id, fix_note=note)
```

Also update `_orm_to_session` to include `fix_note`:

```python
    def _orm_to_session(self, db_session: SessionModel) -> Session:
        return Session(
            id=db_session.id,
            agent_name=db_session.agent_name,
            framework=db_session.framework,
            started_at=db_session.started_at,
            ended_at=db_session.ended_at,
            status=SessionStatus(db_session.status),
            total_tokens=db_session.total_tokens,
            total_cost_usd=db_session.total_cost_usd,
            tool_calls=db_session.tool_calls,
            llm_calls=db_session.llm_calls,
            errors=db_session.errors,
            replay_value=db_session.replay_value,
            config=db_session.config,
            tags=db_session.tags,
            fix_note=db_session.fix_note,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_fix_notes.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `python3 -m pytest -q`
Expected: All PASS (fix_note=None default is backward-compatible)

- [ ] **Step 7: Commit**

```bash
git add agent_debugger_sdk/core/events/session.py storage/models.py storage/repository.py tests/test_fix_notes.py
git commit -m "feat: add fix_note field to sessions for failure memory"
```

---

## Task 3: Session Search with Similarity (DB + Repository)

**Files:**
- Modify: `storage/repository.py` — add `search_sessions()` method
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_api.py
"""Tests for semantic session search."""

import pytest

from agent_debugger_sdk.core.events import Session, SessionStatus, TraceEvent, EventType


@pytest.fixture
async def repo(db_session):
    from storage import TraceRepository
    return TraceRepository(db_session)


async def _seed_session(repo, session_id: str, events_data: list[dict], status: SessionStatus = SessionStatus.ERROR):
    """Helper to create a session with events."""
    session = Session(
        id=session_id,
        agent_name="test-agent",
        framework="pydantic-ai",
        status=status,
    )
    await repo.create_session(session)
    for i, ev in enumerate(events_data):
        event = TraceEvent(
            id=f"{session_id}-evt-{i}",
            session_id=session_id,
            event_type=ev.get("event_type", EventType.ERROR),
            name=ev.get("name", ""),
            data=ev.get("data", {}),
            timestamp=ev.get("timestamp"),
        )
        await repo.add_event(event)
    await repo.commit()
    return session


async def test_search_finds_similar_sessions(repo):
    # Session A: timeout error
    await _seed_session(repo, "sess-a", [
        {"event_type": EventType.ERROR, "name": "timeout", "data": {"error_type": "TimeoutError"}, "timestamp": None},
        {"event_type": EventType.TOOL_CALL, "name": "search_web", "data": {}, "timestamp": None},
    ])
    # Session B: different error
    await _seed_session(repo, "sess-b", [
        {"event_type": EventType.ERROR, "name": "validation", "data": {"error_type": "ValueError"}, "timestamp": None},
    ])
    # Session C: same timeout error pattern
    await _seed_session(repo, "sess-c", [
        {"event_type": EventType.ERROR, "name": "timeout", "data": {"error_type": "TimeoutError"}, "timestamp": None},
    ])

    results = await repo.search_sessions("timeout error")
    session_ids = [r.id for r in results]

    # sess-a and sess-c should be in results (timeout errors)
    assert "sess-a" in session_ids
    assert "sess-c" in session_ids
    # sess-b should not be in top results (different error type)
    assert "sess-b" not in session_ids


async def test_search_returns_similarity_score(repo):
    await _seed_session(repo, "sess-x", [
        {"event_type": EventType.ERROR, "name": "timeout", "data": {"error_type": "TimeoutError"}, "timestamp": None},
    ])

    results = await repo.search_sessions("timeout error")
    assert len(results) > 0
    # Each result should have a similarity score
    assert hasattr(results[0], "search_similarity")
    assert 0.0 < results[0].search_similarity <= 1.0


async def test_search_empty_query(repo):
    results = await repo.search_sessions("")
    assert results == []


async def test_search_no_sessions(repo):
    results = await repo.search_sessions("timeout")
    assert results == []


async def test_search_respects_limit(repo):
    for i in range(5):
        await _seed_session(repo, f"sess-{i}", [
            {"event_type": EventType.ERROR, "name": "timeout", "data": {"error_type": "TimeoutError"}, "timestamp": None},
        ])

    results = await repo.search_sessions("timeout", limit=2)
    assert len(results) <= 2


async def test_search_filters_by_status(repo):
    await _seed_session(repo, "err-1", [
        {"event_type": EventType.ERROR, "name": "timeout", "data": {"error_type": "TimeoutError"}, "timestamp": None},
    ])
    await _seed_session(repo, "ok-1", [
        {"event_type": EventType.TOOL_CALL, "name": "search_web", "data": {}, "timestamp": None},
    ], status=SessionStatus.COMPLETED)

    results = await repo.search_sessions("timeout", status="error")
    session_ids = [r.id for r in results]
    assert "err-1" in session_ids
    assert "ok-1" not in session_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_search_api.py -v`
Expected: FAIL — `AttributeError: 'TraceRepository' object has no attribute 'search_sessions'`

- [ ] **Step 3: Write the implementation**

Add `search_sessions` method to `TraceRepository` in `storage/repository.py` (before the anomaly alert section):

```python
    async def search_sessions(
        self,
        query: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Session]:
        """Search sessions by semantic similarity to a text query.

        Builds a bag-of-words embedding from the query, computes similarity
        against all sessions' event embeddings, and returns the top matches.

        Args:
            query: Natural language search text
            status: Optional session status filter
            limit: Maximum number of results

        Returns:
            List of Session instances with search_similarity attribute
        """
        from storage.embedding import build_session_embedding, cosine_similarity, text_to_vector

        if not query or not query.strip():
            return []

        query_vec = text_to_vector(query)
        if not query_vec:
            return []

        # Fetch candidate sessions with their events
        stmt = select(SessionModel).where(SessionModel.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(SessionModel.status == status)

        result = await self.session.execute(stmt)
        db_sessions = list(result.scalars().all())

        if not db_sessions:
            return []

        # Build similarity scores
        scored: list[tuple[float, SessionModel]] = []
        for db_sess in db_sessions:
            # Fetch events for this session
            ev_result = await self.session.execute(
                select(EventModel).where(EventModel.session_id == db_sess.id)
            )
            db_events = list(ev_result.scalars().all())

            # Build session embedding from event data
            event_dicts = [
                {"event_type": e.event_type, "name": e.name, "data": e.data or {}}
                for e in db_events
            ]
            session_vec = build_session_embedding(event_dicts)

            sim = cosine_similarity(query_vec, session_vec)
            if sim > 0.0:
                scored.append((sim, db_sess))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Convert to Session dataclasses, attaching similarity score
        results: list[Session] = []
        for sim, db_sess in scored[:limit]:
            session = self._orm_to_session(db_sess)
            session.search_similarity = sim  # type: ignore[attr-defined]
            results.append(session)

        return results
```

Also add a `search_similarity` optional attribute to the Session dataclass. In `agent_debugger_sdk/core/events/session.py`:

```python
# Add to Session dataclass:
#    search_similarity: float | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_search_api.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `python3 -m pytest -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add storage/repository.py agent_debugger_sdk/core/events/session.py tests/test_search_api.py
git commit -m "feat: add semantic session search with cosine similarity"
```

---

## Task 4: Cost Summary Repository Methods

**Files:**
- Modify: `storage/repository.py` — add `get_session_cost()` and `get_cost_summary()`
- Test: `tests/test_cost_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cost_api.py
"""Tests for cost aggregation queries."""

import pytest

from agent_debugger_sdk.core.events import Session, SessionStatus


@pytest.fixture
async def repo(db_session):
    from storage import TraceRepository
    return TraceRepository(db_session)


async def _make_session(repo, session_id: str, cost: float, agent: str = "test-agent"):
    session = Session(
        id=session_id,
        agent_name=agent,
        framework="pydantic-ai",
        status=SessionStatus.COMPLETED,
        total_cost_usd=cost,
        total_tokens=1000,
        tool_calls=5,
        llm_calls=3,
        ended_at="2026-03-26T12:00:00",
    )
    await repo.create_session(session)
    return session


async def test_get_cost_summary(repo):
    await _make_session(repo, "s1", 0.50)
    await _make_session(repo, "s2", 1.25)
    await _make_session(repo, "s3", 0.10)
    await repo.commit()

    summary = await repo.get_cost_summary()
    assert summary["total_cost_usd"] == pytest.approx(1.85)
    assert summary["session_count"] == 3
    assert summary["avg_cost_per_session"] == pytest.approx(1.85 / 3)


async def test_get_cost_summary_empty(repo):
    summary = await repo.get_cost_summary()
    assert summary["total_cost_usd"] == 0.0
    assert summary["session_count"] == 0


async def test_get_cost_summary_by_framework(repo):
    await _make_session(repo, "s1", 0.50, agent="agent-a")
    await _make_session(repo, "s2", 1.00, agent="agent-a")
    await _make_session(repo, "s3", 2.00, agent="agent-b")
    await repo.commit()

    summary = await repo.get_cost_summary()
    # Should have per-framework breakdown
    assert "by_framework" in summary
    assert len(summary["by_framework"]) == 2


async def test_get_session_cost_breakdown(repo):
    """Per-session cost is already on the session model."""
    await _make_session(repo, "s1", 0.75)
    await repo.commit()

    session = await repo.get_session("s1")
    assert session.total_cost_usd == 0.75
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cost_api.py -v`
Expected: FAIL — `AttributeError: 'TraceRepository' object has no attribute 'get_cost_summary'`

- [ ] **Step 3: Write the implementation**

Add `get_cost_summary` to `TraceRepository` in `storage/repository.py`:

```python
    async def get_cost_summary(self) -> dict:
        """Get aggregate cost statistics across all sessions.

        Returns:
            Dict with total_cost_usd, session_count, avg_cost_per_session,
            and by_framework breakdown
        """
        # Total cost and count
        result = await self.session.execute(
            select(
                func.count(SessionModel.id).label("session_count"),
                func.sum(SessionModel.total_cost_usd).label("total_cost"),
            )
            .where(SessionModel.tenant_id == self.tenant_id)
        )
        row = result.one()
        session_count = row.session_count or 0
        total_cost = float(row.total_cost or 0)

        # Per-framework breakdown
        fw_result = await self.session.execute(
            select(
                SessionModel.framework,
                func.count(SessionModel.id).label("count"),
                func.sum(SessionModel.total_cost_usd).label("total"),
            )
            .where(SessionModel.tenant_id == self.tenant_id)
            .group_by(SessionModel.framework)
        )
        by_framework = [
            {"framework": fw, "session_count": cnt, "total_cost_usd": float(tot or 0)}
            for fw, cnt, tot in fw_result.all()
        ]

        return {
            "total_cost_usd": round(total_cost, 6),
            "session_count": session_count,
            "avg_cost_per_session": round(total_cost / session_count, 6) if session_count else 0.0,
            "by_framework": by_framework,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cost_api.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add storage/repository.py tests/test_cost_api.py
git commit -m "feat: add cost summary aggregation queries"
```

---

## Task 5: Search and Cost API Routes

**Files:**
- Create: `api/search_routes.py`
- Create: `api/cost_routes.py`
- Modify: `api/schemas.py` — add response schemas
- Modify: `api/main.py` — register routers

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cost_routes.py
"""Tests for cost API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from agent_debugger_sdk.core.events import Session, SessionStatus
from api.main import app
from storage.models import Base
from api import app_context


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app_context.init_app_context(_engine=engine, _session_maker=session_maker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


@pytest.fixture
async def seeded(client):
    """Seed some sessions via the collector API."""
    import asyncio
    from storage import TraceRepository

    async with app_context.require_session_maker()() as db:
        repo = TraceRepository(db)
        for i, (cost, status) in enumerate([
            (0.50, SessionStatus.COMPLETED),
            (1.25, SessionStatus.COMPLETED),
            (0.10, SessionStatus.ERROR),
        ]):
            s = Session(
                id=f"cost-test-{i}",
                agent_name="test-agent",
                framework="pydantic-ai",
                status=status,
                total_cost_usd=cost,
                total_tokens=1000,
                ended_at="2026-03-26T12:00:00",
            )
            await repo.create_session(s)
        await repo.commit()
    return client


async def test_get_cost_summary(seeded):
    resp = await seeded.get("/api/cost/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost_usd"] == pytest.approx(1.85)
    assert data["session_count"] == 3


async def test_get_cost_summary_empty(client):
    resp = await client.get("/api/cost/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost_usd"] == 0.0
    assert data["session_count"] == 0


async def test_get_session_cost(seeded):
    resp = await seeded.get("/api/cost/sessions/cost-test-0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost_usd"] == 0.50


async def test_get_session_cost_not_found(client):
    resp = await client.get("/api/cost/sessions/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cost_routes.py -v`
Expected: FAIL — `404 Not Found` (routes not registered)

- [ ] **Step 3: Create cost routes**

```python
# api/cost_routes.py
"""Cost aggregation API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.app_context import require_session_maker
from storage import TraceRepository

router = APIRouter(tags=["cost"])


class CostSummaryResponse(BaseModel):
    total_cost_usd: float = Field(..., description="Total cost across all sessions in USD")
    session_count: int = Field(..., description="Number of sessions")
    avg_cost_per_session: float = Field(..., description="Average cost per session")
    by_framework: list[dict] = Field(default_factory=list, description="Cost breakdown by framework")


class SessionCostResponse(BaseModel):
    session_id: str
    total_cost_usd: float
    total_tokens: int
    llm_calls: int
    tool_calls: int


@router.get("/api/cost/summary", response_model=CostSummaryResponse)
async def get_cost_summary() -> CostSummaryResponse:
    """Get aggregate cost statistics across all sessions."""
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        summary = await repo.get_cost_summary()
    return CostSummaryResponse(**summary)


@router.get("/api/cost/sessions/{session_id}", response_model=SessionCostResponse)
async def get_session_cost(session_id: str) -> SessionCostResponse:
    """Get cost breakdown for a specific session."""
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return SessionCostResponse(
        session_id=session.id,
        total_cost_usd=session.total_cost_usd,
        total_tokens=session.total_tokens,
        llm_calls=session.llm_calls,
        tool_calls=session.tool_calls,
    )
```

- [ ] **Step 4: Create search routes**

```python
# api/search_routes.py
"""Failure memory search API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.app_context import require_session_maker
from storage import TraceRepository

router = APIRouter(tags=["search"])


class SearchResult(BaseModel):
    session_id: str
    agent_name: str
    framework: str
    status: str
    total_cost_usd: float
    started_at: str
    ended_at: str | None
    errors: int
    fix_note: str | None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


class FixNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000, description="Fix description")


class FixNoteResponse(BaseModel):
    session_id: str
    fix_note: str


@router.get("/api/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=2, description="Search query"),
    status: str | None = Query(default=None, description="Filter by session status"),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    """Search sessions by semantic similarity.

    Finds sessions with events matching the query text.
    Returns sessions ranked by similarity score.
    """
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        sessions = await repo.search_sessions(q, status=status, limit=limit)

    results = [
        SearchResult(
            session_id=s.id,
            agent_name=s.agent_name or "",
            framework=s.framework or "",
            status=str(s.status),
            total_cost_usd=s.total_cost_usd,
            started_at=s.started_at.isoformat() if s.started_at else "",
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            errors=s.errors,
            fix_note=s.fix_note,
            similarity=getattr(s, "search_similarity", 0.0),
        )
        for s in sessions
    ]

    return SearchResponse(query=q, total=len(results), results=results)


@router.post("/api/sessions/{session_id}/fix-note", response_model=FixNoteResponse)
async def add_fix_note(session_id: str, body: FixNoteRequest) -> FixNoteResponse:
    """Add or update a fix note on a session."""
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        session = await repo.add_fix_note(session_id, body.note)
        await db_session.commit()
    if session is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return FixNoteResponse(session_id=session_id, fix_note=body.note)
```

- [ ] **Step 5: Register routers in main.py**

In `api/main.py`, add imports and register:

```python
from api.cost_routes import router as cost_router
from api.search_routes import router as search_router
```

And in `create_app()`, add:

```python
    app.include_router(cost_router)
    app.include_router(search_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cost_routes.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `python3 -m pytest -q`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add api/cost_routes.py api/search_routes.py api/main.py tests/test_cost_routes.py
git commit -m "feat: add cost and search API routes"
```

---

## Task 6: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add TypeScript types**

Add to the end of `frontend/src/types/index.ts`:

```typescript
// Cost Dashboard types
export interface CostSummary {
  total_cost_usd: number
  session_count: number
  avg_cost_per_session: number
  by_framework: Array<{
    framework: string
    session_count: number
    total_cost_usd: number
  }>
}

export interface SessionCost {
  session_id: string
  total_cost_usd: number
  total_tokens: number
  llm_calls: number
  tool_calls: number
}

// Failure Memory Search types
export interface SearchResult {
  session_id: string
  agent_name: string
  framework: string
  status: string
  total_cost_usd: number
  started_at: string
  ended_at: string | null
  errors: number
  fix_note: string | null
  similarity: number
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResult[]
}

export interface FixNoteResponse {
  session_id: string
  fix_note: string
}
```

- [ ] **Step 2: Add API client functions**

Add to the end of `frontend/src/api/client.ts`:

```typescript
// Cost Dashboard API
export async function getCostSummary() {
  return fetchJSON<CostSummary>(`${API_BASE}/cost/summary`)
}

export async function getSessionCost(sessionId: string) {
  return fetchJSON<SessionCost>(`${API_BASE}/cost/sessions/${sessionId}`)
}

// Failure Memory Search API
export async function searchSessions(params: {
  q: string
  status?: string | null
  limit?: number
}) {
  const search = new URLSearchParams()
  search.set('q', params.q)
  if (params.status) search.set('status', params.status)
  if (params.limit) search.set('limit', String(params.limit))
  return fetchJSON<SearchResponse>(`${API_BASE}/search?${search.toString()}`)
}

export async function addFixNote(sessionId: string, note: string) {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/fix-note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<FixNoteResponse>
}
```

Also add the new type imports to the import block at the top of `client.ts`:

```typescript
import type {
  // ... existing imports ...
  CostSummary,
  SessionCost,
  SearchResponse,
  FixNoteResponse,
} from '../types'
```

- [ ] **Step 3: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add cost and search types and API client functions"
```

---

## Task 7: CostSummary Widget Component

**Files:**
- Create: `frontend/src/components/CostSummary.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/CostSummary.tsx
import { useEffect, useState } from 'react'
import { getCostSummary } from '../api/client'
import type { CostSummary as CostSummaryType } from '../types'

export default function CostSummary() {
  const [data, setData] = useState<CostSummaryType | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCostSummary()
      .then(setData)
      .catch(err => setError(err.message))
  }, [])

  if (error) return <div className="cost-summary-error">Failed to load cost data</div>
  if (!data) return <div className="cost-summary-loading">Loading cost data...</div>

  return (
    <div className="cost-summary">
      <h3>Cost Overview</h3>
      <div className="cost-summary-grid">
        <div className="cost-stat">
          <span className="cost-label">Total Spend</span>
          <span className="cost-value">${data.total_cost_usd.toFixed(4)}</span>
        </div>
        <div className="cost-stat">
          <span className="cost-label">Sessions</span>
          <span className="cost-value">{data.session_count}</span>
        </div>
        <div className="cost-stat">
          <span className="cost-label">Avg / Session</span>
          <span className="cost-value">${data.avg_cost_per_session.toFixed(4)}</span>
        </div>
      </div>
      {data.by_framework.length > 0 && (
        <div className="cost-by-framework">
          <h4>By Framework</h4>
          <table>
            <thead>
              <tr>
                <th>Framework</th>
                <th>Sessions</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.by_framework.map(fw => (
                <tr key={fw.framework}>
                  <td>{fw.framework}</td>
                  <td>{fw.session_count}</td>
                  <td>${fw.total_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CostSummary.tsx
git commit -m "feat: add CostSummary widget component"
```

---

## Task 8: CostPanel Component (Per-Session)

**Files:**
- Create: `frontend/src/components/CostPanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/CostPanel.tsx
import { useEffect, useState } from 'react'
import { getSessionCost } from '../api/client'
import type { SessionCost } from '../types'

interface CostPanelProps {
  sessionId: string
}

export default function CostPanel({ sessionId }: CostPanelProps) {
  const [data, setData] = useState<SessionCost | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    getSessionCost(sessionId)
      .then(setData)
      .catch(err => setError(err.message))
  }, [sessionId])

  if (error) return null
  if (!data) return null

  return (
    <div className="cost-panel">
      <h4>Session Cost</h4>
      <div className="cost-details">
        <div className="cost-row">
          <span>Total Cost</span>
          <span className="cost-amount">${data.total_cost_usd.toFixed(6)}</span>
        </div>
        <div className="cost-row">
          <span>Tokens</span>
          <span>{data.total_tokens.toLocaleString()}</span>
        </div>
        <div className="cost-row">
          <span>LLM Calls</span>
          <span>{data.llm_calls}</span>
        </div>
        <div className="cost-row">
          <span>Tool Calls</span>
          <span>{data.tool_calls}</span>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CostPanel.tsx
git commit -m "feat: add per-session CostPanel component"
```

---

## Task 9: SearchBar Component

**Files:**
- Create: `frontend/src/components/SearchBar.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/SearchBar.tsx
import { useCallback, useRef, useState } from 'react'
import { searchSessions } from '../api/client'
import type { SearchResult } from '../types'

interface SearchBarProps {
  onSelectSession: (sessionId: string) => void
}

export default function SearchBar({ onSelectSession }: SearchBarProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  const containerRef = useRef<HTMLDivElement>(null)

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([])
      return
    }
    setIsSearching(true)
    try {
      const resp = await searchSessions({ q, limit: 10 })
      setResults(resp.results)
    } catch {
      setResults([])
    } finally {
      setIsSearching(false)
    }
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(value), 300)
  }

  const handleSelect = (sessionId: string) => {
    setResults([])
    setQuery('')
    onSelectSession(sessionId)
  }

  const formatPercent = (n: number) => `${Math.round(n * 100)}%`

  return (
    <div className="search-bar" ref={containerRef}>
      <input
        type="text"
        className="search-input"
        placeholder="Search past failures..."
        value={query}
        onChange={handleChange}
      />
      {isSearching && <span className="search-loading">Searching...</span>}
      {results.length > 0 && (
        <div className="search-results">
          {results.map(r => (
            <button
              key={r.session_id}
              className="search-result-item"
              onClick={() => handleSelect(r.session_id)}
            >
              <div className="search-result-header">
                <span className="search-result-agent">{r.agent_name}</span>
                <span className="search-result-similarity">{formatPercent(r.similarity)} match</span>
              </div>
              <div className="search-result-meta">
                <span className={`search-result-status status-${r.status}`}>{r.status}</span>
                <span>{r.errors} errors</span>
                <span>${r.total_cost_usd.toFixed(4)}</span>
                <span>{new Date(r.started_at).toLocaleDateString()}</span>
              </div>
              {r.fix_note && (
                <div className="search-result-fix">Fix: {r.fix_note}</div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SearchBar.tsx
git commit -m "feat: add SearchBar component for failure memory"
```

---

## Task 10: FixAnnotation Component

**Files:**
- Create: `frontend/src/components/FixAnnotation.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/FixAnnotation.tsx
import { useState } from 'react'
import { addFixNote } from '../api/client'

interface FixAnnotationProps {
  sessionId: string
  existingNote: string | null
}

export default function FixAnnotation({ sessionId, existingNote }: FixAnnotationProps) {
  const [note, setNote] = useState(existingNote || '')
  const [isSaving, setIsSaving] = useState(false)
  const [isEditing, setIsEditing] = useState(!existingNote)

  const handleSave = async () => {
    if (!note.trim()) return
    setIsSaving(true)
    try {
      await addFixNote(sessionId, note.trim())
      setIsEditing(false)
    } catch {
      // Silently fail — fix notes are optional
    } finally {
      setIsSaving(false)
    }
  }

  if (!isEditing && existingNote) {
    return (
      <div className="fix-annotation">
        <span className="fix-label">Fix:</span>
        <span className="fix-text">{existingNote}</span>
        <button className="fix-edit-btn" onClick={() => setIsEditing(true)}>Edit</button>
      </div>
    )
  }

  return (
    <div className="fix-annotation">
      <input
        type="text"
        className="fix-input"
        placeholder="How did you fix this?"
        value={note}
        onChange={e => setNote(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') handleSave() }}
      />
      <button className="fix-save-btn" onClick={handleSave} disabled={isSaving || !note.trim()}>
        {isSaving ? 'Saving...' : 'Save'}
      </button>
      {existingNote && (
        <button className="fix-cancel-btn" onClick={() => { setNote(existingNote); setIsEditing(false) }}>
          Cancel
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FixAnnotation.tsx
git commit -m "feat: add FixAnnotation component"
```

---

## Task 11: Wire Components into App Layout

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Integrate components**

Read `frontend/src/App.tsx` to understand current layout, then add:

1. Import the new components at the top
2. Add `CostSummary` widget to the analytics view
3. Add `SearchBar` to the main layout (visible from both views)
4. Add `CostPanel` to the session detail view
5. Add `FixAnnotation` to the session detail view (below session metadata)

The exact integration points depend on the current App.tsx structure. Key additions:

```tsx
import CostSummary from './components/CostSummary'
import CostPanel from './components/CostPanel'
import SearchBar from './components/SearchBar'
import FixAnnotation from './components/FixAnnotation'
```

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Run full backend tests**

Run: `python3 -m pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: integrate cost and search components into app layout"
```

---

## Task 12: Add CSS Styles

**Files:**
- Modify: `frontend/src/App.css`

- [ ] **Step 1: Add styles for new components**

Add CSS for `.cost-summary`, `.cost-panel`, `.search-bar`, `.fix-annotation` classes. Keep styles minimal and consistent with existing patterns in `App.css`.

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.css
git commit -m "feat: add CSS styles for cost and search components"
```

---

## Task 13: Final Validation

- [ ] **Step 1: Run full backend test suite**

Run: `python3 -m pytest -q`
Expected: All PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Run linter**

Run: `ruff check .`
Expected: No errors

- [ ] **Step 4: Final commit (if any cleanup needed)**

Run: `git status --short` to check for uncommitted changes.
