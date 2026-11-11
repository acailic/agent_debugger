"""Durable runtime wiring for the evidence gateway launcher.

``GatewayConfig`` models the POLICY surface (identity, bindings,
upstream command).  This module models the RUNTIME surface a deployment
adds on top — where the gateway key lives, where the signed chain
ledger lives, and where the independent checkpoint store lives.  The
launcher JSON carries both, with the runtime parts namespaced under
``"runtime"``::

    {
      "gateway_id": "gw-claims", "principal": "svc-claims-agent", ...,
      "bindings": [...], "upstream_command": [...],
      "runtime": {
        "gateway_key_pem": "keys/gateway_key.pem",
        "sink_db": "evidence/ledger.db",
        "checkpoint_dir": "evidence/checkpoints"
      }
    }

- ``gateway_key_pem`` is loaded when present, generated and persisted
  with 0600 permissions when absent (the first start of a new gateway
  identity).
- ``sink_db`` selects the durable SQLite :class:`ChainLedger`; without
  it the gateway runs on an in-memory sink with a fresh key — demo
  mode, exactly the pre-0.7.0 behaviour.
- ``checkpoint_dir`` selects an independent :class:`CheckpointStore`
  whose ``execution start`` hook fires before the first forwarded call
  (the plan's "Nezavisna potvrda" requirement).

``finalize_execution`` closes the loop on a clean shutdown: it reads
the ledger head and finalizes the checkpoint with the event count and
final chain hash.  A crashed gateway finalizes nothing — the package
then stays incomplete, which is exactly the semantics the offline
verifier reports.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence.checkpoint import CheckpointStore
from evidence.contracts import EvidenceSink, InMemoryEvidenceSink
from evidence.gateway.config import GatewayConfig
from evidence.gateway.proxy import EvidenceGateway
from evidence.gateway.rpc import StdioUpstream
from evidence.ledger import ChainLedger
from evidence.schema import FinalCheckpoint
from evidence.signing import EvidenceSigner

__all__ = ["GatewayRuntime", "build_runtime", "finalize_execution", "write_launcher_example"]

_RUNTIME_SECTION = "runtime"


@dataclass
class GatewayRuntime:
    """One wired, ready-to-serve gateway process."""

    config: GatewayConfig
    gateway: EvidenceGateway
    signer: EvidenceSigner
    sink: EvidenceSink
    upstream: StdioUpstream
    ledger: ChainLedger | None = None
    checkpoints: CheckpointStore | None = None

    @property
    def durable(self) -> bool:
        """True when events persist beyond the process (ledger wired)."""
        return self.ledger is not None

    def close(self) -> None:
        """Release process resources; safe to call once at shutdown."""
        self.upstream.close()
        if self.ledger is not None:
            self.ledger.close()
        if self.checkpoints is not None:
            self.checkpoints.close()


def build_runtime(config_path: str | Path) -> GatewayRuntime:
    """Wire a gateway from a launcher JSON (see the module docstring).

    Raises ``ValueError`` for a malformed config (via GatewayConfig)
    and for a malformed ``runtime`` section.
    """
    data: dict[str, Any] = json.loads(Path(config_path).read_text(encoding="utf-8"))
    runtime_cfg = data.pop(_RUNTIME_SECTION, {})
    if not isinstance(runtime_cfg, dict):
        raise ValueError(f"{_RUNTIME_SECTION!r} section must be an object")
    config = GatewayConfig.from_dict(data)

    key_path = _optional_path(runtime_cfg, "gateway_key_pem")
    sink_db = _optional_path(runtime_cfg, "sink_db")
    checkpoint_dir = _optional_path(runtime_cfg, "checkpoint_dir")
    unknown = set(runtime_cfg) - {"gateway_key_pem", "sink_db", "checkpoint_dir"}
    if unknown:
        raise ValueError(f"unknown runtime keys: {sorted(unknown)}")

    ledger: ChainLedger | None = None
    checkpoints: CheckpointStore | None = None
    if key_path is not None or sink_db is not None or checkpoint_dir is not None:
        signer = _load_or_create_signer(key_path) if key_path is not None else EvidenceSigner.generate()
        if sink_db is not None:
            ledger = ChainLedger(sink_db, signer, gateway_id=config.gateway_id)
        if checkpoint_dir is not None:
            checkpoints = CheckpointStore(checkpoint_dir)
    else:
        signer = EvidenceSigner.generate()

    if ledger is not None:
        sink: EvidenceSink = ledger
    else:
        sink = InMemoryEvidenceSink(signer, gateway_id=config.gateway_id)

    on_execution_started = None
    if checkpoints is not None:
        def on_execution_started(execution_id: str, _store: CheckpointStore = checkpoints) -> None:
            _store.record_execution_start(
                execution_id,
                gateway_id=config.gateway_id,
                principal=config.principal,
                policy_version=config.policy_version,
            )

    upstream = StdioUpstream(config.upstream_command, timeout_s=config.upstream_timeout_s)
    gateway = EvidenceGateway(config, sink=sink, upstream=upstream, on_execution_started=on_execution_started)
    return GatewayRuntime(
        config=config,
        gateway=gateway,
        signer=signer,
        sink=sink,
        upstream=upstream,
        ledger=ledger,
        checkpoints=checkpoints,
    )


def finalize_execution(runtime: GatewayRuntime) -> FinalCheckpoint | None:
    """Finalize the independent checkpoint from the ledger head.

    Only meaningful in durable mode (ledger + checkpoint store).  The
    gateway issues one execution id per process, so this runs once per
    clean shutdown; raises :class:`CheckpointError` if this execution
    was already finalized.
    """
    if runtime.ledger is None or runtime.checkpoints is None:
        return None
    head = runtime.ledger.head(runtime.gateway.execution_id)
    if head is None:
        return None
    return runtime.checkpoints.finalize(
        runtime.gateway.execution_id,
        runtime.config.gateway_id,
        head.event_count,
        head.last_hash,
    )


def write_launcher_example(path: str | Path, config: GatewayConfig, runtime: dict[str, str]) -> Path:
    """Serialize a launcher JSON (policy fields + runtime section)."""
    document = config.model_dump(mode="json")
    document[_RUNTIME_SECTION] = runtime
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target


def _optional_path(section: dict[str, Any], key: str) -> Path | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"runtime.{key} must be a non-empty path string")
    return Path(value)


def _load_or_create_signer(path: Path) -> EvidenceSigner:
    if path.exists():
        return EvidenceSigner.from_pem(path.read_bytes())
    signer = EvidenceSigner.generate()
    # O_EXCL + 0600: a gateway private key must never be world-readable,
    # and a racing creator must not silently win (mirrors CheckpointStore).
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(signer.private_pem())
    return signer
