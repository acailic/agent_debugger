# Repository Root Organization Cleanup

**Date:** 2026-03-24
**Status:** Approved
**Author:** acailic

## Goals

- Reduce root directory clutter from 30 files to ~22 files
- Establish clear data storage location
- Archive session artifacts for reference
- Prevent future artifact accumulation via `.gitignore`

## Context

The repository root has accumulated files over time that make navigation and project structure unclear:
- 9 `TESTING_*.md` files from AI sessions
- 2 database files in root
- Cache directories that may not be properly gitignored
- Documentation files that belong in `docs/`

## Design

### File Moves

#### 1. Create `data/` directory

Move database files to a dedicated data directory:

```
data/
├── .gitkeep
├── agent_debugger.db
└── agent_debugger.db.backup
```

**Rationale:** Database files are runtime data, not source code. A dedicated `data/` directory keeps them organized and makes it easy to exclude from backups and version control.

#### 2. Create `docs/sessions/` directory

Archive AI session notes:

```
docs/sessions/
├── .gitkeep
├── TESTING_FINAL_SUMMARY.md
├── TESTING_IMPROVEMENT_PLAN.md
├── TESTING_LEARNINGS_AND_RECOMMENDATIONS.md
├── TESTING_NEXT_ITERation.md
├── TESTING_NEXT_STEPS.md
├── TESTING_PROGRESS_REPORT.md
├── TESTING_QUICK_START.md
├── TESTING_SESSION_SUMMARY.md
└── TESTING_SUMMARY.md
```

**Rationale:** These files are valuable session history but shouldn't clutter the root. Archiving them preserves their content for reference.

#### 3. Move `LEARNING.md` to `docs/`

```
docs/LEARNING.md
```

**Rationale:** This is project documentation and belongs with other documentation files.

### `.gitignore` Audit

Update `.gitignore` to include:

```gitignore
# Database files (now in data/)
*.db
*.db.backup
data/

# Python caches (verify these exist)
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
*.pyo

# Build artifacts
dist/
*.egg-info/
build/

# Coverage
.coverage
htmlcov/
```

**Note:** `dist/` is intentionally tracked per project requirements, so it should NOT be added to `.gitignore`.

## Files That Stay at Root

The following were reviewed and will remain at root:

| Item | Reason |
|------|--------|
| `venv/`, `.venv/`, `.venv-ci/` | Three distinct virtual environments, each serving a purpose |
| `old_docs/` | Still needed at root level |
| `cli.py` | Standard entry point location |
| `dist/` | Intentionally tracked build artifacts |
| `pyproject.toml`, `pyproject-server.toml` | Monorepo-style config at root |

## Expected Result

**Before:** 30 files in root
**After:** ~22 files in root

Root directory will contain only:
- Entry point (`cli.py`)
- Configuration files (pyproject.toml, alembic.ini, docker-compose.yml, etc.)
- Standard project files (README.md, LICENSE, Makefile, etc.)
- Source directories (agent_debugger_sdk/, api/, auth/, etc.)
- Infrastructure directories (docs/, tests/, scripts/, etc.)

## Implementation Notes

1. Create new directories with `.gitkeep` files
2. Move files using `git mv` to preserve history
3. Update any hardcoded paths that reference moved files
4. Update `.gitignore`
5. Verify tests still pass
6. Commit changes
