"""``peaky-peek-evidence`` — the separately distributed offline CLI.

Two commands:

- ``verify``: check an evidence package directory offline against a
  customer-controlled key registry and an independently obtained final
  checkpoint; prints the three verdict sections (integrity, execution
  coverage, outcome knownness) in a machine-greppable format.
- ``keygen``: generate an Ed25519 keypair for one role and print the
  matching key registry entry so the operator can paste it into the
  registry.

Exit codes: 0 verification passed, 1 verification failed, 2 usage or
environment error (missing files, unreadable registry).  All reporting
logic lives in :mod:`evidence.verify`; this module only parses
arguments, moves bytes and prints.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from evidence.schema import FinalCheckpoint, VerificationResult
from evidence.signing import EvidenceSigner
from evidence.verify import KeyRegistry, verify_package

__all__ = ["main"]

#: Key roles a generated key can declare in the registry entry.
KEY_ROLES = ("gateway", "checkpoint", "package", "any")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        return _cmd_verify(args)
    return _cmd_keygen(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="peaky-peek-evidence",
        description="Offline verification of Agent Evidence Box packages.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="verify an evidence package offline")
    verify.add_argument("--package", required=True, help="package directory (manifest.json, events.ndjson, signature)")
    verify.add_argument("--keys", required=True, help="key registry JSON file (customer controlled)")
    verify.add_argument(
        "--checkpoint", help="FinalCheckpoint JSON dumped by the independent checkpoint store", default=None
    )
    verify.add_argument(
        "--expected-executions",
        help="newline-separated file of execution ids known to deserve packages",
        default=None,
    )

    keygen = sub.add_parser("keygen", help="generate an Ed25519 keypair and print a registry entry")
    keygen.add_argument("--out", required=True, help="output directory for the key files")
    keygen.add_argument("--role", default="gateway", choices=KEY_ROLES, help="key role recorded in the registry entry")
    return parser


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    package_dir = Path(args.package)
    if not package_dir.is_dir():
        print(f"ERROR: package directory not found: {package_dir}", file=sys.stderr)
        return 2
    registry_path = Path(args.keys)
    try:
        registry = KeyRegistry.load(registry_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot load key registry {registry_path}: {exc}", file=sys.stderr)
        return 2

    checkpoint: FinalCheckpoint | None = None
    if args.checkpoint:
        try:
            checkpoint = FinalCheckpoint.model_validate_json(
                Path(args.checkpoint).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot load checkpoint {args.checkpoint}: {exc}", file=sys.stderr)
            return 2

    expected_executions: list[str] | None = None
    if args.expected_executions:
        try:
            text = Path(args.expected_executions).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot read expected executions {args.expected_executions}: {exc}", file=sys.stderr)
            return 2
        expected_executions = [line.strip() for line in text.splitlines() if line.strip()]

    result = verify_package(
        package_dir, registry, checkpoint=checkpoint, expected_executions=expected_executions
    )
    _print_report(result)
    return 0 if result.ok else 1


def _print_report(result: VerificationResult) -> None:
    integrity = result.integrity
    print(f"INTEGRITY: {'PASS' if integrity.ok else 'FAIL'}")
    for finding in integrity.findings:
        print(f"  - [{finding.kind}] {finding.detail}")

    coverage = result.coverage
    print(f"COVERAGE: {'COMPLETE' if coverage.complete else 'INCOMPLETE'}")
    for part in (part for part in coverage.detail.split("; ") if part):
        print(f"  - {part}")

    outcomes = result.outcomes
    print(f"OUTCOMES: {outcomes.known} known, {outcomes.unknown} unknown")
    if outcomes.unknown_call_ids:
        print(f"  - unknown call ids: {', '.join(outcomes.unknown_call_ids)}")

    print(f"RESULT: {'PASS' if result.ok else 'FAIL'}")


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------


def _cmd_keygen(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"ERROR: cannot create output directory {out_dir}: {exc}", file=sys.stderr)
        return 2
    signer = EvidenceSigner.generate()
    private_path = out_dir / f"{args.role}_key.pem"
    public_path = out_dir / f"{args.role}_key.pub.pem"
    try:
        _write_private_key(private_path, signer.private_pem())
        public_path.write_bytes(signer.public_pem())
    except OSError as exc:
        print(f"ERROR: cannot write key files into {out_dir}: {exc}", file=sys.stderr)
        return 2
    entry = {
        "key_id": signer.key_id,
        "public_key_pem": signer.public_pem().decode("ascii"),
        "status": "active",
        "valid_from": datetime.now(timezone.utc).isoformat(),
        "valid_to": None,
        "role": args.role,
    }
    print(json.dumps(entry))
    return 0


def _write_private_key(path: Path, pem: bytes) -> None:
    """Write a private key file with owner-only permissions (0600)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(fd, 0o600)  # also narrows a pre-existing wider mode
        handle.write(pem)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
