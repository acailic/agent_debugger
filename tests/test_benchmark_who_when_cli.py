"""Command-level contract tests for scripts/benchmark_who_when.py.

The 2026-09-19 audit found the CLI --self-test failing while evaluator
unit tests passed; these subprocess tests pin the entry point itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLI = _REPO_ROOT / "scripts" / "benchmark_who_when.py"

_VALID_RECORD = {
    "question_ID": "cli-1",
    "history": [
        {"content": "Compute the total.", "name": "Planner", "role": "user"},
        {"content": "result = compute(total", "name": "Verifier_Expert", "role": "assistant"},
        {
            "content": "Traceback (most recent call last):\nSyntaxError: invalid syntax",
            "name": "Terminal",
            "role": "assistant",
        },
    ],
    "mistake_agent": "Verifier_Expert",
    "mistake_step": "1",
    "mistake_reason": "The Python code is incorrect.",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CLI), *args],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
    )


def test_self_test_passes_and_states_the_contract():
    result = _run("--self-test")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "self-test OK" in result.stdout
    for name in (
        "agent_accuracy_exact",
        "step_accuracy_exact_independent",
        "joint_accuracy_exact",
        "abstention_rate",
    ):
        assert name in result.stdout


def test_self_test_writes_versioned_manifest(tmp_path: Path):
    out = tmp_path / "results" / "selftest.json"
    result = _run("--self-test", "--out", str(out))

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["evaluator"]["step_scope"] == "global"
    assert manifest["evaluator"]["heuristic"]
    assert manifest["upstream"]["pinned_commit"].startswith("b2bae5c")
    assert manifest["metric_convention"]["denominator"].startswith("total records")
    assert manifest["metrics"]["joint_accuracy_exact"]["numerator"] == 1
    assert len(manifest["rows"]) == 2
    assert {row["question_ID"] for row in manifest["rows"]} == {
        "selftest-localized", "selftest-abstain",
    }


def test_invalid_annotations_block_metric_publication(tmp_path: Path):
    broken = dict(_VALID_RECORD, mistake_step="9")
    data = tmp_path / "broken.jsonl"
    data.write_text(json.dumps(broken) + "\n", encoding="utf-8")

    result = _run("--data", str(data))

    assert result.returncode == 2
    assert "invalid" in result.stderr
    assert "step_out_of_range" in result.stderr


def test_full_run_reports_named_metrics_with_denominators(tmp_path: Path):
    data = tmp_path / "valid.jsonl"
    data.write_text(json.dumps(_VALID_RECORD) + "\n", encoding="utf-8")
    out = tmp_path / "manifest.json"

    result = _run("--data", str(data), "--out", str(out))

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(out.read_text(encoding="utf-8"))
    corpus_file = manifest["corpus"]["files"][0]
    assert corpus_file["records"] == 1
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    assert corpus_file["sha256"] == digest
    assert manifest["validation"]["invalid_count"] == 0
    row = manifest["rows"][0]
    assert row["joint_match"] is True
    assert row["predicted_step"] == 1
