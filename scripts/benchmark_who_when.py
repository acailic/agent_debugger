#!/usr/bin/env python3
"""Who&When benchmark CLI.

Runs the audit engine's deterministic failure localization against the
public Who&When annotated failure logs and prints agent/step accuracy.

Usage:
    python scripts/benchmark_who_when.py --data PATH [PATH ...] [--step-scope agent|global]
    python scripts/benchmark_who_when.py --self-test   # offline smoke test

Dataset: https://github.com/mingyin1/Agents_Failure_Attribution
(Hugging Face: Kevin355/Who_and_When). Records are JSONL with a
``history`` of {content, name, role} messages plus ``mistake_agent`` /
``mistake_step`` annotations. The dataset is not vendored here — clone or
download it, then point --data at the JSONL files.

Reference numbers from the paper: best LLM-judge method reaches 53.5%
agent accuracy / 14.2% step accuracy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.audit.who_when import evaluate_records, load_who_when_records  # noqa: E402

_SELF_TEST_RECORDS = [
    {
        "question_ID": "selftest-pass",
        "history": [
            {"content": "Please compute the total.", "name": "Planner", "role": "user"},
            {"content": "Running the computation.", "name": "Computer_terminal", "role": "assistant"},
            {
                "content": "Traceback (most recent call last):\n  File \"x.py\"\nSyntaxError: invalid syntax",
                "name": "Verifier_Expert",
                "role": "assistant",
            },
        ],
        "mistake_agent": "Verifier_Expert",
        "mistake_step": "1",
        "mistake_reason": "The Python code is incorrect.",
    },
    {
        "question_ID": "selftest-none",
        "history": [
            {"content": "Look up the answer.", "name": "Planner", "role": "user"},
        ],
        "mistake_agent": "Planner",
        "mistake_step": "1",
        "mistake_reason": "No work performed.",
    },
]


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
        choices=["agent", "global"],
        default="agent",
        help="Interpret mistake_step per-agent (default) or as a global message index",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run offline on bundled synthetic records to verify the pipeline",
    )
    args = parser.parse_args()

    if args.self_test:
        records = _SELF_TEST_RECORDS
    else:
        if not args.data:
            parser.error("--data is required unless --self-test is given")
        paths: list[Path] = []
        for entry in args.data:
            if entry.is_dir():
                paths.extend(sorted(entry.rglob("*.jsonl")))
            else:
                paths.append(entry)
        if not paths:
            print(f"No JSONL files found under {args.data}", file=sys.stderr)
            return 2
        records = load_who_when_records(paths)

    results = evaluate_records(records, step_scope=args.step_scope)

    print(f"Who&When evaluation — {results['total']} record(s), step_scope={results['step_scope']}")
    print(f"  localized any step : {results['localized_any_step']}/{results['total']}")
    print(f"  agent accuracy     : {results['agent_accuracy']:.1%}  (paper best LLM judge: 53.5%)")
    print(f"  step accuracy      : {results['step_accuracy']:.1%}  (paper best LLM judge: 14.2%)")
    if args.self_test:
        first = results["rows"][0]
        assert first["agent_match"] and first["step_match"], results["rows"]
        print("self-test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
