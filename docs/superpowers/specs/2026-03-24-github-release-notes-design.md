# GitHub Release Notes Design Spec

**Date**: 2026-03-24
**Status**: Draft
**Target**: Integrate into existing `/release` skill

## Problem

When releasing `peaky-peek` packages, the tag push triggers PyPI publishing but no GitHub Release is created. Users must manually create releases or GitHub shows auto-generated notes which lack structure and professionalism.

## Solution

Extend the existing `/release` skill to automatically create professional GitHub Releases after successful tag push. Release notes are parsed from conventional commits between the new tag and the previous tag.

## Design

### Trigger

Integrated into `/release` skill as **Step 6** (after Step 5: tag push report).

### Commit Parsing

**Input**: Commits between `PREVIOUS_TAG` and `NEW_TAG`

**Parsing rules**:
- Match conventional commit format: `type(scope): subject` or `type: subject`
- Skip merge commits (don't match the pattern)
- Skip commits without conventional format

**Category mapping** (simplified):

| Commit Type | GitHub Release Section |
|-------------|------------------------|
| `feat` | ## ✨ Features |
| `fix` | ## 🐛 Bug Fixes |
| All others | ## 📦 Other |

**Scope grouping**:
- Commits with scopes grouped under sub-headers: `### {Scope}`
- Commits without scopes appear directly under the category

### Output Format

```markdown
# v0.2.0

## ✨ Features

### SDK
- add Session, Checkpoint, and EVENT_TYPE_REGISTRY
- complete events/ package decomposition

### API
- add /release-check skill for pre-release validation

## 🐛 Bug Fixes

### Core
- resolve CI failure (lint)

## 📦 Other

### Documentation
- add research features completion design spec

### Tests
- update imports for events package decomposition

### Refactoring
- simplify event emitter logic
```

### Algorithm

```
1. Find previous tag:
   - For SDK releases: find most recent sdk-v* tag
   - For Server releases: find most recent server-v* tag
   - For both releases: find most recent v* tag
   - If no previous tag exists: use initial commit

2. Fetch commits:
   git log PREVIOUS_TAG..NEW_TAG --pretty=format:"%s"

3. Parse commits:
   - Regex: ^(feat|fix|docs|refactor|test|chore|perf|style|ci)(\([a-zA-Z0-9-]+\))?:\s*(.+)$
   - Extract: type, scope (optional), subject

4. Group commits:
   - Primary: by category (feat → Features, fix → Bug Fixes, other → Other)
   - Secondary: by scope (if present)
   - Tertiary: alphabetically by subject

5. Generate markdown:
   - Build sections in order: Features → Bug Fixes → Other
   - Skip empty categories
   - Scope sub-headers only if scope exists

6. Create GitHub Release:
   gh release create {TAG} --title "{TAG}" --notes-file -
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| First release (no previous tag) | Use all commits since initial commit (`git log --reverse --pretty=format:"%s"`) |
| No commits of a type | Skip that category entirely |
| Commits without scopes | List directly under category, no sub-header |
| Merge commits | Skip (don't match conventional format) |
| Breaking changes indicator (`!`) | Include in subject as-is, no special handling |
| Multi-line commit messages | Only use first line (subject) |

### Implementation Location

Update `.claude/commands/release.md`:

- Add Step 6 after existing Step 5
- Step 6 runs `gh release create` with generated notes
- Report includes link to the created release

### Dependencies

- `gh` CLI (already required for GitHub operations)
- Git (already in use)

### Failure Handling

If `gh release create` fails:
- Report the error
- Provide manual command: `gh release create {TAG} --title "{TAG}" --notes-file NOTES.md`
- Do not block the release (PyPI publish already succeeded)

## Success Criteria

- GitHub Releases are created automatically for all releases
- Notes are professionally formatted with emoji headers
- Features and bug fixes are prominently displayed
- Scope sub-groupings make navigation easy
- No manual intervention required during release
