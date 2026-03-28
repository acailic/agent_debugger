# Scheduled Tasks Design

**Date:** 2026-03-27
**Status:** Implemented

## Summary

Two local crontab tasks for the agent_debugger repo: a twice-daily debt scan and an on-demand auto-worker. Both use `claude -p` with scoped tool access.

## Tasks

### 1. debt-scan

- **Schedule:** Twice daily at 9:37 and 21:37 (`37 9,21 * * *`)
- **Script:** `scripts/debt-scan.sh`
- **Mechanism:** Local crontab running `claude -p` with read-only tools
- **Tools allowed:** `Bash,Glob,Grep,Read,WebSearch`
- **Model:** Sonnet
- **Behavior:** Report only — no automatic fixes
- **Output:** Markdown report to `docs/superpowers/scheduled-reports/debt-scan-YYYY-MM-DD_HH-MM.md`
- **Retention:** Last 30 reports kept

### 2. auto-worker

- **Schedule:** Manual/on-demand (run `scripts/auto-worker.sh`)
- **Script:** `scripts/auto-worker.sh`
- **Mechanism:** Local script running `claude -p` with full edit tools
- **Tools allowed:** `Task,Bash,Glob,Grep,Read,Edit,Write,WebSearch,Agent`
- **Model:** Sonnet
- **Behavior:** Full implementation cycle — reads issues, implements fix in worktree, creates PR
- **Output:** Log to `docs/superpowers/scheduled-reports/auto-worker-YYYY-MM-DD_HH-MM.log`
- **Retention:** Last 15 logs kept

## Files

- `scripts/debt-scan.sh` — Debt scan wrapper script
- `scripts/auto-worker.sh` — Auto worker wrapper script
- `docs/superpowers/scheduled-reports/` — Output directory for reports and logs
- `docs/superpowers/specs/2026-03-27-scheduled-tasks-design.md` — This design doc

## Crontab Entry

```
# Agent Debugger - Debt Scan (twice daily at 9:37 and 21:37)
37 9,21 * * * /path/to/agent_debugger/scripts/debt-scan.sh >> /path/to/agent_debugger/docs/superpowers/scheduled-reports/cron.log 2>&1
```

## Running Manually

```bash
# Debt scan
./scripts/debt-scan.sh

# Auto worker
./scripts/auto-worker.sh
```
