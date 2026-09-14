# Plan — M2.4: Seeded Who&When benchmark corpora + two harness correctness fixes

## Context

The Who&When harness (`collector/audit/who_when.py` + `scripts/benchmark_who_when.py`) scores the audit engine's deterministic failure localization against the public benchmark. Today every run requires a manual clone and `--data` plumbing. This change seeds reproducible corpora on disk, fixes two correctness bugs found while preparing the full run, and wires a `just who-when` recipe.

### Verified facts (from the task; spot-checked during planning)

- Dataset repo: `github.com/mingyin1/Agents_Failure_Attribution`, dir `Who&When`, subdirs `Algorithm-Generated` and `Hand-Crafted`. Each file is ONE pretty-printed JSON object.
- Algorithm-Generated records carry the speaker in `history[].name`. `mistake_step` is the **0-based** index of the erroneous message among the mistake agent's own messages (verified: 2-agent-message record with error at raw index 1 is annotated step=1 — 1-based would require 2; single-agent-message record at index 0 is annotated step=0).
- Hand-Crafted records have `history[].name = null` and carry the speaker in `history[].role`, including variants like `Orchestrator (thought)` and `Orchestrator (-> WebSurfer)`. The base name before the parenthetical matches the `mistake_agent` annotations. (Spot-check confirmed: 0/58 HC files have any non-null `name`.)

### ⚠️ Discrepancy the builder must know about (do not "fix" by filtering)

The task text says Algorithm-Generated has **99** files. The actual clone on this machine — `/tmp/ww_repo`, commit `b2bae5c5b06d681d04ea5e9b63b7a30525c04925` — has **126** files in `Who&When/Algorithm-Generated` (numeric IDs 1..126, all parse as single JSON records with non-empty `history` and `mistake_agent`, 126 unique `question_ID`s) and **58** in `Who&When/Hand-Crafted`. 126 + 58 = 184, which matches the "184 annotated failure logs" already stated in the module docstring and docs. The "99" appears to be a miscount from the earlier session.

**Directive:** `scripts/fetch_who_when.py` must NOT hardcode or filter toward 99. It records the counts it actually finds. The done-gate "counts matching the source" means: MANIFEST file counts and JSONL record counts equal what is in the given `--source` (expect 126/58 for `/tmp/ww_repo`). Surface this discrepancy in the final builder report so the operator isn't surprised.

---

## Work items

### 1. `scripts/fetch_who_when.py` (new)

CLI that seeds `benchmarks/corpora/who_when/`. No new dependencies (stdlib + `git` subprocess).

**Interface:**
- `--source PATH` — use an existing clone (its root, i.e. the dir containing `Who&When/`). Default: clone `https://github.com/mingyin1/Agents_Failure_Attribution` into a `tempfile.TemporaryDirectory` (`git clone --depth 1`).
- `--out PATH` — output dir, default `benchmarks/corpora/who_when` (relative to cwd; document "run from repo root").

**Behavior:**
- For each split in `{"algorithm_generated": "Who&When/Algorithm-Generated", "hand_crafted": "Who&When/Hand-Crafted"}`:
  - `sorted((source / reldir).glob("*.json"))`, `json.loads` each file (one object per file).
  - Normalize each record into exactly the harness schema documented in `who_when.py`:
    ```python
    {
        "question_ID": str(raw.get("question_ID") or raw.get("question_id") or ""),
        "history": [
            {"content": str(m.get("content") or ""), "name": m.get("name"), "role": m.get("role")}
            for m in raw.get("history") or []
        ],
        "mistake_agent": str(raw.get("mistake_agent") or ""),
        "mistake_step": str(raw.get("mistake_step") or ""),
        "mistake_reason": str(raw.get("mistake_reason") or ""),
    }
    ```
    Preserve `name: null` and role variants **as-is** — the harness (work item 2) is what normalizes speakers at read time. Drop the non-harness fields (`question`, `ground_truth`, `is_correct`/`is_corrected`, `level`, `system_prompt`) to keep files compact.
  - Sort records by `question_ID` (plain string sort — deterministic, works for both splits). Assert no duplicate `question_ID` within a split; fail loudly with the offending IDs if violated.
  - Write `<out>/algorithm_generated.jsonl` / `<out>/hand_crafted.jsonl`: one compact line per record — `json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"`, file written with `encoding="utf-8"`. Trailing newline at EOF.
- Write `<out>/MANIFEST.json`:
    ```json
    {
      "source_repo": "https://github.com/mingyin1/Agents_Failure_Attribution",
      "commit_sha": "<git -C <source> rev-parse HEAD, or null when not a git repo>",
      "generated_at": "<UTC ISO-8601>",
      "splits": {
        "algorithm_generated": {"source_dir": "Who&When/Algorithm-Generated", "source_files": N, "records": N, "file": "algorithm_generated.jsonl"},
        "hand_crafted": {"source_dir": "Who&When/Hand-Crafted", "source_files": N, "records": N, "file": "hand_crafted.jsonl"}
      },
      "total_records": N
    }
    ```
  `commit_sha` retrieval must tolerate a non-git `--source` (return `null`) — this keeps fixture-driven tests and zip-extracted sources working.
- Error handling: if `--source` doesn't exist, or either split dir is missing/empty, print a clear message to stderr naming exactly what's missing and `return 2` / `sys.exit(2)`. If the default clone fails, print a clear message suggesting `--source /path/to/existing/clone`.
- Structure the script with a testable `run(source: Path, out_dir: Path) -> dict` (returns the manifest) separate from `main()`/argparse, so tests can import and call it directly.

### 2. Harness fixes — `collector/audit/who_when.py`

**(a) Speaker extraction: name OR role, with role-variant normalization.** Add:

```python
import re

_ROLE_PARENTHETICAL = re.compile(r"\s*\([^)]*\)$")

def _speaker_of(message: dict[str, Any]) -> str:
    """name when present; otherwise role with one trailing parenthetical stripped."""
    name = message.get("name")
    if name:
        return str(name)
    role = str(message.get("role") or "").strip()
    if role:
        return _ROLE_PARENTHETICAL.sub("", role).strip() or role
    return "unknown"
```

Use it in `history_to_events` (`speaker = _speaker_of(message)`; it already flows into both the event `name` and `data["speaker"]`, so `_step_index_of` needs no change for this). Stripping applies to the role-derived speaker only; AG names never carry parentheticals, so keep the change scoped and conservative.

**(b) 0-based step indexing.**
- `_step_index_of`: fix the docstring to "0-based step index"; global scope returns `idx` (drop the `+ 1`); agent scope returns `idx` (drop the `+ 1`).
- Module docstring: rewrite the "Step indexing" paragraph — `mistake_step` is the **0-based** index of the erroneous message among the messages spoken by `mistake_agent`; `step_scope="global"` uses the 0-based whole-history index. Also add one sentence noting Hand-Crafted records carry the speaker in `role` (parenthetical variants normalized).
- Leave `_ERROR_MARKERS` and the localization logic untouched.

### 3. `scripts/benchmark_who_when.py` — small required updates

- `_SELF_TEST_RECORDS`: both records encode 1-based steps that become wrong under 0-based. Change `"mistake_step": "1"` → `"0"` in both (Verifier_Expert's single message / Planner's single message are each index 0). The self-test assert (`agent_match and step_match`) must still pass.
- Add `--out PATH`: after evaluation, write the full results dict (including `rows`) as `json.dumps(results, indent=2, ensure_ascii=False) + "\n"` and print where it was written. The recipe depends on this.
- Docstring: mention `scripts/fetch_who_when.py` as the way to seed `--data`, and the new `--out`.

### 4. Fixtures — `tests/fixtures/who_when/` (new, committed; mirrors the dataset layout)

Layout doubles as a fake `--source` for the fetch test:

```
tests/fixtures/who_when/Who&When/Algorithm-Generated/fx_ag_multi.json
tests/fixtures/who_when/Who&When/Hand-Crafted/fx_hc_role.json
tests/fixtures/who_when/Who&When/Hand-Crafted/fx_hc_variant.json
```

Hand-written, tiny, invented content (no dataset redistribution). Exact contents:

`fx_ag_multi.json` — name-speaker, multi-message agent, step points at the error message:
```json
{
  "question_ID": "fx-ag-1",
  "history": [
    {"content": "Split the word list and count each letter.", "name": "Planner", "role": "user"},
    {"content": "Counting letters now.", "name": "Coder", "role": "assistant"},
    {"content": "Traceback (most recent call last):\nSyntaxError: invalid syntax", "name": "Coder", "role": "assistant"},
    {"content": "The count is 4.", "name": "Planner", "role": "assistant"}
  ],
  "mistake_agent": "Coder",
  "mistake_step": "1",
  "mistake_reason": "The Python code is incorrect."
}
```
(Coder's messages: index 0 = counting, index 1 = traceback → agent-scope truth step 1; the error sits at global index 2.)

`fx_hc_role.json` — role-speaker:
```json
{
  "question_ID": "fx-hc-1",
  "history": [
    {"content": "Find nearby climbing gyms.", "name": null, "role": "human"},
    {"content": "Traceback (most recent call last):\nExecution failed: page load timeout", "name": null, "role": "WebSurfer"}
  ],
  "mistake_agent": "WebSurfer",
  "mistake_step": "0",
  "mistake_reason": "The tool call crashed."
}
```

`fx_hc_variant.json` — role variants normalize to the base name:
```json
{
  "question_ID": "fx-hc-2",
  "history": [
    {"content": "Research the topic.", "name": null, "role": "human"},
    {"content": "Initial plan: delegate the search.", "name": null, "role": "Orchestrator (thought)"},
    {"content": "Please run the search.", "name": null, "role": "Orchestrator (-> WebSurfer)"},
    {"content": "Traceback (most recent call last):\nExecution failed", "name": null, "role": "Orchestrator"},
    {"content": "Results ready.", "name": null, "role": "WebSurfer"}
  ],
  "mistake_agent": "Orchestrator",
  "mistake_step": "2",
  "mistake_reason": "The orchestration step crashed."
}
```
(Orchestrator messages after normalization: `(thought)`→0, `(-> WebSurfer)`→1, plain→2.)

### 5. Tests

**Extend `tests/test_who_when.py`:**
- Update the 1-based encodings: `_RECORD`'s `"mistake_step": "1"` → `"0"` (Verifier_Expert has one message, the error). `test_evaluate_counts_miss_when_agent_differs` keeps being a miss via the differing agent; set its step to `"1"` (Planner's second message, 0-based) for realism.
- New fixture-driven tests (load via `json.loads(path.read_text())`, fixture root `Path(__file__).parent / "fixtures" / "who_when" / "Who&When"`):
  - speaker from `role` when `name` is null (`fx_hc_role`): `history_to_events` yields `data["speaker"] == "WebSurfer"` for the second event;
  - role-variant normalization (`fx_hc_variant`): speakers are `["human", "Orchestrator", "Orchestrator", "Orchestrator", "WebSurfer"]`, and `evaluate_records` attributes `predicted_agent == "Orchestrator"`;
  - 0-based agent-scope step mapping (`fx_ag_multi`): `predicted_step == 1`, `step_match is True`;
  - 0-based global-scope step mapping (`fx_ag_multi` re-annotated `mistake_step="2"` via `dict(record, mistake_step="2")`): `evaluate_records(..., step_scope="global")` gives `step_match is True`.

**New `tests/test_fetch_who_when.py`:**
- Import the script via `importlib.util.spec_from_file_location("fetch_who_when", repo_root / "scripts" / "fetch_who_when.py")` (scripts/ is not a package), call `run(fixture_root, tmp_path)`.
- Assert: `algorithm_generated.jsonl` has 1 line, `hand_crafted.jsonl` has 2; lines are compact JSON with exactly the five harness keys; records sorted by `question_ID`; `MANIFEST.json` has `source_repo`, `commit_sha` (null — fixtures aren't a git repo), `generated_at`, per-split `source_files`/`records`, `total_records == 3`.
- Assert `run(Path("/nonexistent"), tmp_path)` raises (or returns an error/exit code — match whatever `run` signals) with a clear message.

### 6. `justfile` — new `who-when` recipe

Append (shebang recipe for the conditional; `just` runs from the justfile dir):

```just
# fetch Who&When corpora if missing, run agent-scope benchmark, write results with per-record rows
who-when:
    #!/usr/bin/env bash
    set -euo pipefail
    CORPUS=benchmarks/corpora/who_when
    if [ ! -s "$CORPUS/algorithm_generated.jsonl" ] || [ ! -s "$CORPUS/hand_crafted.jsonl" ]; then
        echo "Who&When corpora missing under $CORPUS — fetching from github.com/mingyin1/Agents_Failure_Attribution…"
        uv run scripts/fetch_who_when.py
    fi
    if [ ! -s "$CORPUS/algorithm_generated.jsonl" ] || [ ! -s "$CORPUS/hand_crafted.jsonl" ]; then
        echo "ERROR: corpora still missing after fetch. Run 'uv run scripts/fetch_who_when.py' manually (optionally --source /path/to/existing/clone) and retry." >&2
        exit 1
    fi
    uv run scripts/benchmark_who_when.py \
        --data "$CORPUS/algorithm_generated.jsonl" "$CORPUS/hand_crafted.jsonl" \
        --step-scope agent \
        --out "$CORPUS/results_agent_scope.json"
```

`results_agent_scope.json` lives under the corpora dir → automatically runtime state (see item 7).

### 7. `.gitignore`

Add (corpora only — the fixtures under `tests/fixtures/` must stay committed):

```
# Who&When benchmark corpora (runtime state; reseed with scripts/fetch_who_when.py)
benchmarks/corpora/
```

### 8. `docs/guides/audit-and-trust.md`

In "External validation: the Who&When benchmark": replace the manual `git clone` + `--data /tmp/ww` block with the new flow, and fix the indexing sentence:

```markdown
```bash
# Offline pipeline smoke test (bundled synthetic records):
python scripts/benchmark_who_when.py --self-test

# Seed the corpora (clones the dataset; or pass --source /path/to/existing/clone),
# then run the full agent-scope evaluation and write per-record results:
uv run scripts/fetch_who_when.py
just who-when
```

The corpora land in `benchmarks/corpora/who_when/` (`algorithm_generated.jsonl`,
`hand_crafted.jsonl`, plus `MANIFEST.json` recording the source repo, commit
sha, and counts). That directory is runtime state, gitignored — reseed with the
fetch script. `mistake_step` is the **0-based** index among the mistake agent's
own messages (`--step-scope global` switches to 0-based whole-history
indexing). Hand-Crafted records carry the speaker in `history[].role`;
parenthetical variants like `Orchestrator (thought)` normalize to
`Orchestrator`.
```

Keep the surrounding paragraphs (including the paper's 53.5%/14.2% reference numbers — those are the paper's claims, not ours). Add no accuracy claims of our own.

---

## Verification (in order)

1. **Fetch against the real clone:** `uv run scripts/fetch_who_when.py --source /tmp/ww_repo` → both JSONLs + `MANIFEST.json` exist under `benchmarks/corpora/who_when/`; `wc -l` gives **126** and **58** (the actual clone's counts at `b2bae5c`; the task's "99" is a known miscount — do NOT filter to force it, and call this out in the report); MANIFEST `source_files`/`records` match; `commit_sha == b2bae5c5b06d681d04ea5e9b63b7a30525c04925`.
2. **Determinism:** run fetch twice; the two JSONL files are byte-identical (`sha256sum`); MANIFEST differs only in `generated_at`.
3. **Lint + tests:** `.venv-ci/bin/ruff check .` clean; `.venv-ci/bin/pytest -q tests/test_who_when.py tests/test_fetch_who_when.py -v` green (new speaker/role-variant/0-based tests pass, updated 1-based tests still pass); then the full suite `.venv-ci/bin/pytest -q` green.
4. **Self-test:** `uv run scripts/benchmark_who_when.py --self-test` prints `self-test OK` under the 0-based records.
5. **Recipe happy path:** `just who-when` (corpora present) runs both splits, prints the summary, and writes `benchmarks/corpora/who_when/results_agent_scope.json` containing `rows` with 126+58=184 entries.
6. **Recipe clean failure:** `mv benchmarks/corpora /tmp/corpus-bak && just who-when` → either re-fetches (network available — then re-verify results) or exits non-zero with the clear ERROR line; also confirm `uv run scripts/fetch_who_when.py --source /nonexistent` exits 2 with a clear stderr message. Restore the corpora afterwards.

## Out of scope

- Changing the error-marker heuristics (`_ERROR_MARKERS`) or the localization logic.
- Running/interpreting the full benchmark beyond verifying the pipeline executes and writes results (that happens after this lands).
- Any accuracy claims in docs.
- Vendoring the dataset or any real dataset content into the repo.
