# Release Check Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `/release-check` Claude Code skill for pre-release validation.

**Architecture:** Single SKILL.md file containing declarative instructions for Claude to execute lint, security, test, and frontend build checks in sequence with fail-fast behavior.

**Tech Stack:** Claude Code skill system (markdown with YAML frontmatter)

**Spec:** `docs/superpowers/specs/2026-03-24-release-check-skill-design.md`

---

## File Structure

```
.claude/
└── skills/
    └── release-check/
        └── SKILL.md    # Main skill file with instructions
```

---

### Task 1: Create Skill Directory Structure

**Files:**
- Create: `.claude/skills/release-check/` (directory)

- [ ] **Step 1: Create the skill directory**

Run:
```bash
mkdir -p .claude/skills/release-check
```

Expected: Directory created successfully

- [ ] **Step 2: Verify directory exists**

Run:
```bash
ls -la .claude/skills/release-check
```

Expected: Directory listing shows empty directory

---

### Task 2: Create SKILL.md File

**Files:**
- Create: `.claude/skills/release-check/SKILL.md`

- [ ] **Step 1: Write the SKILL.md file**

Create `.claude/skills/release-check/SKILL.md` with the following content:

```markdown
---
name: release-check
description: Run full validation suite before release. Sequential lint, security scan, tests, and frontend build with fail-fast behavior.
---

# Release Check

Run pre-release validation checks in sequence.

## Checks

1. **Lint**: `ruff check .` (timeout: 60s)
2. **Security**: `bandit -r -ll agent_debugger_sdk api collector storage auth redaction` (timeout: 120s)
3. **Tests**: `pytest -q` (timeout: 300s)
4. **Frontend**: `cd frontend && npm run build` (timeout: 180s)

## Process

1. Verify working directory contains `pyproject.toml` (repo root)
2. Run each check in order, timing execution
3. On failure:
   - Show error output (truncate >50 lines: first 20, last 20, with count)
   - Show remediation suggestion (see below)
   - Stop immediately
4. On all success: Print summary with timings

## Failure Remediation

| Check | Suggestion |
|-------|------------|
| Lint | "Fix lint errors above. Run `ruff check . --fix` for auto-fixable issues." |
| Security | "Review security findings above. Add `# nosec` comments only if justified." |
| Tests | "Fix failing tests. Run `pytest -v` for verbose output." |
| Frontend | "Fix TypeScript/build errors above. Check `frontend/src/` for issues." |

## Error Output Truncation

- If error output ≤ 50 lines: show full output
- If error output > 50 lines: show first 20 lines, `... N lines omitted ...`, last 20 lines

## Missing Dependencies

If a tool is not installed, show:
- bandit: `⚠ bandit not found. Install with: pip install bandit`
- npm: `⚠ npm not found. Ensure Node.js is installed.`

## Output Format

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✓ (1.2s)
3/4 Tests (pytest)........ ✓ (12.3s)
4/4 Frontend build........ ✓ (3.1s)

✓ Release check passed. Ready to ship.
```

## Example Failure Output

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✗ (1.2s)

Finding: [MEDIUM] Use of assert detected (security issue)
Location: tests/test_example.py:42

... 15 lines omitted ...

Review security findings above. Add `# nosec` comments only if justified.
```
```

- [ ] **Step 2: Verify file was created correctly**

Run:
```bash
cat .claude/skills/release-check/SKILL.md
```

Expected: File content matches the specification

---

### Task 3: Commit the Skill

**Files:**
- Commit: `.claude/skills/release-check/SKILL.md`

- [ ] **Step 1: Stage the skill file**

Run:
```bash
git add .claude/skills/release-check/SKILL.md
```

Expected: No output (success)

- [ ] **Step 2: Commit with descriptive message**

Run:
```bash
git commit -m "$(cat <<'EOF'
feat: add /release-check skill for pre-release validation

Runs sequential checks with fail-fast behavior:
- Lint (ruff)
- Security scan (bandit)
- Tests (pytest)
- Frontend build (npm)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

Expected: Commit created successfully

- [ ] **Step 3: Verify commit**

Run:
```bash
git log -1 --oneline
```

Expected: Shows the new commit

---

### Task 4: Validate Skill Installation

- [ ] **Step 1: Verify skill is recognized by Claude Code**

Run:
```bash
ls -la .claude/skills/release-check/
```

Expected: Shows SKILL.md file

- [ ] **Step 2: Confirm skill structure is correct**

The skill should now be invocable via `/release-check` in Claude Code.
