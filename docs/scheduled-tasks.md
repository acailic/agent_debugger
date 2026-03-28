# Scheduled Tasks

Automated Claude Code tasks running via local crontab. Each script launches an isolated `claude -p` session with scoped tool access.

## Active Jobs

### Debt Scan

| | |
|---|---|
| **Schedule** | Twice daily at 09:37 and 21:37 |
| **Script** | `scripts/debt-scan.sh` |
| **Tools** | `Bash`, `Glob`, `Grep`, `Read`, `WebSearch` (read-only) |
| **Output** | `docs/superpowers/scheduled-reports/debt-scan-YYYY-MM-DD_HH-MM.md` |

Scans the codebase for technical debt: dead code, unused imports, complex functions, inconsistent patterns, and TODO/FIXME comments. Reviews recent git history for quality trends. Report only — makes no changes.

### PR Review Responder

| | |
|---|---|
| **Schedule** | Every 2 hours |
| **Script** | `scripts/pr-review-responder.sh` |
| **Tools** | `Task`, `Bash`, `Glob`, `Grep`, `Read`, `Edit`, `Write`, `WebSearch`, `Agent` |
| **Output** | `docs/superpowers/scheduled-reports/pr-review-YYYY-MM-DD_HH-MM.log` |

Monitors open PRs for unaddressed review comments. When found, checks out the PR branch, implements the requested changes, validates with `ruff check` and `pytest`, pushes, and replies to the comment confirming what was done.

### Auto Worker

| | |
|---|---|
| **Schedule** | Manual / on-demand |
| **Script** | `scripts/auto-worker.sh` |
| **Tools** | `Task`, `Bash`, `Glob`, `Grep`, `Read`, `Edit`, `Write`, `WebSearch`, `Agent` |
| **Output** | `docs/superpowers/scheduled-reports/auto-worker-YYYY-MM-DD_HH-MM.log` |

Reads open GitHub issues labeled `auto-work`, picks the oldest one, implements a fix in a git worktree, validates, and creates a PR. Falls back to all open issues if no labeled issues exist.

## Crontab Entries

```
# Agent Debugger - Debt Scan (twice daily at 9:37 and 21:37)
37 9,21 * * * .../scripts/debt-scan.sh >> .../docs/superpowers/scheduled-reports/cron.log 2>&1

# Agent Debugger - PR Review Responder (every 2 hours)
17 */2 * * * .../scripts/pr-review-responder.sh >> .../docs/superpowers/scheduled-reports/cron.log 2>&1
```

## Manual Usage

```bash
# Run debt scan now
./scripts/debt-scan.sh

# Run auto worker on queued issues
./scripts/auto-worker.sh

# Check PR reviews now
./scripts/pr-review-responder.sh
```

## Adding Tasks to the Auto Worker Queue

```bash
# Create the label (one-time)
gh label create "auto-work" --description "AI auto-worker queue" --color "0E8A16"

# Queue a task
gh issue create --title "Description" --body "Details..." --label "auto-work"
```

## Output Retention

| Task | Retention |
|------|-----------|
| Debt scan reports | Last 30 files |
| Auto worker logs | Last 15 files |
| PR review logs | Last 15 files |

## Architecture

```
scripts/
├── debt-scan.sh            # Read-only debt scanner
├── auto-worker.sh          # Issue → PR implementation
└── pr-review-responder.sh  # PR feedback implementation

docs/superpowers/scheduled-reports/
├── cron.log                            # Combined cron stdout/stderr
├── debt-scan-2026-03-28_0937.md        # Individual scan reports
├── auto-worker-2026-03-28_1000.log     # Worker run logs
└── pr-review-2026-03-28_1217.log       # Review responder logs
```
