#!/usr/bin/env bash
# Debt Scan - Twice-daily technical debt scan for agent_debugger
# Runs via crontab, logs to docs/superpowers/scheduled-reports/

set -euo pipefail

REPO_DIR="/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger"
REPORT_DIR="${REPO_DIR}/docs/superpowers/scheduled-reports"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
REPORT_FILE="${REPORT_DIR}/debt-scan-${TIMESTAMP}.md"
CLAUDE="/home/nistrator/.local/bin/claude"

cd "$REPO_DIR"

# Run claude with the debt scan prompt
"$CLAUDE" -p "You are working on the agent_debugger repo at ${REPO_DIR}.

Scan the codebase for technical debt:
1. Check for dead code, unused imports, unreachable branches
2. Find overly complex functions (high cyclomatic complexity, deep nesting)
3. Look for inconsistent patterns across the codebase
4. Review recent git log (last 20 commits) for quality trends
5. Check for TODO/FIXME/HACK comments that may need attention

Report findings ranked by severity (high/medium/low). Be specific - name files and line ranges.
Do NOT make any changes. Report only.

If no significant issues are found, say so briefly. Keep the report concise." \
  --allowedTools "Bash,Glob,Grep,Read,WebSearch" \
  --model sonnet \
  --output-format text \
  > "$REPORT_FILE" 2>&1

echo "Debt scan completed: ${REPORT_FILE}"

# Keep only last 30 reports
ls -t "${REPORT_DIR}"/debt-scan-*.md 2>/dev/null | tail -n +31 | xargs -r rm
