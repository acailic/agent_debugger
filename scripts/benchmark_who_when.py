#!/usr/bin/env python3
"""Who&When benchmark CLI.

Runs the deterministic previous-message failure-localization heuristic
against the public Who&When annotated failure logs and prints separately
named agent / step / joint / abstention metrics with denominators.

Usage:
    python scripts/benchmark_who_when.py --data PATH [PATH ...] [--step-scope global|agent] [--out PATH]
    python scripts/benchmark_who_when.py --self-test   # offline contract smoke test

Dataset: https://github.com/mingyin1/Agents_Failure_Attribution
(Hugging Face: Kevin355/Who_and_When). Records are JSONL with a
``history`` of {content, name, role} messages plus ``mistake_agent`` /
``mistake_step`` annotations. By default ``mistake_step`` is read as the
0-based index into the WHOLE history — the pinned upstream convention
(see collector/audit/who_when.py). ``--step-scope agent`` reproduces the
superseded 2026-09-15 per-agent misreading and is not comparable. The
dataset is not vendored here — seed the corpora with
``scripts/fetch_who_when.py`` (pinned to the upstream commit) and point
--data at the JSONL files.

Metric contract: exact agent equality, exact independent step equality,
joint = both; denominator is the total record count including
abstentions. The paper's 53.5% agent / 14.2% step LLM-judge numbers use
substring matching on a different input-information protocol, so they are
context, not a matched baseline.

``--out PATH`` writes a versioned result manifest: corpus file hashes and
counts, upstream + evaluator revisions, the metric convention, validation
findings, aggregate metrics with numerators/denominators, and frozen
per-record prediction rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.audit.who_when import (  # noqa: E402
    DEFAULT_STEP_SCOPE,
    UPSTREAM_COMMIT,
    UPSTREAM_REPO,
    evaluate_records,
    load_who_when_records,
)

RESULT_SCHEMA_VERSION = 1

#: Offline smoke fixtures. The first encodes the heuristic's contract —
#: the mistake precedes the first visible error signal, so the predictor
#: names the agent and global step exactly. The second has no error
#: signal at all and must abstain.
_SELF_TEST_RECORDS = [
    {
        "question_ID": "selftest-localized",
        "history": [
            {"content": "Please compute the total.", "name": "Planner", "role": "user"},
            {
                "content": "result = compute(total  # wrong argument order",
                "name": "Verifier_Expert",
                "role": "assistant",
            },
            {
                "content": (
                    "Traceback (most recent call last):\n  File \"x.py\"\n"
                    "TypeError: compute() takes 2 positional arguments"
                ),
                "name": "Computer_terminal",
                "role": "assistant",
            },
        ],
        "mistake_agent": "Verifier_Expert",
        "mistake_step": "1",
        "mistake_reason": "The Python code passes the arguments in the wrong order.",
    },
    {
        "question_ID": "selftest-abstain",
        "history": [
            {"content": "Look up the answer.", "name": "Planner", "role": "user"},
            {"content": "I will get right on it.", "name": "Researcher", "role": "assistant"},
        ],
        "mistake_agent": "Planner",
        "mistake_step": "0",
        "mistake_reason": "No work performed.",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_commit() -> tuple[str | None, bool]:
    """HEAD commit of this repository, and whether tracked files differ from it."""
    root = Path(__file__).resolve().parent.parent
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return head, bool(status)
    except (subprocess.CalledProcessError, OSError):
        return None, False


def _corpus_entry(path: Path, records: list[dict]) -> dict:
    """Per-file descriptor with hash, count and any sibling seeding manifest info."""
    entry: dict = {
        "path": str(path),
        "sha256": _sha256(path),
        "records": len(records),
    }
    manifest_path = path.parent / "MANIFEST.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return entry
        entry["source_commit"] = manifest.get("commit_sha")
        for split in manifest.get("splits", {}).values():
            if split.get("file") == path.name:
                entry["split"] = split.get("source_dir")
                break
    return entry


def _collect_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for entry in inputs:
        if entry.is_dir():
            paths.extend(sorted(entry.rglob("*.jsonl")))
        else:
            paths.append(entry)
    return paths


def _load_with_sources(paths: list[Path]) -> tuple[list[dict], list[dict]]:
    """Load records file-by-file so each row can carry its source file."""
    records: list[dict] = []
    corpus: list[dict] = []
    for path in paths:
        file_records = load_who_when_records([path])
        corpus.append(_corpus_entry(path, file_records))
        records.extend(file_records)
    return records, corpus


def build_result_manifest(results: dict, corpus: list[dict], step_scope: str) -> dict:
    commit, dirty = _repo_commit()
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": "who_and_when",
        "upstream": {
            "repo": UPSTREAM_REPO,
            "pinned_commit": UPSTREAM_COMMIT,
            "paper_reference": "Zhang et al., Who&When, ICML 2025 (arXiv:2505.00212)",
        },
        "evaluator": {
            "module": "collector.audit.who_when",
            "repo_commit": commit,
            "repo_dirty": dirty,
            "heuristic": "message-immediately-before-first-error-marker",
            "engine": "standalone text-marker heuristic; not SessionAuditEngine/CausalAnalyzer",
            "step_scope": step_scope,
        },
        "metric_convention": {
            "step_indexing": (
                "global 0-based history index (upstream prompt enumerates the whole "
                "conversation; 'agent' scope reproduces the superseded 2026-09-15 result)"
                if step_scope == "global"
                else "per-agent 0-based index — superseded misreading, kept only for legacy reproduction"
            ),
            "agent_match": "exact speaker-name equality",
            "step_match": "exact integer equality, scored independently of agent",
            "joint_match": "agent_match AND step_match",
            "denominator": "total records, including abstentions",
            "paper_comparability": (
                "paper LLM-judge numbers use substring membership and a different "
                "input-information protocol; not a matched baseline"
            ),
        },
        "corpus": {"files": corpus, "total_records": results["total"]},
        "validation": results["validation"],
        "totals": {
            "total": results["total"],
            "localized": results["localized"],
            "abstained": results["abstained"],
            "agent_exact": results["agent_exact"],
            "step_exact": results["step_exact"],
            "joint_exact": results["joint_exact"],
        },
        "metrics": results["metrics"],
        "rows": results["rows"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        nargs="+",
        type=Path,
        help="Who&When JSONL file(s) or directories containing them",
    )
    parser.add_argument(
        "--step-scope",
        choices=["global", "agent"],
        default=DEFAULT_STEP_SCOPE,
        help=(
            "Interpret mistake_step as a global history index (upstream default) "
            "or per-agent (superseded 2026-09-15 protocol; not comparable)"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run offline on bundled synthetic records to verify the pipeline contract",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write the versioned result manifest (with frozen per-record rows) to this JSON file",
    )
    args = parser.parse_args()

    corpus: list[dict] = []
    if args.self_test:
        records = _SELF_TEST_RECORDS
    else:
        if not args.data:
            parser.error("--data is required unless --self-test is given")
        paths = _collect_paths(args.data)
        if not paths:
            print(f"No JSONL files found under {args.data}", file=sys.stderr)
            return 2
        records, corpus = _load_with_sources(paths)

    results = evaluate_records(records, step_scope=args.step_scope)

    if not args.self_test:
        invalid = results["validation"]["invalid_count"]
        if invalid:
            print(
                f"ERROR: {invalid} annotation(s) invalid under step_scope={args.step_scope} "
                "(non-integer or out of range); refusing to publish metrics:",
                file=sys.stderr,
            )
            for issue in results["validation"]["invalid"][:10]:
                print(f"  {issue}", file=sys.stderr)
            return 2
        mismatched = results["validation"]["speaker_mismatch_count"]
        if mismatched:
            print(
                f"note: {mismatched} annotation(s) point at a step spoken by another agent "
                "(upstream annotation noise; reported in the manifest)"
            )

    metrics = results["metrics"]
    print(f"Who&When evaluation — {results['total']} record(s), step_scope={results['step_scope']}")
    print(f"  localized          : {results['localized']}/{results['total']}")
    print(f"  abstained          : {results['abstained']}/{results['total']}")
    for name, rate in metrics.items():
        print(f"  {name:34s}: {rate['numerator']}/{rate['denominator']} = {rate['value']:.1%}")
    print(
        "  context (not a matched baseline): paper best LLM judge 53.5% agent / 14.2% step, "
        "substring-scored on a different protocol"
    )

    if args.self_test:
        by_id = {row["question_ID"]: row for row in results["rows"]}
        localized_row = by_id["selftest-localized"]
        assert localized_row["agent_match"] and localized_row["step_match"], results["rows"]
        assert localized_row["joint_match"], results["rows"]
        assert by_id["selftest-abstain"]["abstained"] is True, results["rows"]
        assert results["total"] == 2 and results["localized"] == 1 and results["abstained"] == 1
        assert results["agent_exact"] == 1 and results["step_exact"] == 1 and results["joint_exact"] == 1
        assert localized_row["predicted_agent"] == "Verifier_Expert"
        assert localized_row["predicted_step"] == 1 and localized_row["truth_step"] == 1
        print("self-test OK")

    if args.out:
        manifest = build_result_manifest(results, corpus, args.step_scope)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"results written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
