"""SQLite chain ledger tests — atomicity, durability, tamper evidence."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from evidence.contracts import EvidenceSink
from evidence.ledger import ChainLedger
from evidence.schema import (
    GENESIS_PREV_HASH,
    EventDraft,
    EventType,
    SignedEventRecord,
    event_content_bytes,
    event_hash,
    utc_now,
)
from evidence.signing import EvidenceSigner

DB_NAME = "ledger.db"


class FlakySigner:
    """EvidenceSigner stand-in that fails once its success budget is spent."""

    def __init__(self, inner: EvidenceSigner, successes: int) -> None:
        self._inner = inner
        self._remaining = successes

    @property
    def key_id(self) -> str:
        return self._inner.key_id

    def sign(self, payload: bytes) -> str:
        if self._remaining <= 0:
            raise RuntimeError("signing backend unavailable")
        self._remaining -= 1
        return self._inner.sign(payload)


@pytest.fixture()
def signer() -> EvidenceSigner:
    return EvidenceSigner.generate()


@pytest.fixture()
def ledger(tmp_path, signer) -> ChainLedger:
    ledger = ChainLedger(tmp_path / DB_NAME, signer=signer, gateway_id="gw-ledger-test")
    yield ledger
    ledger.close()


def draft(event_type: EventType, execution_id: str = "exec-1", **payload) -> EventDraft:
    return EventDraft(
        type=event_type, execution_id=execution_id, recorded_at=utc_now(), payload=payload
    )


def open_raw(tmp_path) -> sqlite3.Connection:
    """Direct connection to the ledger file, bypassing ChainLedger (tampering)."""
    conn = sqlite3.connect(tmp_path / DB_NAME)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


class TestChainSemantics:
    def test_first_append_is_seq_one_with_genesis_prev_hash(self, ledger):
        record = ledger.append(draft(EventType.EXECUTION_STARTED, principal="svc-claims"))
        assert record.event.seq == 1
        assert record.event.prev_hash == GENESIS_PREV_HASH
        assert record.event.gateway_id == "gw-ledger-test"
        assert record.event.key_id == ledger.key_id

    def test_second_append_links_to_first_hash(self, ledger):
        first = ledger.append(draft(EventType.EXECUTION_STARTED))
        second = ledger.append(draft(EventType.DECISION_RECORDED, call_id="call-1"))
        assert second.event.seq == 2
        assert second.event.prev_hash == first.hash

    def test_chains_independent_per_execution(self, ledger):
        ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        other = ledger.append(draft(EventType.EXECUTION_STARTED, "exec-b"))
        assert other.event.seq == 1
        assert other.event.prev_hash == GENESIS_PREV_HASH
        assert ledger.head("exec-a").event_count == 1
        assert ledger.head("exec-b").event_count == 1

    def test_head_tracks_chain_and_none_for_unknown(self, ledger):
        first = ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        second = ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id="c1"))
        head = ledger.head("exec-a")
        assert (head.last_seq, head.last_hash, head.event_count) == (2, second.hash, 2)
        assert head.last_hash != first.hash
        assert ledger.head("unknown-exec") is None

    def test_events_parsed_as_records_ordered_by_seq(self, ledger):
        for i in range(3):
            ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id=f"c{i}"))
        records = ledger.events("exec-a")
        assert all(isinstance(record, SignedEventRecord) for record in records)
        assert [record.event.seq for record in records] == [1, 2, 3]

    def test_execution_ids_lists_all_chains(self, ledger):
        ledger.append(draft(EventType.EXECUTION_STARTED, "exec-b"))
        ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        assert ledger.execution_ids() == ["exec-a", "exec-b"]

    def test_ledger_satisfies_evidence_sink_protocol(self, ledger):
        assert isinstance(ledger, EvidenceSink)


class TestRestartDurability:
    def test_reopen_preserves_state_and_chain_continues(self, tmp_path, signer):
        db_path = tmp_path / DB_NAME
        first_ledger = ChainLedger(db_path, signer=signer, gateway_id="gw-dur")
        first_ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a", principal="svc"))
        first_ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id="c1"))
        first_ledger.append(draft(EventType.OUTCOME_RECORDED, "exec-b", call_id="c9"))
        head_before = first_ledger.head("exec-a")
        events_before = [record.model_dump() for record in first_ledger.events("exec-a")]
        ids_before = first_ledger.execution_ids()
        first_ledger.close()

        reopened = ChainLedger(db_path, signer=signer, gateway_id="gw-dur")
        try:
            assert reopened.head("exec-a") == head_before
            assert [record.model_dump() for record in reopened.events("exec-a")] == events_before
            assert reopened.execution_ids() == ids_before == ["exec-a", "exec-b"]
            third = reopened.append(draft(EventType.OUTCOME_RECORDED, "exec-a", call_id="c1"))
            assert third.event.seq == 3
            assert third.event.prev_hash == head_before.last_hash
            assert reopened.head("exec-a").event_count == 3
        finally:
            reopened.close()


class TestConcurrentAppends:
    def test_parallel_appends_two_executions_no_gaps_or_duplicates(self, ledger, signer):
        executions = ("exec-a", "exec-b")
        threads, per_thread_per_execution = 8, 10
        expected_per_execution = threads * per_thread_per_execution

        def worker(index: int) -> int:
            appended = 0
            for i in range(per_thread_per_execution):
                for execution_id in executions:
                    ledger.append(
                        draft(EventType.DECISION_RECORDED, execution_id, call_id=f"c-{index}-{i}")
                    )
                    appended += 1
            return appended

        with ThreadPoolExecutor(max_workers=threads) as pool:
            results = list(pool.map(worker, range(threads)))
        assert sum(results) == threads * per_thread_per_execution * len(executions)

        for execution_id in executions:
            chain = ledger.events(execution_id)
            assert len(chain) == expected_per_execution
            assert [record.event.seq for record in chain] == list(
                range(1, expected_per_execution + 1)
            )
            head = ledger.head(execution_id)
            assert (head.last_seq, head.event_count) == (
                expected_per_execution,
                expected_per_execution,
            )
            assert ledger.verify_chain(execution_id, signer.public_pem()) == []


class TestAppendFailure:
    def test_signing_failure_mid_transaction_persists_nothing(self, tmp_path):
        real = EvidenceSigner.generate()
        ledger = ChainLedger(
            tmp_path / DB_NAME, signer=FlakySigner(real, successes=1), gateway_id="gw-flaky"
        )
        try:
            first = ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
            with pytest.raises(RuntimeError, match="signing backend unavailable"):
                ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id="c1"))
            head = ledger.head("exec-a")
            assert (head.last_seq, head.last_hash, head.event_count) == (1, first.hash, 1)
            assert len(ledger.events("exec-a")) == 1
            assert ledger.verify_chain("exec-a", real.public_pem()) == []
        finally:
            ledger.close()

    def test_insert_failure_rolls_back_head_unchanged(self, ledger, tmp_path):
        first = ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a"))
        conn = open_raw(tmp_path)
        conn.execute(
            "CREATE TRIGGER block_event_insert BEFORE INSERT ON ledger_events "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END;"
        )
        conn.commit()
        conn.close()

        with pytest.raises(sqlite3.IntegrityError):
            ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id="c1"))

        head = ledger.head("exec-a")
        assert (head.last_seq, head.last_hash, head.event_count) == (1, first.hash, 1)
        assert len(ledger.events("exec-a")) == 1


class TestVerifyChain:
    def test_honest_chain_verifies_clean(self, ledger, signer):
        ledger.append(draft(EventType.EXECUTION_STARTED, "exec-a", principal="svc"))
        ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id="c1"))
        ledger.append(draft(EventType.OUTCOME_RECORDED, "exec-a", call_id="c1"))
        assert ledger.verify_chain("exec-a", signer.public_pem()) == []

    def test_unknown_execution_reports_problem(self, ledger, signer):
        problems = ledger.verify_chain("nope", signer.public_pem())
        assert len(problems) == 1
        assert "no events" in problems[0]

    def test_tampered_stored_payload_detected(self, ledger, signer, tmp_path):
        for i in range(3):
            ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", reason=f"r{i}", call_id=f"c{i}"))
        conn = open_raw(tmp_path)
        (record_json,) = conn.execute(
            "SELECT record_json FROM ledger_events WHERE execution_id = 'exec-a' AND seq = 2"
        ).fetchone()
        document = json.loads(record_json)
        document["event"]["payload"]["reason"] = "tampered"
        conn.execute(
            "UPDATE ledger_events SET record_json = ? WHERE execution_id = 'exec-a' AND seq = 2",
            (json.dumps(document),),
        )
        conn.commit()
        conn.close()

        problems = ledger.verify_chain("exec-a", signer.public_pem())
        assert any("hash" in problem and "seq 2" in problem for problem in problems)
        assert any("signature" in problem and "seq 2" in problem for problem in problems)

    def test_deleted_middle_event_detected(self, ledger, signer, tmp_path):
        for i in range(3):
            ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id=f"c{i}"))
        conn = open_raw(tmp_path)
        conn.execute("DELETE FROM ledger_events WHERE execution_id = 'exec-a' AND seq = 2")
        conn.commit()
        conn.close()

        problems = ledger.verify_chain("exec-a", signer.public_pem())
        assert any("not contiguous" in problem and "seq 3" in problem for problem in problems)
        assert any("prev_hash" in problem for problem in problems)

    def test_resigned_event_with_different_key_detected(self, ledger, signer, tmp_path):
        records = [
            ledger.append(draft(EventType.DECISION_RECORDED, "exec-a", call_id=f"c{i}"))
            for i in range(3)
        ]
        attacker = EvidenceSigner.generate()
        forged_event = records[1].event.model_copy(
            update={"payload": {**records[1].event.payload, "call_id": "forged"}}
        )
        forged = SignedEventRecord(
            event=forged_event,
            hash=event_hash(forged_event),
            signature=attacker.sign(event_content_bytes(forged_event)),
        )
        assert forged.event.prev_hash == records[0].hash  # properly relinked...
        assert forged.hash == event_hash(forged_event)  # ...and honestly hashed...
        conn = open_raw(tmp_path)
        conn.execute(
            "UPDATE ledger_events SET record_json = ? WHERE execution_id = 'exec-a' AND seq = 2",
            (forged.model_dump_json(),),
        )
        conn.commit()
        conn.close()

        problems = ledger.verify_chain("exec-a", signer.public_pem())
        # ...so only the signature check against the trusted key can catch it.
        assert any("signature" in problem and "seq 2" in problem for problem in problems)
