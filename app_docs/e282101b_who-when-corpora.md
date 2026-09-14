# Who&When seeded corpora + harness correctness fixes (M2.4)

Seeds reproducible Who&When benchmark corpora on disk, fixes two attribution-correctness bugs in the audit harness found while preparing the full-dataset run, and wires a one-command `just who-when` recipe. 13 files changed (+1251 −38) against `bce2a0d`.

## Why it matters

Previously every benchmark run required a manual clone and `--data` plumbing, and the harness had two bugs that made it silently wrong on roughly half the dataset:

1. **Step indexing was 1-based.** The benchmark's `mistake_step` annotations are the **0-based** index of the erroneous message among the mistake agent's own messages (verified against records where 1-based would give the wrong answer — see `specs/e282101b_who-when-corpora.md`). Every step-accuracy number computed before this change was misaligned by one.
2. **Speakers were read from `name` only.** Hand-Crafted records (58 files) have `history[].name = null` and carry the speaker in `history[].role`, including parenthetical variants like `Orchestrator (thought)`. Those records previously attributed every message to `"unknown"`.

## What changed

### `collector/audit/who_when.py` — the two fixes

- New `_speaker_of(message)` helper (plus `_ROLE_PARENTHETICAL` regex): prefers `name`; otherwise uses `role` with one trailing parenthetical stripped (`"Orchestrator (-> WebSurfer)"` → `"Orchestrator"`); falls back to `"unknown"`. `history_to_events` now uses it, and the normalized speaker flows into both the event name and `data["speaker"]`.
- `_step_index_of` now returns 0-based indices in **both** scopes (agent and global) — the `+1` is gone. Module and function docstrings corrected from "1-based" to "0-based", and the docstring now documents the name-vs-role speaker convention.
- `_ERROR_MARKERS` and the localization logic are untouched.

### `scripts/fetch_who_when.py` (new, 186 lines) — corpora seeding

- `uv run scripts/fetch_who_when.py` shallow-clones `github.com/mingyin1/Agents_Failure_Attribution` to a temp dir; `--source PATH` uses an existing clone instead. `--out` defaults to `benchmarks/corpora/who_when`.
- Reads `Who&When/Algorithm-Generated/*.json` and `Who&When/Hand-Crafted/*.json` (one pretty-printed object per file), projects each onto exactly the harness schema (five keys: `question_ID`, `history[{content,name,role}]`, `mistake_agent`, `mistake_step`, `mistake_reason` — non-harness fields dropped), sorts by `question_ID`, fails loudly (`FetchError`, exit 2) on missing source/split dirs, unparseable JSON, or duplicate IDs.
- Writes compact deterministic JSONL (`algorithm_generated.jsonl`, `hand_crafted.jsonl`) plus `MANIFEST.json` with source repo URL, commit sha (`null` when the source isn't a git repo), per-split file/record counts, total, and UTC timestamp. Only `generated_at` varies between runs. Speakers are preserved as-is — normalization happens at harness read time, not in the corpora.
- `run(source, out_dir) -> dict` is importable separately from `main()` for tests.

### `tests/fixtures/who_when/` (new, committed) and tests

- Three hand-written mini-records mirroring the dataset layout (doubles as a fake `--source`): `fx_ag_multi.json` (name-speaker, Coder's traceback at own-index 1), `fx_hc_role.json` (role-speaker, step 0), `fx_hc_variant.json` (Orchestrator role variants, step 2). No dataset content redistributed.
- `tests/test_who_when.py`: `_speaker_of` unit tests (name preference, role fallback, parenthetical stripping, unknown default); fixture-driven attribution tests for role-speaker, role-variant normalization, and 0-based mapping in both scopes; existing records re-annotated to 0-based (`_RECORD` step `"1"`→`"0"`; miss-test `"2"`→`"1"`).
- `tests/test_fetch_who_when.py` (new): loads the script via `importlib`, verifies JSONL/manifest contents from the fixture source (counts, exact key sets, sort order, compact serialization, null commit sha, preserved `name: null` and role variants), and loud failures on missing source / missing split dir.

### `scripts/benchmark_who_when.py`

- `_SELF_TEST_RECORDS` steps updated to 0-based (`"1"` → `"0"` both).
- New `--out PATH` flag: writes the full results dict including per-record rows as JSON (the recipe depends on this). Docstring now points at the fetch script.

### `justfile`, `.gitignore`, docs

- New `who-when` recipe: fetches corpora if missing, exits 1 with a clear ERROR line if still missing after fetch, then runs the benchmark over both JSONL files with `--step-scope agent --out .../results_agent_scope.json`.
- `.gitignore` adds `benchmarks/corpora/` — corpora and results are runtime state, reseeding is the fetch script. The fixtures under `tests/fixtures/` stay committed.
- `docs/guides/audit-and-trust.md`: the manual `git clone` + `--data /tmp/ww` block is replaced with the `fetch_who_when.py` + `just who-when` flow, and now documents the corpora location, the gitignored runtime state, the **0-based** convention for both scopes, and the name-vs-role speaker fields. No accuracy claims added; the paper's 53.5%/14.2% reference numbers were kept as-is.

Also in the diff: `specs/e282101b_who-when-corpora.md` (the plan document for this work) and a `uv.lock` refresh (new pinned packages such as aiofiles, alembic, coverage, fastapi, greenlet — a lockfile update, no source change). One fact worth knowing from the spec: the task text's "99" Algorithm-Generated files was a miscount — the actual clone at `b2bae5c` has **126**, and 126+58=184 matches the "184 annotated failure logs" already in the docs. The fetch script records the counts it actually finds; it does not filter toward any hardcoded number.

## How to verify

```bash
# Seed corpora from a real clone (or omit --source to shallow-clone):
uv run scripts/fetch_who_when.py --source /tmp/ww_repo
# → benchmarks/corpora/who_when/{algorithm_generated.jsonl, hand_crafted.jsonl, MANIFEST.json}
# Expect 126 + 58 records (see the count note above); re-running gives byte-identical JSONLs.

# Offline pipeline smoke test (now 0-based):
uv run scripts/benchmark_who_when.py --self-test   # prints "self-test OK"

# Full flow, including clean failure when corpora are absent:
just who-when

# Tests + lint:
.venv-ci/bin/pytest -q tests/test_who_when.py tests/test_fetch_who_when.py -v
.venv-ci/bin/pytest -q
.venv-ci/bin/ruff check .
```

Out of scope by design: the error-marker heuristics, running/interpreting the full benchmark (that happens after this lands), and any accuracy claims in docs.
