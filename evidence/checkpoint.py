"""Independent checkpoint store for the Agent Evidence Box.

This store implements the "Nezavisna potvrda" requirement of
``docs/plans/agent-evidence-box.md``: a separate storage under audit-team
control receives an execution-start record *before* the first forwarded
call and a signed final checkpoint (event count + final chain hash) at
the end.  The auditor obtains the expected execution id and the checkpoint
from here, independently of the gateway, and can therefore detect a
missing package or a truncated chain.

Independence is a hard boundary: this module never imports or reads the
gateway ledger.  It records only what the gateway reports, in its own
directory, its own SQLite database (``checkpoints.db``, WAL) and with its
own Ed25519 keypair (``checkpoint_key.pem`` / ``checkpoint_key.pub.pem``).
Both record families are insert-only — rewriting history is a bug, not an
operation — so a second start or finalize for the same execution raises
:class:`CheckpointError`.

``dump_checkpoint`` writes the stored checkpoint as plain JSON so it can
be handed to the offline verifier through any out-of-band channel.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from evidence.schema import (
    ExecutionStartRecord,
    FinalCheckpoint,
    checkpoint_body_bytes,
    utc_now,
)
from evidence.signing import EvidenceSigner, verify_signature

__all__ = ["CheckpointError", "CheckpointStore"]

_DB_FILENAME = "checkpoints.db"
_PRIVATE_KEY_FILENAME = "checkpoint_key.pem"
_PUBLIC_KEY_FILENAME = "checkpoint_key.pub.pem"


class CheckpointError(ValueError):
    """A checkpoint-store contract violation (duplicate or missing record)."""


class CheckpointStore:
    """Insert-only store of execution starts and signed final checkpoints.

    The store is deliberately independent of the gateway ledger: it never
    validates checkpoints against recorded events, it only persists and
    signs what the gateway reports.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._private_key_path = self.directory / _PRIVATE_KEY_FILENAME
        self._public_key_path = self.directory / _PUBLIC_KEY_FILENAME
        self._signer = self._load_or_create_signer()
        self._connection = sqlite3.connect(self.directory / _DB_FILENAME)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    # -- Key management ----------------------------------------------------

    @property
    def key_id(self) -> str:
        """Content-derived id of the store's checkpoint signing key."""
        return self._signer.key_id

    def _load_or_create_signer(self) -> EvidenceSigner:
        if self._private_key_path.exists():
            signer = EvidenceSigner.from_pem(self._private_key_path.read_bytes())
        else:
            signer = EvidenceSigner.generate()
            # O_EXCL + explicit 0o600: the private key must never be
            # world-readable, and a racing creator must not silently win.
            fd = os.open(self._private_key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(signer.private_pem())
        if not self._public_key_path.exists():
            self._public_key_path.write_bytes(signer.public_pem())
        return signer

    # -- Persistence -------------------------------------------------------

    def _create_tables(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS execution_starts ("
                "    execution_id TEXT PRIMARY KEY,"
                "    record_json  TEXT NOT NULL"
                ")"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS final_checkpoints ("
                "    execution_id TEXT PRIMARY KEY,"
                "    record_json  TEXT NOT NULL"
                ")"
            )

    def _insert_only(self, table: str, execution_id: str, record_json: str) -> None:
        try:
            with self._connection:
                # Table names come only from the constants in this module.
                self._connection.execute(
                    f"INSERT INTO {table} (execution_id, record_json) VALUES (?, ?)",
                    (execution_id, record_json),
                )
        except sqlite3.IntegrityError as exc:
            raise CheckpointError(f"{table} already has a record for execution {execution_id!r}") from exc

    # -- Write API ---------------------------------------------------------

    def record_execution_start(
        self, execution_id: str, gateway_id: str, principal: str, policy_version: str
    ) -> ExecutionStartRecord:
        """Persist the start record for *execution_id* (insert-only).

        The caller's contract is to call this before the first forwarded
        call of the execution; this store only persists, it cannot observe
        the gateway.  A second call for the same execution raises.
        """
        record = ExecutionStartRecord(
            execution_id=execution_id,
            gateway_id=gateway_id,
            recorded_at=utc_now(),
            principal=principal,
            policy_version=policy_version,
        )
        self._insert_only("execution_starts", execution_id, record.model_dump_json())
        return record

    def finalize(
        self, execution_id: str, gateway_id: str, event_count: int, final_hash: str
    ) -> FinalCheckpoint:
        """Build, sign and persist the final checkpoint (insert-only).

        The checkpoint records exactly what the gateway reports; it is
        deliberately NOT validated against any event chain here —
        cross-checking against independently exported events is the
        offline verifier's job.
        """
        checkpoint = FinalCheckpoint(
            execution_id=execution_id,
            gateway_id=gateway_id,
            event_count=event_count,
            final_hash=final_hash,
            checkpoint_key_id=self.key_id,
            recorded_at=utc_now(),
            signature="",
        )
        checkpoint.signature = self._signer.sign(checkpoint_body_bytes(checkpoint))
        self._insert_only("final_checkpoints", execution_id, checkpoint.model_dump_json())
        return checkpoint

    # -- Read API ----------------------------------------------------------

    def get_start(self, execution_id: str) -> ExecutionStartRecord | None:
        row = self._connection.execute(
            "SELECT record_json FROM execution_starts WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return ExecutionStartRecord.model_validate_json(row[0]) if row else None

    def get_final(self, execution_id: str) -> FinalCheckpoint | None:
        row = self._connection.execute(
            "SELECT record_json FROM final_checkpoints WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return FinalCheckpoint.model_validate_json(row[0]) if row else None

    def execution_ids(self) -> list[str]:
        """All executions known to the store (starts and finals), sorted."""
        rows = self._connection.execute(
            "SELECT execution_id FROM execution_starts "
            "UNION SELECT execution_id FROM final_checkpoints "
            "ORDER BY execution_id"
        ).fetchall()
        return [row[0] for row in rows]

    def verify_final(self, checkpoint: FinalCheckpoint) -> bool:
        """Re-verify a checkpoint's signature with the store's public key."""
        return verify_signature(
            self._signer.public_pem(), checkpoint_body_bytes(checkpoint), checkpoint.signature
        )

    def dump_checkpoint(self, execution_id: str, out_file: Path | str) -> FinalCheckpoint:
        """Write the stored final checkpoint as JSON for offline handoff.

        This is the channel through which the auditor "independently
        obtains" the checkpoint.  Raises :class:`CheckpointError` if the
        store has no final checkpoint for *execution_id*.
        """
        checkpoint = self.get_final(execution_id)
        if checkpoint is None:
            raise CheckpointError(f"no final checkpoint recorded for execution {execution_id!r}")
        path = Path(out_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(checkpoint.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return checkpoint

    def close(self) -> None:
        """Close the database connection (the store cannot be used after)."""
        self._connection.close()
