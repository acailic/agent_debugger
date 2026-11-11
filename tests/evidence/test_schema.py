"""Shared evidence schema contract tests."""

import pytest
from pydantic import ValidationError

from evidence.canonical import CanonicalizationError
from evidence.contracts import EvidenceSink, InMemoryEvidenceSink
from evidence.schema import (
    GENESIS_PREV_HASH,
    EventDraft,
    EventType,
    EvidenceEvent,
    FinalCheckpoint,
    OutcomePayload,
    OutcomeStatus,
    checkpoint_body_bytes,
    event_content_bytes,
    event_hash,
    input_schema_hash,
    manifest_bytes,
    utc_now,
)
from evidence.signing import EvidenceSigner


@pytest.fixture()
def sink() -> InMemoryEvidenceSink:
    return InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")


def draft(event_type: EventType, execution_id: str = "exec-1", **payload) -> EventDraft:
    return EventDraft(
        type=event_type, execution_id=execution_id, recorded_at=utc_now(), payload=payload
    )


class TestEventDraft:
    def test_execution_id_required(self):
        with pytest.raises(ValidationError):
            EventDraft(type=EventType.EXECUTION_STARTED, execution_id="", recorded_at=utc_now())

    def test_empty_execution_id_rejected(self):
        with pytest.raises(ValidationError):
            EventDraft(type=EventType.DECISION_RECORDED, execution_id="", recorded_at=utc_now())


class TestSinkChainSemantics:
    def test_first_event_genesis_link(self, sink):
        record = sink.append(draft(EventType.EXECUTION_STARTED, principal="svc-claims"))
        assert record.event.seq == 1
        assert record.event.prev_hash == GENESIS_PREV_HASH

    def test_chain_links_hash_of_previous(self, sink):
        first = sink.append(draft(EventType.EXECUTION_STARTED))
        second = sink.append(draft(EventType.DECISION_RECORDED))
        assert second.event.seq == 2
        assert second.event.prev_hash == first.hash

    def test_chains_independent_per_execution(self, sink):
        sink.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        other = sink.append(draft(EventType.EXECUTION_STARTED, "exec-b"))
        assert other.event.seq == 1
        assert other.event.prev_hash == GENESIS_PREV_HASH

    def test_head_tracks_chain(self, sink):
        sink.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        second = sink.append(draft(EventType.OUTCOME_RECORDED, "exec-a"))
        head = sink.head("exec-a")
        assert head is not None
        assert (head.last_seq, head.last_hash, head.event_count) == (2, second.hash, 2)

    def test_head_none_for_unknown_execution(self, sink):
        assert sink.head("nope") is None

    def test_events_ordered_by_seq(self, sink):
        sink.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        sink.append(draft(EventType.DECISION_RECORDED, "exec-a"))
        sink.append(draft(EventType.OUTCOME_RECORDED, "exec-a"))
        seqs = [record.event.seq for record in sink.events("exec-a")]
        assert seqs == [1, 2, 3]

    def test_in_memory_sink_satisfies_protocol(self, sink):
        assert isinstance(sink, EvidenceSink)

    def test_gateway_and_key_id_stamped_on_events(self, sink):
        record = sink.append(draft(EventType.EXECUTION_STARTED))
        assert record.event.gateway_id == "gw-test"
        assert record.event.key_id == sink.signer.key_id
        assert record.event.key_id == sink.key_id


class TestSignedContent:
    def test_event_hash_is_sha256_of_canonical_content(self, sink):
        record = sink.append(draft(EventType.EXECUTION_STARTED))
        assert record.hash == event_hash(record.event)
        assert len(record.hash) == 64
        assert record.signature == sink.signer.sign(event_content_bytes(record.event))

    def test_content_bytes_deterministic_across_payload_key_order(self):
        base = dict(type=EventType.EXECUTION_STARTED, execution_id="exec-1", seq=1,
                    prev_hash=GENESIS_PREV_HASH, gateway_id="g", key_id="k",
                    recorded_at=utc_now(), payload={"b": 1, "a": 2})
        one = EvidenceEvent(**base)
        base["payload"] = {"a": 2, "b": 1}
        two = EvidenceEvent(**base)
        assert event_content_bytes(one) == event_content_bytes(two)

    def test_floats_rejected_at_signing_time(self):
        event = EvidenceEvent(
            type=EventType.EXECUTION_STARTED, execution_id="e", seq=1,
            prev_hash=GENESIS_PREV_HASH, gateway_id="g", key_id="k",
            recorded_at=utc_now(), payload={"bad": 1.5},
        )
        with pytest.raises(CanonicalizationError):
            event_content_bytes(event)

    def test_input_schema_hash_key_order_insensitive(self):
        a = {"type": "object", "properties": {"x": {"type": "string"}, "y": {"type": "number"}}}
        b = {"properties": {"y": {"type": "number"}, "x": {"type": "string"}}, "type": "object"}
        assert input_schema_hash(a) == input_schema_hash(b)


class TestCheckpointAndManifestBytes:
    def _checkpoint(self) -> FinalCheckpoint:
        return FinalCheckpoint(
            execution_id="exec-1", gateway_id="gw", event_count=3,
            final_hash="ab" * 32, checkpoint_key_id="ed25519:deadbeefdeadbeef",
            recorded_at=utc_now(), signature="ff" * 64,
        )

    def test_checkpoint_signature_excluded_from_body(self):
        body = checkpoint_body_bytes(self._checkpoint())
        assert b'"signature"' not in body
        assert b'"event_count":3' in body

    def test_manifest_bytes_canonical_and_deterministic(self):
        from evidence.schema import PackageManifest

        manifest = PackageManifest(
            gateway_id="gw", execution_id="exec-1", event_count=3,
            final_hash="ab" * 32, key_id="ed25519:deadbeefdeadbeef", created_at=utc_now(),
        )
        assert manifest_bytes(manifest) == manifest_bytes(manifest)
        assert b"   " not in manifest_bytes(manifest)


class TestPayloadModels:
    def test_outcome_payload_defaults(self):
        payload = OutcomePayload(call_id="call-1", status=OutcomeStatus.UNKNOWN)
        assert payload.outcome_code is None
        assert payload.duration_ms is None

    def test_outcome_payload_serializes_into_event_payload(self, sink):
        payload = OutcomePayload(
            call_id="call-1", status=OutcomeStatus.SUCCESS, outcome_code="updated", duration_ms=12
        )
        record = sink.append(
            draft(EventType.OUTCOME_RECORDED, **payload.model_dump(mode="json"))
        )
        assert record.event.payload["call_id"] == "call-1"
        assert record.event.payload["status"] == "success"
