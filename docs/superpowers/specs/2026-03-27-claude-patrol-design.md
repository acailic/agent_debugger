# Claude Patrol Bot Design

**Date:** 2026-03-27
**Status:** Approved
**Scope:** Automated Claude Code sessions for code quality and performance monitoring

## Overview

A scheduled automation system that launches Claude Code sessions every 2 hours to perform code quality checks and performance monitoring on the agent_debugger repository.

## Schedule

- **Frequency:** Every 2 hours (12 sessions/day)
- **Cron expression:** `0 */2 * * *`

## Tasks Per Session

### 1. Code Quality Patrol

| Check | Command | Action on Failure |
|-------|---------|-------------------|
| Lint | `ruff check .` | Auto-fix and create PR |
| Tests | `pytest -q` | Fix failing tests, create PR |
| Dead code | Scan for unused imports/functions | Remove and create PR |

### 2. Performance Monitoring

| Check | Command | Action on Regression |
|-------|---------|---------------------|
| Benchmarks | `python scripts/benchmarks/run_benchmarks.py` | Create GitHub issue if >10% slower |

## Workflow

```
┌─────────────────┐
│  Cron (every 2h)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ claude-patrol.sh│
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ Claude Code Session │
│ with patrol.md      │
└────────┬────────────┘
         │
         ├──────────────────────────────────┐
         │                                  │
         ▼                                  ▼
┌─────────────────┐              ┌──────────────────┐
│ Changes Made?   │──Yes────────▶│ Create PR        │
└────────┬────────┘              │ [patrol] prefix  │
         │No                     └──────────────────┘
         ▼
┌─────────────────┐
│ Issues Found?   │──Yes────────▶│ Create GitHub    │
└────────┬────────┘              │ Issue            │
         │No                     └──────────────────┘
         ▼
┌─────────────────┐
│ Log Success     │
└─────────────────┘
```

## Files to Create

```
scripts/
├── claude-patrol.sh           # Cron entry point
├── prompts/
│   └── patrol.md              # Task instructions for Claude
└── benchmarks/
    └── run_benchmarks.py      # Performance baseline runner
```

### scripts/claude-patrol.sh

```bash
#!/bin/bash
# Claude Patrol - Automated code quality and performance checks
# Runs every 2 hours via cron

set -e

REPO_DIR="/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger"
LOG_DIR="$REPO_DIR/.claude-patrol-logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$LOG_DIR"

cd "$REPO_DIR"

# Activate virtual environment
source .venv/bin/activate

# Run Claude Code with patrol prompt
claude --prompt-file scripts/prompts/patrol.md \
       --output "$LOG_DIR/patrol-$TIMESTAMP.log" \
       --json
```

### scripts/prompts/patrol.md

```markdown
# Claude Patrol Tasks

You are running as an automated patrol bot. Perform the following checks:

## 1. Code Quality

Run `ruff check .` and fix any lint issues.
Run `pytest -q` and fix any failing tests.

## 2. Performance

Run benchmarks with `python scripts/benchmarks/run_benchmarks.py`.
If any benchmark shows >10% regression, note it.

## 3. Reporting

- If you made changes: Create a PR with title prefix `[patrol]`
- If you found issues you couldn't fix: Create a GitHub issue
- If everything passed: Just log success

Use git identity: Claude Patrol <noreply@anthropic.com>
```

### scripts/benchmarks/run_benchmarks.py

```python
"""Run performance benchmarks and compare against baseline."""

import json
import subprocess
import sys
from pathlib import Path

BASELINE_FILE = Path(__file__).parent / "baseline.json"
REGRESSION_THRESHOLD = 0.10  # 10%


def run_benchmark(name: str, command: list[str]) -> dict:
    """Run a benchmark command and return timing info."""
    import time
    start = time.perf_counter()
    subprocess.run(command, capture_output=True, check=False)
    elapsed = time.perf_counter() - start
    return {"name": name, "elapsed_seconds": elapsed}


def main():
    benchmarks = [
        ("session_analysis", ["python", "-m", "pytest", "tests/intelligence/", "-q"]),
        ("replay_building", ["python", "-m", "pytest", "tests/test_replay_collapse.py", "-q"]),
    ]

    results = {"benchmarks": [run_benchmark(name, cmd) for name, cmd in benchmarks]}

    # Load baseline and compare
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        regressions = []
        for current, base in zip(results["benchmarks"], baseline["benchmarks"]):
            if current["elapsed_seconds"] > base["elapsed_seconds"] * (1 + REGRESSION_THRESHOLD):
                regressions.append(current["name"])

        if regressions:
            print(f"PERFORMANCE REGRESSION detected in: {', '.join(regressions)}")
            sys.exit(1)

    # Save new baseline
    BASELINE_FILE.write_text(json.dumps(results, indent=2))
    print("Benchmarks completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## Git Identity

- **Author:** Claude Patrol <noreply@anthropic.com>
- **PR Title Prefix:** `[patrol]`
- **Commit Message Prefix:** `patrol:`

## Cron Setup

```bash
# Edit crontab
crontab -e

# Add this line:
0 */2 * * * /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/scripts/claude-patrol.sh
```

## Logging

Logs stored in `.claude-patrol-logs/`:
- `patrol-YYYYMMDD-HHMMSS.log` - Session output
- Retain for 7 days, then auto-delete

## Safety Measures

1. **Never force push** - All changes via PR
2. **Run tests before committing** - Ensure CI passes
3. **Scope limits** - Only fix what's broken, no refactoring scope creep
4. **Rate limiting** - If previous PR still open, skip session

## Verification

After setup, verify with:
```bash
# Manual test
./scripts/claude-patrol.sh

# Check logs
cat .claude-patrol-logs/patrol-*.log
```
