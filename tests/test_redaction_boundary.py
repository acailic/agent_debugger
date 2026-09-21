"""One redaction policy across every sink (roadmap W10 / queue item Q08).

Boundary tests with synthetic sentinel markers. A single configured
pipeline (prompts + tool payloads + PII/secret scrub, one instance) must
govern every sink an event, session config, or checkpoint can reach:

- persisted DB rows (events, event metadata, session config, checkpoint
  state/memory),
- the live buffer and the SSE fan-out built on it,
- and (for the in-process path) the object the SDK emitter publishes
  concurrently with persistence.

Markers must be ABSENT from every sink above; structural ids and
policy-permitted values must SURVIVE. Documented exception: original
in-memory objects that the caller keeps outside the persist/stream path
(e.g. the live ``Session.config`` of a running agent, or a local dict the
test built the request from) may stay unredacted — only the stored and
streamed copies are scrubbed.
"""

from __future__ import annotations

import asyncio
import uuid
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import collector.server as collector_server
from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from api.services.ingestion import (
    event_generator,
    persist_checkpoint,
    persist_event,
    persist_session_start,
    persist_session_update,
)
from collector.buffer import EventBuffer
from collector.server import CollectorDependencies, TraceEventIngest
from redaction.pipeline import RedactionPipeline, apply_payload_redaction
from storage import Base, TraceRepository
from tests.helpers.fakes import FakeEventBuffer

# --------------------------------------------------------------------------
# Synthetic sentinel markers
# --------------------------------------------------------------------------

MARKER_EMAIL = "boundary.user+tag@example.org"
MARKER_AWS_KEY = "AKIABOUNDARYTESTKEY1"
MARKER_API_KEY = "api_key=SUPERSECRETBOUNDARY123"
MARKER_SENTINEL = "SENTINEL-SECRET-8642"

ALL_MARKERS = (MARKER_EMAIL, MARKER_AWS_KEY, MARKER_API_KEY, MARKER_SENTINEL)


def _uid(prefix: str) -> str:
    """Unique id per seeding; the shared test DB persists across a run."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _mock_scorer():
    return SimpleNamespace(score=MagicMock(return_value=0.5))


def _fake_request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))


def _full_policy() -> RedactionPipeline:
    """The single configured policy used across every sink in these tests."""
    return RedactionPipeline(
        redact_prompts=True,
        redact_tool_payloads=True,
        redact_pii=True,
        max_payload_kb=0,
    )


def _assert_markers_absent(blob: object, where: str) -> None:
    text = repr(blob)
    for marker in ALL_MARKERS:
        assert marker not in text, f"{marker} leaked into {where}: {text[:500]}"


@pytest.fixture
def boundary_db(tmp_path):
    """Isolated sqlite database with schema + session maker."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'boundary.db'}")

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    asyncio.run(engine.dispose())


async def _seed_session(maker, session_id: str, tenant_id: str = "local") -> None:
    async with maker() as db:
        repo = TraceRepository(db, tenant_id=tenant_id)
        await repo.create_session(
            Session(id=session_id, agent_name="boundary-agent", framework="pytest")
        )
        await repo.commit()


# --------------------------------------------------------------------------
# Pipeline boundary: metadata joins the scrub path; structure survives
# --------------------------------------------------------------------------


class TestPipelineBoundary:
    def test_event_metadata_is_scrubbed(self):
        pipeline = _full_policy()
        event = TraceEvent(
            session_id="boundary-meta",
            event_type=EventType.TOOL_CALL,
            name="tool_call",
            data={"tool_name": "search"},
            metadata={"contact": MARKER_EMAIL, "nested": {"creds": MARKER_AWS_KEY}},
        )

        redacted = pipeline.apply(event)

        assert MARKER_EMAIL not in repr(redacted.metadata)
        assert MARKER_AWS_KEY not in repr(redacted.metadata)
        assert "[EMAIL]" in redacted.metadata["contact"]
        assert "[AWS_ACCESS_KEY]" in redacted.metadata["nested"]["creds"]

    def test_structural_fields_survive_full_policy(self):
        pipeline = _full_policy()
        event_id = _uid("evt")
        session_id = _uid("ses")
        event = TraceEvent(
            id=event_id,
            session_id=session_id,
            event_type=EventType.LLM_RESPONSE,
            name="llm_boundary",
            data={"content": MARKER_SENTINEL, "model": "gpt-4-boundary"},
            metadata={"note": MARKER_EMAIL},
        )

        redacted = pipeline.apply(event)

        assert redacted.id == event_id
        assert redacted.session_id == session_id
        assert redacted.name == "llm_boundary"
        assert redacted.data["model"] == "gpt-4-boundary"  # permitted value survives
        assert redacted.data["content"] == "[REDACTED]"

    def test_scrub_payload_reuses_the_same_policy(self):
        pipeline = _full_policy()
        payload = {
            "notify": MARKER_EMAIL,
            "credentials": MARKER_AWS_KEY,
            "setting": MARKER_API_KEY,
            "stage": "transformed",
            "aggregates": 84,
        }

        scrubbed = pipeline.scrub_payload(payload)

        assert "[EMAIL]" in scrubbed["notify"]
        assert "[AWS_ACCESS_KEY]" in scrubbed["credentials"]
        assert "[API_KEY]" in scrubbed["setting"]
        assert scrubbed["stage"] == "transformed"
        assert scrubbed["aggregates"] == 84

    def test_apply_payload_redaction_passes_through_apply_only_doubles(self):
        """Duck-typed apply-only pipelines are event-only policies.

        Payload scrubbing never adds ``apply()`` calls for such doubles —
        only a real pipeline (with ``scrub_payload``) scrubs non-event
        payloads, so injecting a test double never widens the policy.
        """
        apply_calls: list[TraceEvent] = []

        class ApplyOnlyPipeline:
            def apply(self, event: TraceEvent) -> TraceEvent:
                apply_calls.append(event)
                return event

        payload = {"mode": "test"}
        scrubbed = apply_payload_redaction(ApplyOnlyPipeline(), payload)

        assert scrubbed == {"mode": "test"}
        assert apply_calls == []
        scrubbed["mode"] = "mutated"
        assert payload["mode"] == "test"  # returned payload is a copy


class TestFromConfigWiring:
    def test_defaults_keep_optional_flags_off(self, monkeypatch):
        monkeypatch.delenv("AGENT_DEBUGGER_REDACT_PII", raising=False)
        monkeypatch.delenv("AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS", raising=False)

        pipeline = RedactionPipeline.from_config()

        assert pipeline.redact_pii is False
        assert pipeline.redact_tool_payloads is False

    def test_env_toggles_turn_the_policy_on(self, monkeypatch):
        monkeypatch.setenv("AGENT_DEBUGGER_REDACT_PII", "1")
        monkeypatch.setenv("AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS", "true")

        pipeline = RedactionPipeline.from_config()

        assert pipeline.redact_pii is True
        assert pipeline.redact_tool_payloads is True

    def test_config_fields_take_precedence_when_present(self, monkeypatch):
        monkeypatch.delenv("AGENT_DEBUGGER_REDACT_PII", raising=False)
        monkeypatch.delenv("AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS", raising=False)
        fake_config = SimpleNamespace(
            redact_prompts=True,
            max_payload_kb=16,
            redact_pii=True,
            redact_tool_payloads=True,
        )

        import agent_debugger_sdk.config as cfg_mod

        original = cfg_mod.get_config
        cfg_mod.get_config = lambda: fake_config
        try:
            pipeline = RedactionPipeline.from_config()
        finally:
            cfg_mod.get_config = original

        assert pipeline.redact_prompts is True
        assert pipeline.redact_pii is True
        assert pipeline.redact_tool_payloads is True
        assert pipeline.max_payload_kb == 16


# --------------------------------------------------------------------------
# Collector HTTP path: stored row, buffer, session config, checkpoint
# --------------------------------------------------------------------------


class TestCollectorHttpBoundary:
    @pytest.mark.asyncio
    async def test_stored_and_streamed_events_are_equally_redacted(self, boundary_db):
        session_id = _uid("ses")
        event_id = _uid("evt")
        await _seed_session(boundary_db, session_id, tenant_id="tenant-red")

        pipeline = _full_policy()
        buffer = FakeEventBuffer()
        deps = CollectorDependencies(
            session_maker=boundary_db,
            buffer=buffer,
            scorer=_mock_scorer(),
            tenant_resolver=AsyncMock(return_value="tenant-red"),
            redaction_pipeline_factory=lambda: pipeline,
        )
        ingest = TraceEventIngest(
            session_id=session_id,
            id=event_id,
            event_type="llm_response",
            name="llm_boundary",
            data={"content": f"reply to {MARKER_EMAIL} says {MARKER_SENTINEL}", "model": "gpt-4-boundary"},
            metadata={"contact": MARKER_EMAIL, "creds": MARKER_AWS_KEY},
        )

        response = await collector_server._ingest_trace(
            ingest, request=_fake_request(), dependencies=deps
        )

        assert response.event_id == event_id  # structural id survives

        # Streamed (buffer) copy is redacted.
        streamed = await buffer.get_events(session_id)
        assert len(streamed) == 1
        _assert_markers_absent(streamed[0].to_dict(), "live buffer / SSE fan-out")
        assert streamed[0].content == "[REDACTED]"
        assert streamed[0].model == "gpt-4-boundary"
        assert "[EMAIL]" in streamed[0].metadata["contact"]

        # Stored copy is redacted identically.
        async with boundary_db() as db:
            repo = TraceRepository(db, tenant_id="tenant-red")
            stored = await repo.list_events(session_id)
        assert len(stored) == 1
        _assert_markers_absent(stored[0].to_dict(), "persisted event row")
        _assert_markers_absent(stored[0].metadata, "persisted event metadata column")
        assert stored[0].id == event_id
        assert stored[0].session_id == session_id
        assert stored[0].model == "gpt-4-boundary"

    @pytest.mark.asyncio
    async def test_session_config_is_redacted_on_create(self, boundary_db):
        pipeline = _full_policy()
        deps = CollectorDependencies(
            session_maker=boundary_db,
            buffer=FakeEventBuffer(),
            scorer=_mock_scorer(),
            tenant_resolver=AsyncMock(return_value="tenant-red"),
            redaction_pipeline_factory=lambda: pipeline,
        )
        session_id = _uid("ses")
        config = {
            "notify": MARKER_EMAIL,
            "credentials": MARKER_AWS_KEY,
            "setting": MARKER_API_KEY,
            "retries": 3,
        }

        created = await collector_server._create_session(
            collector_server.SessionCreate(
                id=session_id,
                agent_name="boundary-agent",
                framework="pytest",
                config=config,
                tags=["boundary"],
            ),
            request=_fake_request(),
            dependencies=deps,
        )

        assert created.id == session_id  # structural id survives

        async with boundary_db() as db:
            repo = TraceRepository(db, tenant_id="tenant-red")
            stored = await repo.get_session(session_id)

        assert stored is not None
        _assert_markers_absent(stored.config, "persisted session config")
        assert "[EMAIL]" in stored.config["notify"]
        assert stored.config["retries"] == 3
        assert stored.agent_name == "boundary-agent"
        # Local, in-memory request payload is the documented exception.
        assert MARKER_EMAIL in config["notify"]

    @pytest.mark.asyncio
    async def test_checkpoint_state_and_memory_are_redacted(self, boundary_db, monkeypatch):
        session_id = _uid("ses")
        await _seed_session(boundary_db, session_id, tenant_id="tenant-red")
        # Consistent anchor event: checkpoint event references must resolve
        # to an event of the checkpoint's own session.
        anchor_id = _uid("evt")
        async with boundary_db() as db:
            repo = TraceRepository(db, tenant_id="tenant-red")
            await repo.add_event(
                TraceEvent(
                    id=anchor_id,
                    session_id=session_id,
                    event_type=EventType.TOOL_CALL,
                    name="boundary_anchor",
                )
            )
            await repo.commit()
        monkeypatch.setattr(collector_server, "_session_maker", boundary_db)
        monkeypatch.setattr(
            collector_server, "_get_redaction_pipeline", lambda: _full_policy()
        )
        monkeypatch.setattr(
            collector_server, "_get_tenant_id", AsyncMock(return_value="tenant-red")
        )
        checkpoint_id = _uid("cp")

        result = await collector_server.ingest_checkpoint(
            collector_server.CheckpointIngest(
                id=checkpoint_id,
                session_id=session_id,
                event_id=anchor_id,
                sequence=7,
                state={
                    "stage": "transformed",
                    "contact": MARKER_EMAIL,
                    "credentials": MARKER_AWS_KEY,
                    "setting": MARKER_API_KEY,
                    "aggregates": 84,
                },
                memory={"last_table": "revenue_daily", "note": f"use {MARKER_EMAIL}"},
            ),
            request=_fake_request(),
        )

        assert result["checkpoint_id"] == checkpoint_id  # structural id survives

        async with boundary_db() as db:
            repo = TraceRepository(db, tenant_id="tenant-red")
            checkpoints = await repo.list_checkpoints(session_id)

        assert len(checkpoints) == 1
        stored = checkpoints[0]
        _assert_markers_absent(stored.state, "persisted checkpoint state")
        _assert_markers_absent(stored.memory, "persisted checkpoint memory")
        assert stored.state["stage"] == "transformed"
        assert stored.state["aggregates"] == 84
        assert stored.memory["last_table"] == "revenue_daily"
        assert "[EMAIL]" in stored.state["contact"]
        assert stored.sequence == 7


# --------------------------------------------------------------------------
# In-process path (api/services/ingestion.py), including the SDK emitter's
# concurrent buffer publish
# --------------------------------------------------------------------------


class TestInProcessBoundary:
    @pytest.mark.asyncio
    async def test_persist_event_redacts_the_object_the_buffer_streams(self, boundary_db):
        session_id = _uid("ses")
        await _seed_session(boundary_db, session_id)
        pipeline = _full_policy()
        event = TraceEvent(
            session_id=session_id,
            event_type=EventType.LLM_RESPONSE,
            name="llm_boundary",
            data={"content": f"contact {MARKER_EMAIL} for {MARKER_SENTINEL}", "model": "gpt-4-boundary"},
            metadata={"contact": MARKER_EMAIL},
        )
        buffer = EventBuffer()
        original_content = event.data["content"]

        # Mirror the SDK emitter: persist and publish the SAME object
        # concurrently, persister scheduled first (see api/services/ingestion.py).
        async def persist():
            await persist_event(event, session_maker=boundary_db, redaction_pipeline=pipeline)

        async def publish():
            await buffer.publish(session_id, event)

        await asyncio.gather(persist(), publish())

        # The streamed object is the redacted one.
        streamed = await buffer.get_events(session_id)
        assert len(streamed) == 1
        _assert_markers_absent(streamed[0].to_dict(), "in-process buffer / SSE fan-out")
        assert streamed[0].data["content"] == "[REDACTED]"

        # The stored row is redacted too, with structure intact.
        async with boundary_db() as db:
            repo = TraceRepository(db)
            stored = await repo.list_events(session_id)
        assert len(stored) == 1
        _assert_markers_absent(stored[0].to_dict(), "in-process persisted event row")
        assert stored[0].session_id == session_id
        assert stored[0].model == "gpt-4-boundary"

        # Local string built before ingestion is the documented in-memory
        # exception; it may keep the marker.
        assert MARKER_EMAIL in original_content

    @pytest.mark.asyncio
    async def test_persist_session_and_checkpoint_payloads_are_redacted(self, boundary_db):
        pipeline = _full_policy()
        session = Session(
            id=_uid("ses"),
            agent_name="boundary-agent",
            framework="pytest",
            status=SessionStatus.RUNNING,
            config={"notify": MARKER_EMAIL, "credentials": MARKER_AWS_KEY, "retries": 3},
        )
        await persist_session_start(
            session, session_maker=boundary_db, redaction_pipeline=pipeline
        )

        # Anchor event of the same session — checkpoint event references
        # must be consistent since the platform-audit gap closed.
        anchor_id = _uid("evt")
        await persist_event(
            TraceEvent(
                id=anchor_id,
                session_id=session.id,
                event_type=EventType.TOOL_CALL,
                name="boundary_anchor",
                data={"contact": MARKER_EMAIL},
            ),
            session_maker=boundary_db,
            redaction_pipeline=pipeline,
        )

        checkpoint = Checkpoint(
            session_id=session.id,
            event_id=anchor_id,
            sequence=3,
            state={"stage": "transformed", "contact": MARKER_EMAIL, "aggregates": 84},
            memory={"note": f"ping {MARKER_EMAIL}", "last_table": "revenue_daily"},
        )
        await persist_checkpoint(
            checkpoint, session_maker=boundary_db, redaction_pipeline=pipeline
        )

        session.status = SessionStatus.COMPLETED
        session.config["setting"] = MARKER_API_KEY
        await persist_session_update(
            session, session_maker=boundary_db, redaction_pipeline=pipeline
        )

        async with boundary_db() as db:
            repo = TraceRepository(db)
            stored_session = await repo.get_session(session.id)
            stored_checkpoints = await repo.list_checkpoints(session.id)

        assert stored_session is not None
        _assert_markers_absent(stored_session.config, "in-process session config row")
        assert stored_session.config["retries"] == 3
        assert str(stored_session.status) == "completed"

        assert len(stored_checkpoints) == 1
        _assert_markers_absent(
            stored_checkpoints[0].state, "in-process checkpoint state row"
        )
        _assert_markers_absent(
            stored_checkpoints[0].memory, "in-process checkpoint memory row"
        )
        assert stored_checkpoints[0].state["stage"] == "transformed"
        assert stored_checkpoints[0].memory["last_table"] == "revenue_daily"

        # Live caller objects keep their originals (documented exception).
        assert MARKER_EMAIL in session.config["notify"]
        assert MARKER_EMAIL in checkpoint.state["contact"]

    @pytest.mark.asyncio
    async def test_sdk_emitter_stream_is_redacted_end_to_end(self, boundary_db):
        """Full in-process wiring: emitter -> persist_event + buffer.publish."""
        from agent_debugger_sdk.core.emitter import EventEmitter

        session_id = _uid("ses")
        await _seed_session(boundary_db, session_id)
        pipeline = _full_policy()
        buffer = EventBuffer()
        session = Session(id=session_id, agent_name="boundary-agent", framework="pytest")
        emitter = EventEmitter(
            session_id=session_id,
            session=session,
            event_store=[],
            event_lock=asyncio.Lock(),
            event_sequence=ContextVar("boundary_seq", default=0),
            event_buffer=buffer,
            event_persister=lambda event: persist_event(
                event, session_maker=boundary_db, redaction_pipeline=pipeline
            ),
            session_update_hook=None,
            score_on_emit=False,
        )
        event = TraceEvent(
            session_id=session_id,
            event_type=EventType.TOOL_CALL,
            name="tool_call",
            data={"tool_name": "search", "arguments": {"q": MARKER_SENTINEL}},
            metadata={"contact": MARKER_EMAIL},
        )

        await emitter.emit(event)

        streamed = await buffer.get_events(session_id)
        assert len(streamed) == 1
        _assert_markers_absent(streamed[0].to_dict(), "emitter buffer / SSE fan-out")
        assert streamed[0].data["arguments"] == "[REDACTED]"

        async with boundary_db() as db:
            repo = TraceRepository(db)
            stored = await repo.list_events(session_id)
        assert len(stored) == 1
        _assert_markers_absent(stored[0].to_dict(), "emitter persisted event row")
        assert stored[0].tool_name == "search"


# --------------------------------------------------------------------------
# SSE generator: redacted frames survive, quiet streams keepalive
# --------------------------------------------------------------------------


class TestSseStreamBoundary:
    @pytest.mark.asyncio
    async def test_stream_emits_redacted_event(self):
        buffer = EventBuffer()
        session_id = _uid("ses")
        event = TraceEvent(
            session_id=session_id,
            event_type=EventType.LLM_RESPONSE,
            name="llm_boundary",
            data={"content": f"hi {MARKER_EMAIL}", "model": "gpt-4-boundary"},
            metadata={"contact": MARKER_EMAIL, "note": MARKER_SENTINEL},
        )
        # Pre-redact the way the publisher paths now always do.
        event = _full_policy().apply(event)

        frames: list[str] = []

        async def consume() -> None:
            async for frame in event_generator(session_id, buffer=buffer, max_connection_time=2):
                frames.append(frame)
                if "data: " in frame:
                    return

        reader = asyncio.create_task(consume())
        await _wait_for_subscriber(buffer, session_id)
        await buffer.publish(session_id, event)
        await asyncio.wait_for(reader, timeout=5)

        # Event blocks carry an id line plus the data line (Last-Event-ID
        # cursor support); match on the data payload, not the block prefix.
        data_frames = [f for f in frames if "data: " in f]
        assert len(data_frames) == 1
        _assert_markers_absent(data_frames[0], "SSE data frame")
        assert "[EMAIL]" in data_frames[0]
        assert "gpt-4-boundary" in data_frames[0]

    @pytest.mark.asyncio
    async def test_quiet_stream_yields_keepalive_then_close(self):
        """Direct exercise of the keepalive path (TimeoutError except clause).

        On Python 3.10 ``asyncio.wait_for`` raises ``asyncio.TimeoutError``,
        which only became an alias of the builtin ``TimeoutError`` in 3.11;
        the except clause catches both so a quiet period yields a keepalive
        instead of killing the stream.
        """
        buffer = EventBuffer()
        session_id = _uid("ses")

        frames = [
            frame
            async for frame in event_generator(session_id, buffer=buffer, max_connection_time=1)
        ]

        assert any(frame.startswith(": keepalive") for frame in frames)
        assert any(frame.startswith("event: close") for frame in frames)


async def _wait_for_subscriber(buffer: EventBuffer, session_id: str, timeout: float = 2.0) -> None:
    """Wait until the SSE generator has subscribed to the buffer."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if buffer._queues.get(session_id):  # noqa: SLF001 — test hook
            return
        await asyncio.sleep(0.02)
    raise AssertionError("SSE generator did not subscribe in time")
