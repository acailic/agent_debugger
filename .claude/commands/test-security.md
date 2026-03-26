# Security Validation Suite

Run all security-focused checks in one shot. Ideal before merging or releasing.

## Steps

Run checks **in parallel** where possible.

### 1. Bandit — Python security lint

```bash
bandit -r agent_debugger_sdk api storage auth redaction collector -f screen -ll
```

Report PASS if exit code 0, FAIL otherwise.

### 2. Redaction security tests

```bash
python3 -m pytest tests/test_redaction_security.py -q
```

Report PASS if all tests pass, FAIL otherwise.

### 3. Auth tests

```bash
python3 -m pytest tests/ -k "auth" -q
```

Report PASS if all tests pass, FAIL otherwise.

### 4. Dependency audit

```bash
pip-audit --desc 2>/dev/null || echo "pip-audit not installed — SKIP"
```

Report PASS if no vulnerabilities found, FAIL if vulnerabilities found, SKIP if not installed.

## Summary

Output this exact format:

```text
=== Security Validation Scorecard ===

  Bandit (security lint)     : PASS or FAIL
  Redaction tests            : PASS or FAIL
  Auth tests                 : PASS or FAIL
  Dependency audit (pip)     : PASS or FAIL or SKIP

  Overall: PASS  or  FAIL  or  PARTIAL ({N} check(s) skipped)
```

If FAIL or PARTIAL, list actionable items.
