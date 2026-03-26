# Targeted Test Runner

Run tests relevant to the current changes. Falls back to the full suite if no mapping is found.

## Args

- `$ARGUMENTS` — optional: `--full`, `--integration`, or `--watch`

## Steps

### 1. Determine mode

If `$ARGUMENTS` contains `--full`, run the full suite and skip mapping:

```bash
python3 -m pytest -q
```

Exit after reporting results.

If `$ARGUMENTS` contains `--integration`, run integration tests:

```bash
python3 -m pytest -q -m integration
```

Exit after reporting results.

If `$ARGUMENTS` contains `--watch`, start watch mode:

```bash
python3 -m pytest -q --watch
```

Exit after starting.

### 2. Collect changed Python files

Run in parallel:

```bash
git diff --name-only
git diff --cached --name-only
```

Filter to `.py` files only. Deduplicate.

### 3. Map changed files to test files

For each changed `.py` file, try these mappings in order:

1. **Same-name test**: If the file is `foo.py`, look for `tests/test_foo.py`
2. **Module-prefix test**: If the file is `agent_debugger_sdk/core/foo.py`, look for `tests/test_core_foo.py` or `tests/test_foo.py`
3. **Directory test**: Look for any `test_*.py` file in `tests/` whose name starts with the module name
4. **Adjacent test**: If the file has a sibling `test_*.py` in the same directory, include it

Collect all matched test file paths. If no tests were found for any changed file, fall back to running the full suite.

### 4. Run matched tests

```bash
python3 -m pytest -q <matched-test-paths>
```

### 5. Report results

Print:
- Which tests were run and why (which files changed)
- Pass/fail summary
- If fallback to full suite was used, note it
