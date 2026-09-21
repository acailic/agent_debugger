"""CI gate: the committed regression baseline must pass on the current engine.

``benchmarks/regression/`` holds committed incident bundles — sanitized,
content-hashed fixtures exported by the regression lab. These tests replay
every bundle in that directory through the *current*
:class:`~collector.audit.SessionAuditEngine` (in-process; no subprocess, no
database) and fail on any assertion drift. That makes engine and analysis
changes regression-gated wherever the suite runs — locally and in CI's
existing matrix — with zero new CI configuration.

A drifted engine fails here with the per-assertion diff (expected vs actual
per pinned path); ``test_gate_failure_output_names_the_drifted_assertion``
pins that behaviour using an engine double that flips one output field.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from collector.audit import SessionAuditEngine
from collector.regression.bundles import content_hash, load_bundle
from collector.regression.runner import run_bundle

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLI = _REPO_ROOT / "scripts" / "regression_cli.py"
SUITE_DIR = _REPO_ROOT / "benchmarks" / "regression"
COMMITTED_BASELINE = SUITE_DIR / "baseline_session.json"

#: The committed baseline's synthetic session — pinned so an accidental
#: rename/move of the fixture is caught as a missing gate, not a silent skip.
_BASELINE_SESSION_ID = "regbase-session-0001"


def _failure_diff(result: dict) -> str:
    """Render the runner's per-assertion rows for a failing run result."""
    lines = [
        f"bundle {result['bundle_hash']}: {result['passed']}/{result['total']} assertions "
        f"passed — the current engine drifted from the committed baseline:"
    ]
    lines.extend(
        f"  [{row['kind']}] {row['path']}: expected {row['expected']!r}, got {row['actual']!r}"
        for row in result["assertions"]
        if not row["passed"]
    )
    return "\n".join(lines)


def _committed_bundles() -> list[Path]:
    return sorted(SUITE_DIR.glob("*.json"))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_committed_baseline_bundle_exists() -> None:
    """The gate must have something to gate on — never silently skip."""
    assert COMMITTED_BASELINE.is_file(), (
        f"Missing committed regression baseline {COMMITTED_BASELINE}; regenerate it with "
        "`.venv-ci/bin/python scripts/seed_regression_baseline.py` and commit the result."
    )
    bundle = load_bundle(COMMITTED_BASELINE)
    assert bundle["session"]["id"] == _BASELINE_SESSION_ID
    assert bundle["sanitized"] is True
    # Meaningful contract, not a vacuous one: every assertion kind the
    # exporter derives, including claim rows and failure findings.
    kinds = {assertion["kind"] for assertion in bundle["expected_assertions"]}
    assert kinds == {
        "trust_band",
        "trust_score",
        "claim_verification_status",
        "failure_event_ids",
        "failure_narrative_mechanism",
        "summary_verdict",
    }
    assert any(
        assertion["kind"] == "claim_verification_status"
        and assertion["expected"] == "verified"
        for assertion in bundle["expected_assertions"]
    )
    assert any(
        assertion["kind"] == "claim_verification_status"
        and assertion["expected"] == "unsupported"
        for assertion in bundle["expected_assertions"]
    )
    failure_ids = next(
        assertion["expected"]
        for assertion in bundle["expected_assertions"]
        if assertion["kind"] == "failure_event_ids"
    )
    assert failure_ids, "baseline must demonstrate a failure (error chain)"


@pytest.mark.parametrize(
    "bundle_path",
    _committed_bundles(),
    ids=lambda path: path.name,
)
def test_committed_regression_bundle_passes_on_current_engine(bundle_path: Path) -> None:
    """Replay a committed bundle in-process; fail with the assertion diff.

    ``load_bundle`` verifies the content hash first, so a fixture edited
    after export fails here as tampering rather than evaluating to "pass".
    """
    result = run_bundle(load_bundle(bundle_path))
    assert result["verdict"] == "pass", _failure_diff(result)
    assert result["failed"] == 0


def test_gate_covers_every_bundle_in_the_suite_directory() -> None:
    """New baselines land in the gate automatically — and the dir is never empty."""
    bundles = _committed_bundles()
    assert COMMITTED_BASELINE in bundles


# ---------------------------------------------------------------------------
# The gate's failure output (pinned with an engine double)
# ---------------------------------------------------------------------------


class _BandFlippedEngine:
    """A drifted engine: identical to the real one except the trust band."""

    def __init__(self) -> None:
        self._inner = SessionAuditEngine()

    def audit(self, events, checkpoints=None, **kwargs):
        report = self._inner.audit(events, checkpoints, **kwargs)
        report["trust"]["band"] = "low" if report["trust"]["band"] != "low" else "high"
        return report


def test_gate_failure_output_names_the_drifted_assertion() -> None:
    """A drifted engine fails the gate and the message names exactly the drift."""
    result = run_bundle(load_bundle(COMMITTED_BASELINE), engine=_BandFlippedEngine())

    assert result["verdict"] == "fail"
    diff = _failure_diff(result)
    assert "trust.band" in diff
    assert "expected" in diff and "got" in diff
    # The wrapper's own assertion path renders the same diff.
    with pytest.raises(AssertionError, match="trust.band"):
        assert result["verdict"] == "pass", _failure_diff(result)


# ---------------------------------------------------------------------------
# run-suite CLI (the multi-bundle verdict)
# ---------------------------------------------------------------------------


def test_cli_run_suite_passes_on_committed_baselines() -> None:
    result = subprocess.run(
        [sys.executable, str(_CLI), "run-suite", "--dir", str(SUITE_DIR)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Suite verdict PASS" in result.stdout
    assert COMMITTED_BASELINE.name in result.stdout


def test_cli_run_suite_fails_when_any_bundle_fails(tmp_path: Path) -> None:
    """One failing bundle in the directory fails the combined verdict."""
    bundle = json.loads(COMMITTED_BASELINE.read_text(encoding="utf-8"))
    target = next(
        assertion
        for assertion in bundle["expected_assertions"]
        if assertion["kind"] == "summary_verdict"
    )
    target["expected"] = "pass" if target["expected"] != "pass" else "review"
    bundle["content_hash"] = content_hash(bundle)  # the reviewed-edit re-sign path
    (tmp_path / "drifted.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_CLI), "run-suite", "--dir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Suite verdict FAIL" in result.stdout
    assert "summary.verdict" in result.stdout


def test_cli_run_suite_empty_directory_is_an_operational_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_CLI), "run-suite", "--dir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 2
    assert "no *.json incident bundles" in result.stderr
