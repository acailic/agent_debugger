# GitHub Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `/release` skill to automatically create professional GitHub Releases with notes parsed from conventional commits.

**Architecture:** Add Step 6 to the existing release.md skill that finds the previous tag, parses commits between tags using conventional commit format, groups them by category and scope, generates markdown notes, and creates a GitHub release via `gh release create`.

**Tech Stack:** Bash/git commands, `gh` CLI, regex parsing in bash

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `.claude/commands/release.md` | Modify | Add Step 6 for GitHub release creation |

---

### Task 1: Add Step 6 to release.md

**Files:**
- Modify: `.claude/commands/release.md`

- [ ] **Step 1: Add Step 6 after Step 5**

Add the following content after the Step 5 section:

```markdown
## Step 6: Create GitHub Release

After the tag is pushed, create a GitHub Release with auto-generated notes from conventional commits.

### 6a. Find the previous tag

Based on the release type from Step 1:

```bash
# SDK releases: find most recent sdk-v* tag
# Server releases: find most recent server-v* tag
# Both releases: find most recent v* tag
PREV_TAG=$(git tag -l "{PREFIX}*" --sort=-version:refname | head -2 | tail -1)

# If no previous tag, use initial commit
if [ -z "$PREV_TAG" ]; then
    PREV_TAG=$(git rev-list --max-parents=0 HEAD)
fi
```

### 6b. Fetch and parse commits

Get commits between previous tag and new tag:

```bash
git log "$PREV_TAG..$TAG_NAME" --pretty=format:"%s"
```

Parse using conventional commit regex:
- Pattern: `^(feat|fix|docs|refactor|test|chore|perf|style|ci)(\([a-zA-Z0-9-]+\))?:\s*(.+)$`
- Extract: type, scope (optional), subject

### 6c. Group commits

Group by:
1. **Category**: feat → Features, fix → Bug Fixes, all others → Other
2. **Scope**: Group under `### {Scope}` sub-header if scope exists
3. **Sort**: Alphabetically by subject within each group

### 6d. Generate release notes markdown

Format:

```markdown
# {TAG_NAME}

## ✨ Features

### {Scope}
- {subject}
- {subject}

## 🐛 Bug Fixes

### {Scope}
- {subject}

## 📦 Other

### Documentation
- {subject}

### Refactoring
- {subject}
```

Skip empty categories. Skip scope sub-headers if no scope.

### 6e. Create the GitHub Release

```bash
gh release create "$TAG_NAME" --title "$TAG_NAME" --notes-file NOTES.md
```

Or pipe directly:
```bash
gh release create "$TAG_NAME" --title "$TAG_NAME" --notes-file - <<< "$NOTES"
```

### 6f. Report

After creating the release, report:
- GitHub Release URL: `https://github.com/acailic/agent_debugger/releases/tag/{TAG_NAME}`
- Summary of categories (e.g., "3 features, 2 bug fixes, 5 other changes")

### 6g. Failure Handling

If `gh release create` fails:
- Report the error message
- Provide manual command: `gh release create {TAG_NAME} --title "{TAG_NAME}" --notes-file NOTES.md`
- Note: PyPI publish already succeeded via CI, so this is non-blocking
```

- [ ] **Step 2: Update Step 5 to reference Step 6**

Modify the end of Step 5 to transition to Step 6:

Change:
```markdown
If the tag push fails, report the error and suggest the user check their remote configuration and permissions.
```

To:
```markdown
If the tag push fails, report the error and suggest the user check their remote configuration and permissions.

If the tag push succeeds, proceed to Step 6 to create the GitHub Release.
```

- [ ] **Step 3: Commit the changes**

```bash
git add .claude/commands/release.md
git commit -m "feat(release): add GitHub Release creation with conventional commit notes"
```

---

### Task 2: Test the implementation

**Files:**
- Test: Manual verification

- [ ] **Step 1: Verify skill is recognized**

```bash
# The skill should be available at /release
# Verify the file is syntactically valid markdown
```

- [ ] **Step 2: Simulate commit parsing logic**

Run a test to verify the commit parsing would work:

```bash
# Get recent commits in conventional format
git log --oneline -20 | grep -E "^(feat|fix|docs|refactor|test|chore|perf|style|ci)(\([a-zA-Z0-9-]+\))?:"

# Expected: Should return commits matching conventional format
```

- [ ] **Step 3: Verify gh CLI is available**

```bash
gh --version
# Expected: gh version X.Y.Z or similar
```

---

## Summary

| Task | Files Changed | Tests |
|------|---------------|-------|
| Add Step 6 to release.md | `.claude/commands/release.md` | Manual verification |

**Total files modified:** 1
