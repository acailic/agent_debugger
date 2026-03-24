#!/usr/bin/env python3
"""PreToolUse hook to detect duplicate SQLAlchemy query patterns.

Blocks edits that introduce queries already in storage/repository.py or auth/middleware.py
"""
import argparse
import json
import re
import sys
from pathlib import Path


# Pre-computed patterns loaded from existing code
PATTERNS = {
    "SessionModel.where[id, tenant_id]": {
        "method": "get_session",
        "file": "storage/repository.py",
    },
    "SessionModel.where[tenant_id]": {
        "method": "list_sessions",
        "file": "storage/repository.py"
    },
    "EventModel.join[SessionModel].where[tenant_id, session_id]": {
        "method": "get_event_tree",
        "file": "storage/repository.py",
    },
    "EventModel.where[id]": {
        "method": "get_event",
        "file": "storage/repository.py"
    },
    "EventModel.where[session_id]": {
        "method": "list_events",
        "file": "storage/repository.py"
    },
    "CheckpointModel.join[SessionModel].where[tenant_id, session_id]": {
        "method": "list_checkpoints",
        "file": "storage/repository.py"
    },
    "CheckpointModel.where[id]": {
        "method": "get_checkpoint",
        "file": "storage/repository.py"
    },
    "APIKeyModel.where[tenant_id, is_active]": {
        "method": "(auth query - consider auth_repository)",
        "file": "api/auth_routes.py",
    },
    "APIKeyModel.where[key_prefix.startswith, is_active]": {
        "method": "_resolve_tenant_from_key",
        "file": "auth/middleware.py"
    },
}


SCOPE_DIRS = ["api/", "auth/", "collector/"]
EXEMPT_DIRS = ["tests/"]


def extract_query_shapes(content: str) -> list[str]:
    """Extract canonical query shapes from code."""
    shapes = []
    select_pattern = r"select\((\w+)\)"
    for match in re.finditer(select_pattern, content):
        model = match.group(1)
        start = match.end()
        remaining = content[start:]
        where_match = re.search(r"\.where\(([^)]+)\)", remaining[start:])
        if where_match:
            where_clause = where_match.group(1)
            conditions = re.findall(r"(\w+)\.(\w+)\s*==", where_clause)
            if conditions:
                cond_names = sorted(set([c[1] for c in conditions))
                shapes.append(f"{model}.where[{', '.join(cond_names)}]")
    return shapes


def check_duplicates(content: str) -> list[dict]:
    """Check content against known patterns."""
    duplicates = []
    for shape in extract_query_shapes(content):
        if shape in PATTERNS:
            info = PATTERNS[shape]
            duplicates.append({
                "shape": shape,
                "method": info["method"],
                "file": info["file"],
            })
    return {"duplicates": duplicates, "shapes_found": shapes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--content", required=True)
    args = parser.parse_args()

    path = args.path
    content = args.content.strip() if args.content else ""

    # Check path is in scope
    in_scope = any(path.startswith(d) for d in SCOPE_DIRS)
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)

    # Check if exempt
    if any(path.startswith(d) for d in EXEMPT_DIRS):
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)

    # Check for duplicates
    duplicates = check_duplicates(content)
    if duplicates:
        dup = duplicates[0]
        print(json.dumps({
            "decision": "deny",
            "reason": f"""Duplicate query detected!

Pattern: {dup['shape']}
Existing method: {dup['method']}
Location: {dup['file']}

Use this existing method instead of writing a new query.
Add `# @duplicate-allowed` to your code to bypass."""
        sys.exit(0)


    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
