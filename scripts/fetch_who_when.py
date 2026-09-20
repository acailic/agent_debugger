#!/usr/bin/env python3
"""Seed Who&When benchmark corpora as normalized JSONL.

Fetches the public Who&When dataset (github.com/mingyin1/Agents_Failure_Attribution),
normalizes every record into the harness schema documented in
``collector/audit/who_when.py``, and writes two compact JSONL corpora plus a
MANIFEST.json recording the source repo, requested and resolved commit shas,
per-file sha256 hashes, and counts. The default fetch is pinned to the
upstream revision the benchmark protocol references; pass ``--commit`` to
evaluate a different revision explicitly.

Usage (run from the repo root):

    uv run scripts/fetch_who_when.py                                # pinned fetch to a temp dir
    uv run scripts/fetch_who_when.py --source /path/to/existing/clone
    uv run scripts/fetch_who_when.py --out benchmarks/corpora/who_when

Output dir default: ``benchmarks/corpora/who_when`` (gitignored runtime state).
The output is deterministic across runs for a given source: records are sorted
by ``question_ID`` and serialized compactly; only MANIFEST's ``generated_at``
varies between runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collector.audit.who_when import UPSTREAM_COMMIT, UPSTREAM_REPO  # noqa: E402

SOURCE_REPO = UPSTREAM_REPO
PINNED_COMMIT = UPSTREAM_COMMIT

SPLITS: dict[str, str] = {
    "algorithm_generated": "Who&When/Algorithm-Generated",
    "hand_crafted": "Who&When/Hand-Crafted",
}

DEFAULT_OUT = Path("benchmarks/corpora/who_when")


class FetchError(RuntimeError):
    """Raised with a human-readable message when the source is unusable."""


def _normalize(raw: dict) -> dict:
    """Project one source record onto exactly the harness schema."""
    return {
        "question_ID": str(raw.get("question_ID") or raw.get("question_id") or ""),
        "history": [
            {
                "content": str(message.get("content") or ""),
                "name": message.get("name"),
                "role": message.get("role"),
            }
            for message in raw.get("history") or []
        ],
        "mistake_agent": str(raw.get("mistake_agent") or ""),
        "mistake_step": str(raw.get("mistake_step") or ""),
        "mistake_reason": str(raw.get("mistake_reason") or ""),
    }


def _commit_sha(source: Path) -> str | None:
    """Head commit of the source repo, or None when it is not a git repo."""
    try:
        out = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_pinned(target: Path, commit: str) -> None:
    """Materialize exactly ``commit`` from SOURCE_REPO into ``target``.

    Fetches the single revision (GitHub allows fetching arbitrary SHAs) so the
    seeded corpus is reproducible regardless of upstream's moving HEAD.
    """
    target.mkdir(parents=True)
    steps = [
        ["git", "init", "-q", str(target)],
        ["git", "-C", str(target), "remote", "add", "origin", SOURCE_REPO],
        ["git", "-C", str(target), "fetch", "--depth", "1", "origin", commit],
        ["git", "-C", str(target), "checkout", "--quiet", "FETCH_HEAD"],
    ]
    for step in steps:
        result = subprocess.run(step, capture_output=True, text=True)
        if result.returncode != 0:
            raise FetchError(
                f"pinned fetch failed at {' '.join(step[:3])}…:\n{result.stderr.strip()}"
            )


def run(
    source: Path,
    out_dir: Path,
    *,
    requested_commit: str | None = None,
) -> dict:
    """Normalize the dataset at ``source`` into ``out_dir``; return the manifest.

    Raises FetchError with a clear message when the source is missing or a
    split directory is absent/empty.
    """
    if not source.is_dir():
        raise FetchError(f"source directory does not exist: {source}")

    out_dir.mkdir(parents=True, exist_ok=True)
    splits_manifest: dict[str, dict] = {}
    total_records = 0

    for split_name, rel_dir in SPLITS.items():
        split_path = source / rel_dir
        if not split_path.is_dir():
            raise FetchError(f"missing split directory: {split_path}")
        files = sorted(split_path.glob("*.json"))
        if not files:
            raise FetchError(f"no .json files under {split_path}")

        records: list[dict] = []
        for file_path in files:
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FetchError(f"cannot parse JSON record {file_path}: {exc}") from exc
            records.append(_normalize(raw))

        ids = [record["question_ID"] for record in records]
        duplicates = sorted({q_id for q_id in ids if ids.count(q_id) > 1})
        if duplicates:
            raise FetchError(f"duplicate question_ID in {rel_dir}: {duplicates}")

        records.sort(key=lambda record: record["question_ID"])
        jsonl_path = out_dir / f"{split_name}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        splits_manifest[split_name] = {
            "source_dir": rel_dir,
            "source_files": len(files),
            "records": len(records),
            "file": jsonl_path.name,
            "sha256": _sha256(jsonl_path),
        }
        total_records += len(records)

    resolved = _commit_sha(source)
    if requested_commit and resolved and resolved != requested_commit:
        print(
            f"warning: source HEAD {resolved} != requested {requested_commit}; "
            "seeding proceeds and both are recorded in the manifest",
            file=sys.stderr,
        )
    manifest = {
        "source_repo": SOURCE_REPO,
        "requested_commit": requested_commit,
        "commit_sha": resolved,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "splits": splits_manifest,
        "total_records": total_records,
    }
    manifest_path = out_dir / "MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help="Existing clone root (the directory containing 'Who&When/'); default: pinned fetch",
    )
    parser.add_argument(
        "--commit",
        default=PINNED_COMMIT,
        help=f"Upstream revision to fetch (default: pinned {PINNED_COMMIT[:12]}…)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT}, relative to cwd — run from repo root)",
    )
    args = parser.parse_args()

    try:
        if args.source is not None:
            manifest = run(args.source, args.out, requested_commit=args.commit)
        else:
            with tempfile.TemporaryDirectory(prefix="who_when_fetch_") as tmp:
                clone_path = Path(tmp) / "repo"
                print(f"Fetching {SOURCE_REPO} at pinned commit {args.commit}…")
                try:
                    _fetch_pinned(clone_path, args.commit)
                except FetchError as exc:
                    print(f"{exc}", file=sys.stderr)
                    print(
                        "Hint: pass --source /path/to/existing/clone "
                        "(e.g. a manual clone of the repo).",
                        file=sys.stderr,
                    )
                    return 2
                manifest = run(clone_path, args.out, requested_commit=args.commit)
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for name, split in manifest["splits"].items():
        out_file = args.out / split["file"]
        print(f"{name}: {split['records']} record(s) from {split['source_files']} file(s) -> {out_file}")
    print(f"MANIFEST: {args.out / 'MANIFEST.json'} (commit {manifest['commit_sha'] or 'n/a'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
