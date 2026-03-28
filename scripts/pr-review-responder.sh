#!/usr/bin/env bash
# PR Review Responder - Monitors open PRs for review comments and implements feedback
# Runs via crontab, logs to docs/superpowers/scheduled-reports/

set -euo pipefail

REPO_DIR="/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger"
LOG_DIR="${REPO_DIR}/docs/superpowers/scheduled-reports"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
LOG_FILE="${LOG_DIR}/pr-review-${TIMESTAMP}.log"
CLAUDE="/home/nistrator/.local/bin/claude"

cd "$REPO_DIR"

# Run claude with the PR review responder prompt
"$CLAUDE" -p "You are working on the agent_debugger repo at ${REPO_DIR}.

1. List open PRs using \`gh pr list --state open\`
2. For each open PR, check for unaddressed review comments using \`gh pr view <number> --comments\` and \`gh api repos/{owner}/{repo}/pulls/<number>/comments\`
3. If there are review comments that haven't been addressed (no reply from the PR author, no matching commit):
   a. Check out the PR branch with \`gh pr checkout <number>\`
   b. Read the review comments carefully
   c. Implement the requested changes
   d. Run validation: \`ruff check .\` and if pytest is available run \`python3 -m pytest -q\`
   e. Commit and push the changes with a message like 'address review feedback'
   f. Reply to the review comment confirming the changes using \`gh pr comment <number> --body \"...\"\`
4. If no PRs have unaddressed comments, report that briefly.

Be thorough but conservative — only make changes that the reviewer explicitly requested." \
  --allowedTools "Task,Bash,Glob,Grep,Read,Edit,Write,WebSearch,Agent" \
  --model sonnet \
  --output-format text \
  > "$LOG_FILE" 2>&1

echo "PR review check completed: ${LOG_FILE}"

# Keep only last 15 logs
ls -t "${LOG_DIR}"/pr-review-*.log 2>/dev/null | tail -n +16 | xargs -r rm
