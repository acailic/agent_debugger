"""Tests for scripts/fetch_who_when.py — corpora seeding from the dataset layout."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "who_when"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_who_when", _REPO_ROOT / "scripts" / "fetch_who_when.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_who_when"] = module
    spec.loader.exec_module(module)
    return module


fetch_who_when = _load_module()

_HARNESS_KEYS = {"question_ID", "history", "mistake_agent", "mistake_step", "mistake_reason"}


def test_run_seeds_jsonl_and_manifest_from_fixture_source(tmp_path: Path):
    # Copy to a non-git directory so commit_sha is exercised as null.
    source = tmp_path / "source"
    shutil.copytree(_FIXTURE_ROOT, source)
    out_dir = tmp_path / "out"
    manifest = fetch_who_when.run(source, out_dir)

    ag_lines = (out_dir / "algorithm_generated.jsonl").read_text(encoding="utf-8").splitlines()
    hc_lines = (out_dir / "hand_crafted.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ag_lines) == 1
    assert len(hc_lines) == 2

    ag_records = [json.loads(line) for line in ag_lines]
    hc_records = [json.loads(line) for line in hc_lines]
    for record in [*ag_records, *hc_records]:
        assert set(record.keys()) == _HARNESS_KEYS
        for message in record["history"]:
            assert set(message.keys()) == {"content", "name", "role"}

    # Hand-Crafted messages keep name: null and the role variants as-is.
    variant = next(r for r in hc_records if r["question_ID"] == "fx-hc-2")
    assert [m["role"] for m in variant["history"]] == [
        "human",
        "Orchestrator (thought)",
        "Coder",
        "Orchestrator (-> WebSurfer)",
        "Orchestrator (thought)",
        "WebSurfer",
    ]
    assert all(m["name"] is None for m in variant["history"])

    # Records sorted by question_ID within each split.
    assert [r["question_ID"] for r in hc_records] == ["fx-hc-1", "fx-hc-2"]

    manifest_on_disk = json.loads((out_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest_on_disk == manifest
    assert manifest["source_repo"] == fetch_who_when.SOURCE_REPO
    # Fixtures are not a git repo -> null commit sha.
    assert manifest["commit_sha"] is None
    assert manifest["generated_at"]
    assert manifest["splits"]["algorithm_generated"]["source_files"] == 1
    assert manifest["splits"]["algorithm_generated"]["records"] == 1
    assert manifest["splits"]["hand_crafted"]["source_files"] == 2
    assert manifest["splits"]["hand_crafted"]["records"] == 2
    assert manifest["total_records"] == 3


def test_run_jsonl_is_compact_and_sorted(tmp_path: Path):
    source = tmp_path / "source"
    shutil.copytree(_FIXTURE_ROOT, source)
    fetch_who_when.run(source, tmp_path / "out")

    text = (tmp_path / "out" / "hand_crafted.jsonl").read_text(encoding="utf-8")
    assert text.endswith("\n")
    lines = text.splitlines()
    assert lines == sorted(lines, key=lambda line: json.loads(line)["question_ID"])
    for line in lines:
        assert json.dumps(json.loads(line), ensure_ascii=False, separators=(",", ":")) == line


def test_run_fails_loudly_on_missing_source(tmp_path: Path):
    with pytest.raises(fetch_who_when.FetchError) as excinfo:
        fetch_who_when.run(Path("/nonexistent"), tmp_path)
    assert "/nonexistent" in str(excinfo.value)


def test_run_fails_loudly_on_missing_split_dir(tmp_path: Path):
    with pytest.raises(fetch_who_when.FetchError) as excinfo:
        fetch_who_when.run(tmp_path, tmp_path / "out")
    assert "missing split directory" in str(excinfo.value)
