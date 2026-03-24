# Release peaky-peek Package(s)

You are performing a release of the peaky-peek project. Follow each step carefully. Stop immediately if any pre-release check fails.

Ground the process in `.github/workflows/publish.yml`, `pyproject.toml`, and `pyproject-server.toml`.

## Step 1: Determine Release Target

If `$ARGUMENTS` contains a version number (e.g., `0.2.0`), use it as the new version. Otherwise, you will ask the user later.

Ask the user what they want to release. Present these three options clearly:

1. **SDK only** — publishes `peaky-peek` to PyPI. Tag prefix: `sdk-v` (e.g., `sdk-v0.2.0`)
2. **Server only** — publishes `peaky-peek-server` to PyPI. Tag prefix: `server-v` (e.g., `server-v0.2.0`)
3. **Both SDK and Server** — publishes both packages. Tag prefix: `v` (e.g., `v0.2.0`)

Wait for the user to choose before proceeding.

## Step 2: Determine Version Number

Read the current versions from both:

- `pyproject.toml`
- `pyproject-server.toml`

If they differ, stop and tell the user to reconcile them before releasing.

If a version was provided via `$ARGUMENTS`, confirm it with the user. Otherwise, suggest three bump options based on the current version:

- **Patch**: MAJOR.MINOR.(PATCH+1) — for bug fixes
- **Minor**: MAJOR.(MINOR+1).0 — for new features
- **Major**: (MAJOR+1).0.0 — for breaking changes

Wait for the user to confirm or provide a version before proceeding.

## Step 3: Pre-Release Validation

Run ALL of the following checks. Report each as PASS or FAIL:

1. **Lint**: `ruff check .`
2. **Tests**: `python3 -m pytest -q`
3. **Frontend build**: `cd frontend && npm run build`
4. **SDK build**: `python3 -m build`
5. **Server release inputs present**: verify `pyproject-server.toml` and `frontend/package-lock.json` exist
6. **Clean git status**: `git status --porcelain` must be empty
7. **On main branch**: `git branch --show-current` must be `main`
8. **Up-to-date with remote**: `git fetch origin main` then `git rev-list HEAD..origin/main --count` must be `0`

If ANY check fails, stop here. Report a summary of what passed and what failed. Do NOT create or push any tags. Tell the user what needs to be fixed.

## Step 4: Create and Push Tag

Only proceed here if ALL checks in Step 3 passed.

Construct the tag name using the prefix from Step 1 and the version from Step 2:
- SDK only: `sdk-v{VERSION}`
- Server only: `server-v{VERSION}`
- Both: `v{VERSION}`

Create the tag:
```
git tag {TAG_NAME}
```

Push the tag to origin:
```
git push origin {TAG_NAME}
```

## Step 5: Report

After successfully pushing the tag, report:

- the tag that was created and pushed
- that `.github/workflows/publish.yml` will handle the publish
- the publish target(s): SDK, server, or both
- monitor URL: `https://github.com/acailic/agent_debugger/actions`
- remind the user that CI derives the published version from the tag and rewrites the package metadata during the workflow

If the tag push fails, report the error and suggest the user check their remote configuration and permissions.

If the tag push succeeds, proceed to Step 6 to create the GitHub Release.

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
