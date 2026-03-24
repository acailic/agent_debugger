# Repository Root Organization Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize repository root by moving database files, session notes, and documentation to appropriate directories while updating all path references.

**Architecture:** Simple file moves using `git mv` to preserve history, followed by path reference updates in code and config files. No code logic changes required.

**Tech Stack:** Git, Python, SQLite, Docker Compose, Alembic

---

## File Structure Changes

### New Directories
```
data/
├── .gitkeep
├── agent_debugger.db          # moved from root
└── agent_debugger.db.backup   # moved from root

docs/sessions/
├── .gitkeep
└── TESTING_*.md (9 files)     # moved from root
```

### Moved Files
- `LEARNING.md` → `docs/LEARNING.md`

### Modified Files (path updates)
- `storage/engine.py:13` - DEFAULT_SQLITE_URL
- `storage/migrations/env.py:24` - default URL fallback
- `scripts/seed_demo_sessions.py:22` - DATABASE_URL default
- `alembic.ini:4` - sqlalchemy.url
- `docker-compose.yml:7` - volume mount path

### Updated `.gitignore`
Add: `data/` and `*.db.backup`

---

## Parallelizable Tasks (Tasks 1-4 can run concurrently)

### Task 1: Create data/ Directory and Move Database Files

**Files:**
- Create: `data/.gitkeep`
- Move: `agent_debugger.db` → `data/agent_debugger.db`
- Move: `agent_debugger.db.backup` → `data/agent_debugger.db.backup`

- [ ] **Step 1: Create data directory with .gitkeep**

```bash
mkdir -p data && touch data/.gitkeep
```

- [ ] **Step 2: Move database files using git mv**

```bash
git mv agent_debugger.db data/agent_debugger.db
git mv agent_debugger.db.backup data/agent_debugger.db.backup
```

- [ ] **Step 3: Stage the changes**

```bash
git add data/
```

- [ ] **Step 4: Verify files moved correctly**

```bash
ls -la data/
```
Expected: `agent_debugger.db`, `agent_debugger.db.backup`, `.gitkeep` present

---

### Task 2: Create docs/sessions/ and Move Session Files

**Files:**
- Create: `docs/sessions/.gitkeep`
- Move: 9 `TESTING_*.md` files from root to `docs/sessions/`

- [ ] **Step 1: Create docs/sessions directory with .gitkeep**

```bash
mkdir -p docs/sessions && touch docs/sessions/.gitkeep
```

- [ ] **Step 2: Move all TESTING_*.md files**

```bash
git mv TESTING_*.md docs/sessions/
```

- [ ] **Step 3: Stage the changes**

```bash
git add docs/sessions/
```

- [ ] **Step 4: Verify files moved correctly**

```bash
ls docs/sessions/
```
Expected: 9 TESTING_*.md files + `.gitkeep` present

---

### Task 3: Move LEARNING.md to docs/

**Files:**
- Move: `LEARNING.md` → `docs/LEARNING.md`

- [ ] **Step 1: Move LEARNING.md using git mv**

```bash
git mv LEARNING.md docs/LEARNING.md
```

- [ ] **Step 2: Stage the changes**

```bash
git add docs/LEARNING.md
```

- [ ] **Step 3: Verify file moved correctly**

```bash
ls docs/LEARNING.md
```
Expected: file exists

---

### Task 4: Update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add data/ and *.db.backup to .gitignore**

Add after line 19 (after `*.db` entries):

```gitignore
# Database files (now in data/)
*.db.backup
data/
```

The current `.gitignore` already has:
- `*.db` (line 19)
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` (covered)
- `dist/` (already ignored - but directory exists at root, user wants to keep)

**Note:** Do NOT remove `dist/` from `.gitignore` - user confirmed to keep as-is.

- [ ] **Step 2: Stage the changes**

```bash
git add .gitignore
```

---

## Sequential Tasks (Must run after Tasks 1-4)

### Task 5: Update Path References in Code Files

**Files:**
- Modify: `storage/engine.py:13`
- Modify: `storage/migrations/env.py:24`
- Modify: `scripts/seed_demo_sessions.py:22`
- Modify: `alembic.ini:4`
- Modify: `docker-compose.yml:7`

**Rationale:** These files hardcode `./agent_debugger.db` which must change to `./data/agent_debugger.db`

- [ ] **Step 1: Update storage/engine.py**

Change line 13:
```python
# Before:
DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./agent_debugger.db"
# After:
DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./data/agent_debugger.db"
```

- [ ] **Step 2: Update storage/migrations/env.py**

Change line 24:
```python
# Before:
config.get_main_option("sqlalchemy.url", "sqlite+aiosqlite:///./agent_debugger.db"),
# After:
config.get_main_option("sqlalchemy.url", "sqlite+aiosqlite:///./data/agent_debugger.db"),
```

- [ ] **Step 3: Update scripts/seed_demo_sessions.py**

Change line 22:
```python
# Before:
DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./agent_debugger.db")
# After:
DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./data/agent_debugger.db")
```

- [ ] **Step 4: Update alembic.ini**

Change line 4:
```ini
# Before:
sqlalchemy.url = sqlite+aiosqlite:///./agent_debugger.db
# After:
sqlalchemy.url = sqlite+aiosqlite:///./data/agent_debugger.db
```

- [ ] **Step 5: Update docker-compose.yml**

Change line 7:
```yaml
# Before:
- ./agent_debugger.db:/app/agent_debugger.db
# After:
- ./data/agent_debugger.db:/app/data/agent_debugger.db
```

- [ ] **Step 6: Stage all modified files**

```bash
git add storage/engine.py storage/migrations/env.py scripts/seed_demo_sessions.py alembic.ini docker-compose.yml
```

---

### Task 6: Verify and Commit

- [ ] **Step 1: Run tests to verify nothing is broken**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Step 2: Verify root directory is cleaner**

```bash
ls -la | grep -E "^-" | wc -l
```
Expected: ~22 files (down from 30)

- [ ] **Step 3: Commit all changes**

```bash
git commit --author="acailic <acailic@users.noreply.github.com>" -m "$(cat <<'EOF'
refactor: reorganize repository structure

- Move database files to data/ directory
- Move TESTING_*.md session notes to docs/sessions/
- Move LEARNING.md to docs/
- Update path references in code and config files
- Add data/ and *.db.backup to .gitignore

Root directory reduced from 30 to ~22 files.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify commit succeeded**

```bash
git log -1 --oneline
```
Expected: Shows the new commit

---

## Summary

| Task | Description | Parallelizable |
|------|-------------|----------------|
| 1 | Create data/, move DB files | Yes |
| 2 | Create docs/sessions/, move files | Yes |
| 3 | Move LEARNING.md | Yes |
| 4 | Update .gitignore | Yes |
| 5 | Update path references | No (after 1-4) |
| 6 | Verify and commit | No (after 5) |

**Recommended execution:** Run Tasks 1-4 in parallel using subagents, then Tasks 5-6 sequentially.
