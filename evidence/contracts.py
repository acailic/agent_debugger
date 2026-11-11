"""The ``EvidenceSink`` contract every durable evidence store implements.

The gateway depends only on this protocol, not on any concrete storage,
so the SQLite chain ledger, test doubles and future stores are
interchangeable.  Implementations must guarantee the plan's atomicity
requirement: assigning ``seq``, linking ``prev_hash``, signing and
persisting the event, and advancing the chain head happen as one
indivisible operation even under concurrent calls.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from evidence.schema import (
    GENESIS_PREV_HASH,
    ChainHead,
    EventDraft,
    EvidenceEvent,
    SignedEventRecord,
    event_content_bytes,
    event_hash,
)
from evidence.signing import EvidenceSigner

__all__ = ["EvidenceSink", "InMemoryEvidenceSink"]


@runtime_checkable
class EvidenceSink(Protocol):
    """Durable, tamper-evident store of signed chain events."""

    gateway_id: str
    key_id: str

    def append(self, draft: EventDraft) -> SignedEventRecord:
        """Atomically number, link, sign and persist *draft*.

        Must raise (and persist nothing) if persistence fails — callers
        treat a failed append as an operation-blocking condition.
        """
        ...

    def head(self, execution_id: str) -> ChainHead | None:
        """Current chain head for *execution_id*, or None if no events exist."""
        ...

    def events(self, execution_id: str) -> list[SignedEventRecord]:
        """All signed events for *execution_id*, ordered by ``seq``."""
        ...


class InMemoryEvidenceSink:
    """Reference ``EvidenceSink`` used by tests and as executable semantics.

    Not durable — production wiring uses the SQLite chain ledger.
    """

    def __init__(self, signer: EvidenceSigner, gateway_id: str = "gateway-memory") -> None:
        self.signer = signer
        self.gateway_id = gateway_id
        self.key_id = signer.key_id
        self._chains: dict[str, list[SignedEventRecord]] = {}

    def append(self, draft: EventDraft) -> SignedEventRecord:
        chain = self._chains.setdefault(draft.execution_id, [])
        prev_hash = chain[-1].hash if chain else GENESIS_PREV_HASH
        event = EvidenceEvent(
            type=draft.type,
            execution_id=draft.execution_id,
            seq=len(chain) + 1,
            prev_hash=prev_hash,
            gateway_id=self.gateway_id,
            key_id=self.key_id,
            recorded_at=draft.recorded_at,
            payload=draft.payload,
        )
        content = event_content_bytes(event)
        record = SignedEventRecord(
            event=event,
            hash=event_hash(event),
            signature=self.signer.sign(content),
        )
        chain.append(record)
        return record

    def head(self, execution_id: str) -> ChainHead | None:
        chain = self._chains.get(execution_id)
        if not chain:
            return None
        last = chain[-1]
        return ChainHead(
            execution_id=execution_id,
            last_seq=last.event.seq,
            last_hash=last.hash,
            event_count=len(chain),
        )

    def events(self, execution_id: str) -> list[SignedEventRecord]:
        return list(self._chains.get(execution_id, []))

    def all_executions(self) -> Iterable[str]:
        return list(self._chains)
