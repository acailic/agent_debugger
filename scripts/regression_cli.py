#!/usr/bin/env python3
"""Regression-lab CLI: incident export → local run → baseline/candidate compare.

Roadmap W05 / queue item Q14 — the operator entry points for the first slice
of the incident-to-regression workflow. Everything is local and
deterministic; no agent or tool is executed.

Usage::

    # 1. Export a captured incident as a sanitized, shareable regression case
    #    (default) or a raw local copy (--raw).
    python scripts/regression_cli.py export --session-id X --out incident.json \\
        [--raw] [--db-url URL] [--tenant ID]

    # 2. Replay a bundle through the CURRENT audit engine and evaluate its
    #    stored expected assertions. Exit 1 when any assertion fails.
    python scripts/regression_cli.py run --bundle incident.json [--json] [--out run.json]

    # 3. Compare a candidate run against a baseline run of the SAME bundle
    #    (e.g. before/after engine tuning). Exit 1 when anything regressed.
    python scripts/regression_cli.py compare --baseline base.json --candidate cand.json [--json]

    # 4. Run every bundle in a directory (the committed regression suite) and
    #    report a combined verdict. Exit 1 when any bundle fails.
    python scripts/regression_cli.py run-suite --dir benchmarks/regression/ [--json]

Exit codes: 0 = pass / nothing regressed, 1 = failed assertions or a
regression was found, 2 = operational error (missing session, tampered
bundle, mismatched bundles, empty suite directory, ...).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.regression import (  # noqa: E402
    compare_run_results,
    export_session_bundle,
    load_bundle,
    run_bundle,
    save_bundle,
)
from storage import TraceRepository  # noqa: E402
from storage.engine import get_database_url  # noqa: E402

# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


async def _export_async(args: argparse.Namespace) -> int:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    db_url = args.db_url or get_database_url()
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db_session:
            repo = TraceRepository(db_session, tenant_id=args.tenant)
            bundle = await export_session_bundle(
                repo, args.session_id, sanitized=not args.raw
            )
    finally:
        await engine.dispose()

    out = save_bundle(bundle, args.out)
    print(f"Exported session {bundle['session']['id']} -> {out}")
    print(f"  events: {bundle['event_count']}  checkpoints: {bundle['checkpoint_count']}")
    print(f"  sanitized: {bundle['sanitized']}  redaction: {bundle['redaction']}")
    print(f"  assertions: {len(bundle['expected_assertions'])}")
    print(f"  content_hash: {bundle['content_hash']}")
    return 0


# ---------------------------------------------------------------------------
# run / compare
# ---------------------------------------------------------------------------


def _print_run_result(result: dict) -> None:
    verdict = "PASS" if result["verdict"] == "pass" else "FAIL"
    print(
        f"Session {result['session_id']} — verdict {verdict}: "
        f"{result['passed']}/{result['total']} assertions passed "
        f"({result['failed']} failed)"
    )
    print(f"  bundle: {result['bundle_hash']}  sanitized: {result['sanitized']}")
    print(f"  engine: audit_engine_version={result['engine']['audit_engine_version']}")
    for row in result["assertions"]:
        marker = "PASS" if row["passed"] else "FAIL"
        if row["passed"]:
            print(f"  [{marker}] {row['path']} = {row['actual']!r}")
        else:
            print(f"  [{marker}] {row['path']}: expected {row['expected']!r}, got {row['actual']!r}")


def _run(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    result = run_bundle(bundle)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        _print_run_result(result)
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"Run result written to {args.out}")
    return 0 if result["verdict"] == "pass" else 1


def _print_comparison(comparison: dict) -> None:
    counts = comparison["counts"]
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    print(
        f"Baseline {baseline['verdict']} ({baseline['passed']}/{baseline['total']}) vs "
        f"candidate {candidate['verdict']} ({candidate['passed']}/{candidate['total']})"
    )
    print(f"  bundle: {comparison['bundle_hash']}")
    print(f"  engine versions match: {comparison['engine_versions_match']}")
    print(
        f"Verdict {comparison['verdict'].upper()}: {counts['regressed']} regressed, "
        f"{counts['improved']} improved, {counts['changed']} changed, "
        f"{counts['unchanged']} unchanged"
        + (
            f", {counts['added']} added, {counts['removed']} removed"
            if counts["added"] or counts["removed"]
            else ""
        )
    )
    for row in comparison["rows"]:
        if row["status"] == "unchanged":
            continue
        detail = ""
        if "baseline" in row and "candidate" in row:
            detail = f": {row['baseline']['actual']!r} -> {row['candidate']['actual']!r}"
        print(f"  [{row['status'].upper()}] {row['path']}{detail}")


def _compare(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    comparison = compare_run_results(baseline, candidate)
    if args.json:
        print(json.dumps(comparison, indent=2, sort_keys=True, default=str))
    else:
        _print_comparison(comparison)
    return 0 if comparison["verdict"] != "regressed" else 1


# ---------------------------------------------------------------------------
# run-suite (the committed regression suite)
# ---------------------------------------------------------------------------


def _run_suite(args: argparse.Namespace) -> int:
    """Run every ``*.json`` bundle in *args.dir*; one combined verdict."""
    directory = Path(args.dir)
    bundle_paths = sorted(directory.glob("*.json"))
    if not bundle_paths:
        print(f"ERROR: no *.json incident bundles found in {directory}", file=sys.stderr)
        return 2

    results = []
    for path in bundle_paths:
        result = run_bundle(load_bundle(path))
        results.append((path, result))
        verdict = "PASS" if result["verdict"] == "pass" else "FAIL"
        print(
            f"{path.name}: {verdict} — {result['passed']}/{result['total']} assertions passed "
            f"({result['failed']} failed)"
        )
        for row in result["assertions"]:
            if not row["passed"]:
                print(
                    f"  [FAIL] {row['path']}: expected {row['expected']!r}, got {row['actual']!r}"
                )

    failed_bundles = sum(1 for _, result in results if result["verdict"] != "pass")
    total = sum(result["total"] for _, result in results)
    passed = sum(result["passed"] for _, result in results)
    suite_verdict = "PASS" if failed_bundles == 0 else "FAIL"
    print(
        f"Suite verdict {suite_verdict}: {len(results) - failed_bundles}/{len(results)} bundles "
        f"passed, {passed}/{total} assertions passed"
    )
    if args.json:
        print(
            json.dumps(
                {
                    "verdict": suite_verdict.lower(),
                    "bundle_count": len(results),
                    "failed_bundles": failed_bundles,
                    "passed": passed,
                    "total": total,
                    "bundles": [
                        {"file": path.name, **{key: result[key] for key in (
                            "session_id", "bundle_hash", "verdict", "passed", "failed", "total"
                        )}}
                        for path, result in results
                    ],
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    return 0 if failed_bundles == 0 else 1


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Incident-bundle regression lab: export, run, compare.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export a stored session as an incident bundle")
    export_parser.add_argument("--session-id", required=True, help="Session id to export")
    export_parser.add_argument("--out", required=True, help="Output bundle file (JSON)")
    export_parser.add_argument("--raw", action="store_true", help="Skip sanitization (local operator only)")
    export_parser.add_argument("--db-url", default=None, help="Database URL (default: AGENT_DEBUGGER_DB_URL)")
    export_parser.add_argument("--tenant", default="local", help="Tenant id for repository scoping")

    run_parser = subparsers.add_parser("run", help="Replay a bundle and evaluate its assertions")
    run_parser.add_argument("--bundle", required=True, help="Incident bundle file (JSON)")
    run_parser.add_argument("--json", action="store_true", help="Print the run result as JSON")
    run_parser.add_argument("--out", default=None, help="Write the run result to this file for later compare")

    compare_parser = subparsers.add_parser("compare", help="Compare candidate vs baseline run results")
    compare_parser.add_argument("--baseline", required=True, help="Baseline run-result file (JSON)")
    compare_parser.add_argument("--candidate", required=True, help="Candidate run-result file (JSON)")
    compare_parser.add_argument("--json", action="store_true", help="Print the comparison as JSON")

    suite_parser = subparsers.add_parser(
        "run-suite", help="Run every bundle in a directory and report a combined verdict"
    )
    suite_parser.add_argument(
        "--dir",
        default="benchmarks/regression",
        help="Directory of incident bundles to run (default: benchmarks/regression)",
    )
    suite_parser.add_argument("--json", action="store_true", help="Print the suite summary as JSON")

    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            return asyncio.run(_export_async(args))
        if args.command == "run":
            return _run(args)
        if args.command == "run-suite":
            return _run_suite(args)
        return _compare(args)
    except Exception as exc:  # operational failure, not a regression verdict
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
