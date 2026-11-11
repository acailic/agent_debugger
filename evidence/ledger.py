"""Durable SQLite chain ledger — the production ``EvidenceSink``.

Implements the atomicity rule of ``docs/plans/agent-evidence-box.md``
§"Potpisivanje i čuvanje": seq assignment, ``prev_hash`` linkage,
signing, the event INSERT and the chain-head advance all happen inside
ONE ``BEGIN IMMEDIATE`` transaction, so parallel ``append`` calls
serialize into a single correct chain per execution, and any failure
rolls back leaving the ledger exactly as it was.

Storage is stdlib ``sqlite3`` (no SQLAlchemy) with ``journal_mode=WAL``
and ``synchronous=FULL``: committed events survive process crash or
power loss, and the WAL sidecar lets external readers (export, audit)
inspect the ledger concurrently.  One connection is shared by all
threads behind a single lock — a write is short (sign plus two
statements), so contention is negligible next to the atomicity
guarantee the lock buys.

Each event is stored as the JSON text of its full
:class:`SignedEventRecord`, keyed ``(execution_id, seq)``; the head row
keeps the last seq/hash and event count, updated in the same
transaction.  ``verify_chain`` re-derives everything (content hash,
prev-hash linkage, seq contiguity, Ed25519 signature) from the stored
rows alone, so tampering with the database file is detectable offline.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from evidence.schema import (
    GENESIS_PREV_HASH,
    ChainHead,
    EventDraft,
    EvidenceEvent,
    SignedEventRecord,
    event_content_bytes,
    sha256_hex,
)
from evidence.signing import EvidenceSigner, verify_signature

__all__ = ["ChainLedger"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_events (
    execution_id TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    record_json  TEXT NOT NULL,
    PRIMARY KEY (execution_id, seq)
);
CREATE TABLE IF NOT EXISTS ledger_heads (
    execution_id TEXT NOT NULL PRIMARY KEY,
    last_seq     INTEGER NOT NULL,
    last_hash    TEXT NOT NULL,
    event_count  INTEGER NOT NULL
);
"""

_HEAD_COLUMNS = "last_seq, last_hash, event_count"


class ChainLedger:
    """SQLite-backed ``EvidenceSink``: per-execution signed hash chains.

    Satisfies the :class:`evidence.contracts.EvidenceSink` protocol.
    Construct once per gateway process and share across threads;
    ``append`` is the only method that writes, always atomically.
    """

    def __init__(self, path: str | Path, signer: EvidenceSigner, gateway_id: str) -> None:
        self.path = Path(path)
        self.signer = signer
        self.gateway_id = gateway_id
        self.key_id = signer.key_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(_SCHEMA)

    # -- EvidenceSink -------------------------------------------------------

    def append(self, draft: EventDraft) -> SignedEventRecord:
        """Atomically number, link, sign and persist *draft*.

        Runs in one ``BEGIN IMMEDIATE`` transaction: read the chain head,
        assign ``seq = last_seq + 1`` (1 for a new chain, genesis
        ``prev_hash``), sign the canonical event content, insert the
        record and advance the head.  Any failure rolls back and
        re-raises — nothing is persisted, the head is unchanged.
        """
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    f"SELECT {_HEAD_COLUMNS} FROM ledger_heads WHERE execution_id = ?",
                    (draft.execution_id,),
                ).fetchone()
                if row is None:
                    seq, prev_hash, event_count = 1, GENESIS_PREV_HASH, 1
                else:
                    seq, prev_hash, event_count = row[0] + 1, row[1], row[2] + 1
                event = EvidenceEvent(
                    type=draft.type,
                    execution_id=draft.execution_id,
                    seq=seq,
                    prev_hash=prev_hash,
                    gateway_id=self.gateway_id,
                    key_id=self.key_id,
                    recorded_at=draft.recorded_at,
                    payload=draft.payload,
                )
                content = event_content_bytes(event)
                digest = sha256_hex(content)  # identical to event_hash(event)
                record = SignedEventRecord(
                    event=event, hash=digest, signature=self.signer.sign(content)
                )
                self._conn.execute(
                    "INSERT INTO ledger_events (execution_id, seq, record_json) VALUES (?, ?, ?)",
                    (draft.execution_id, seq, record.model_dump_json()),
                )
                self._conn.execute(
                    """
                    INSERT INTO ledger_heads (execution_id, last_seq, last_hash, event_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(execution_id) DO UPDATE SET
                        last_seq = excluded.last_seq,
                        last_hash = excluded.last_hash,
                        event_count = excluded.event_count
                    """,
                    (draft.execution_id, seq, digest, event_count),
                )
                self._conn.execute("COMMIT")
                return record
            except BaseException:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass  # the connection itself is broken; nothing was committed
                raise

    def head(self, execution_id: str) -> ChainHead | None:
        """Current chain head for *execution_id*, or None if no events exist."""
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_HEAD_COLUMNS} FROM ledger_heads WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            return None
        return ChainHead(
            execution_id=execution_id, last_seq=row[0], last_hash=row[1], event_count=row[2]
        )

    def events(self, execution_id: str) -> list[SignedEventRecord]:
        """All signed events for *execution_id*, ordered by ``seq``."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT record_json FROM ledger_events WHERE execution_id = ? ORDER BY seq",
                (execution_id,),
            ).fetchall()
        return [SignedEventRecord.model_validate_json(row[0]) for row in rows]

    # -- Ledger-specific ----------------------------------------------------

    def execution_ids(self) -> list[str]:
        """All execution ids that have at least one event, sorted."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT execution_id FROM ledger_heads ORDER BY execution_id"
            ).fetchall()
        return [row[0] for row in rows]

    def verify_chain(self, execution_id: str, public_pem: bytes) -> list[str]:
        """Re-verify a stored chain against *public_pem*; empty list means clean.

        Checks per event: seq contiguity from 1, ``prev_hash`` linkage
        (genesis for seq 1, the previous record's stored hash otherwise),
        the recomputed canonical content hash, and the Ed25519 signature.
        All problems are reported, not just the first.
        """
        records = self.events(execution_id)
        if not records:
            return [f"execution {execution_id!r}: no events stored"]
        problems: list[str] = []
        expected_seq = 1
        prev_hash = GENESIS_PREV_HASH
        for record in records:
            event = record.event
            if event.seq != expected_seq:
                problems.append(f"seq {event.seq}: expected seq {expected_seq}, chain not contiguous")
            if event.prev_hash != prev_hash:
                problems.append(
                    f"seq {event.seq}: prev_hash does not link to previous hash "
                    f"({event.prev_hash} != {prev_hash})"
                )
            if record.hash != sha256_hex(event_content_bytes(event)):
                problems.append(f"seq {event.seq}: stored hash does not match recomputed content hash")
            if not verify_signature(public_pem, event_content_bytes(event), record.signature):
                problems.append(f"seq {event.seq}: signature verification failed")
            expected_seq = event.seq + 1
            prev_hash = record.hash
        return problems

    def close(self) -> None:
        """Close the underlying connection; the ledger must not be used afterwards."""
        with self._lock:
            self._conn.close()
