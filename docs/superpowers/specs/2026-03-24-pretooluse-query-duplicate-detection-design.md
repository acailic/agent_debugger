# PreToolUse Hook: Query Duplicate Detection

**Date:** 2026-03-24
**Status:** Approved

## Purpose

Block edits that introduce duplicate SQLAlchemy query patterns in `api/`, `auth/`, and `collector/` directories. Enforces reuse of existing repository methods to maintain code cleanliness and reduce duplication.

## Problem Statement
When editing API routes or auth code, developers (including AI assistants) may write raw SQLAlchemy queries instead of using existing repository methods. This leads to:
- Duplicated query logic
- Inconsistent patterns across the codebase
- Harder maintenance when queries need to change
- Missed optimization opportunities

## Solution
A PreToolUse hook that:
1. Intercepts `Edit`, `Write`, and `MultiEdit` tool calls
2. Checks if the target file is in scope directories
3. Extracts SQLAlchemy query shapes from the new code
4. Compares against known patterns in `storage/repository.py` and `auth/middleware.py`
5. Blocks the edit with a helpful message pointing to the existing method

## Scope
**Directories watched:**
- `api/**/*.py`
- `auth/**/*.py`
- `collector/**/*.py`

**Directories exempt:**
- `tests/**` - Test files should be free to write any queries needed

## Architecture

### Hook Flow
```
1. Extract file path being edited
2. If path not in scope → allow
3. Extract new/changed code content
4. Parse SQLAlchemy query patterns from new code
5. For each pattern, check against known patterns in:
   - storage/repository.py
   - auth/middleware.py
6. If duplicate found → block with message
7. Otherwise → allow
```

### Pattern Matching Approach
**Canonical Form:** Model name + sorted where conditions (order-independent)

**Example:**
```python
# Raw query
result = await db.execute(
    select(SessionModel).where(
        SessionModel.id == session_id,
        SessionModel.tenant_id == tenant_id,
    )
)

# Canonical form
"SessionModel.where[id, tenant_id]"
```

### Pattern Registry
Pre-computed patterns loaded from existing code:

```json
{
  "SessionModel.where[id, tenant_id]": {
    "method": "get_session",
    "file": "storage/repository.py",
    "line": 71
  },
  "SessionModel.where[tenant_id]": {
    "method": "list_sessions",
    "file": "storage/repository.py",
    "line": 91
  },
  "EventModel.join[SessionModel].where[tenant_id, session_id]": {
    "method": "get_event_tree / list_events",
    "file": "storage/repository.py",
    "line": 269
  },
  "CheckpointModel.join[SessionModel].where[tenant_id, session_id]": {
    "method": "list_checkpoints",
    "file": "storage/repository.py",
    "line": 343
  },
  "APIKeyModel.where[tenant_id, is_active]": {
    "method": "(auth query - consider creating AuthRepository)",
    "file": "api/auth_routes.py",
    "line": 52
  },
  "APIKeyModel.where[key_prefix.startswith, is_active]": {
    "method": "_resolve_tenant_from_key",
    "file": "auth/middleware.py",
    "line": 27
  }
}
```

## Hook Configuration

**File:** `.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "path=$(jq -r '.tool_input.file_path // .tool_input.path //); content=$(jq -r '.tool_input.new_string // .tool_input.old_string //'); if echo \"$path\" | grep -qE '(api/|auth/|collector/).*\\.py$' && ! echo \"$path\" | grep -qE 'tests/'; then python3 scripts/hooks/check_duplicate_queries.py --path \"$path\" --content \"$content\" --repo-root \"$PWD\"; fi"
          }
        ]
      }
    ]
  }
}
```

## Supporting Script

**File:** `scripts/hooks/check_duplicate_queries.py`

**Purpose:**
- Extract canonical query shapes from code
- Compare against pattern registry
- Return allow/deny decision with helpful message

**Key Functions:**
1. `extract_query_shapes(content: str) -> list[str]` - Extract canonical patterns
2. `load_patterns(repo_root: str) -> dict` - Load pattern registry
3. `check_duplicates(shapes, patterns) -> list[dict]` - Find matches

**Output Format:**
```json
// Allow
{"decision": "allow"}

// Deny with helpful message
{
  "decision": "deny",
  "reason": "⚠️ Duplicate query detected!\n\nPattern: SessionModel.where[id, tenant_id]\nExisting method: get_session\nLocation: storage/repository.py\n\nUse the existing method instead of writing a new query."
}
```

## Pattern Extraction Logic

**Patterns to detect:**
1. `select(Model)` statements
2. `.where(...)` clauses with conditions
3. `.join(Model, ...)` statements
4. Combined into canonical form: `Model.where[cond1, cond2]` or `Model.join[OtherModel].where[...]`

**Canonicalization:**
- Extract model name(s)
- Extract where condition field names (sorted alphabetically)
- Ignore values, focus on structure
- Order-independent matching

## Success Criteria
1. Hook correctly identifies existing patterns
2. Hook allows new patterns that don't exist
3. Hook blocks duplicate patterns with helpful messages
4. Hook doesn't significantly slow down editing
5. Hook works with Edit, Write, and MultiEdit tools

## Edge Cases
1. **Partial code snippets** - May not parse correctly,   - **Handling:** Gracefully allow if parsing fails
2. **Complex queries** - Subqueries, CTEs, etc.
   - **Handling:** May not catch all variants, allow by default
3. **Modified existing code** - Editing a file that already has the pattern
   - **Handling:** Check both old_string and new_string to detect if pattern is new or just being moved

## Future Enhancements
1. Auto-generate pattern registry from repository.py at hook runtime
2. Support suggesting refactor to create new repository method for legitimate new queries
3. Add exemption comments (e.g., `# @duplicate-allowed`)
4. Extend to frontend API call patterns
