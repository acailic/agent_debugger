#!/usr/bin/env bash
# Auto Worker - GitHub issue processor for agent_debugger
# Picks up auto-work labeled issues, implements, creates PRs
set -euo pipefail

REPO_DIR="/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger"
LOG_DIR="${REPO_DIR}/docs/superpowers/scheduled-reports"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
LOG_FILE="${LOG_DIR}/auto-worker-${TIMESTAMP}.log"

cd "$REPO_DIR"

/home/nistrator/.local/bin/claude -p "You are working on the agent_debugger repo at ${REPO_DIR}.

1. List open GitHub issues labeled 'auto-work' using \`gh issue list --label auto-work\`
2. If none found, fall back to all open issues with \`gh issue list\`
3. Pick the oldest issue (FIFO queue order)
4. Read the issue details with \`gh issue view\`
5. Create a git worktree for isolated work
6. Implement the fix
7. Run validation: \`ruff check .\` and if pytest is available run \`python3 -m pytest -q\`
8. Create a PR with a clear description referencing the issue
9. Report the PR link

If no actionable issues exist, report that and suggest what could be created." \
  --allowedTools "Task,Bash,Glob,Grep,Read,Edit,Write,WebSearch,Agent" \
  --model sonnet \
  --output-format text \
  > "$LOG_FILE" 2>&1

echo "Auto worker completed: ${LOG_FILE}"

# Keep only last 15 logs
ls -t "${LOG_DIR}"/auto-worker-*.log 2>/dev/null | tail -n +16 | xargs -r rm
