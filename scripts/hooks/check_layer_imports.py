#!/usr/bin/env python3
"""
PreToolUse hook: Architecture Boundary Enforcement

Checks Python files for forbidden cross-layer imports.
Forbidden patterns:
  - agent_debugger_sdk/ files should NOT import from api, storage, collector, auth, redaction
  - storage/ files should NOT import from api or collector
  - auth/ files should NOT import from api or collector
"""

import sys
import json
import re
from pathlib import Path


def check_file_for_violations(file_path: str) -> dict:
    """
    Check a Python file for architectural import violations.

    Returns: {"decision": "allow"} or {"decision": "deny", "reason": "..."}
    """
    file_path = Path(file_path).resolve()

    # Handle missing or non-Python files gracefully
    if not file_path.exists():
        return {"decision": "allow"}
    if file_path.suffix != ".py":
        return {"decision": "allow"}

    # Read file content
    try:
        content = file_path.read_text()
    except Exception:
        return {"decision": "allow"}

    # Define forbidden import rules based on file location
    rules = [
        # SDK files should not import from server/runtime layers
        {
            "path_prefix": "agent_debugger_sdk",
            "forbidden_imports": ["from api ", "import api", "from storage ", "import storage",
                                  "from collector ", "import collector", "from auth ", "import auth",
                                  "from redaction ", "import redaction"],
            "reason": "SDK layer (agent_debugger_sdk/) should not import from server/runtime layers (api, storage, collector, auth, redaction)"
        },
        # Storage layer should not import from API or collector
        {
            "path_prefix": "storage",
            "forbidden_imports": ["from api ", "import api", "from collector ", "import collector"],
            "reason": "Storage layer should not import from API or collector layers"
        },
        # Auth layer should not import from API or collector
        {
            "path_prefix": "auth",
            "forbidden_imports": ["from api ", "import api", "from collector ", "import collector"],
            "reason": "Auth layer should not import from API or collector layers"
        },
    ]

    # Check each rule
    file_str = str(file_path)
    for rule in rules:
        if f"/{rule['path_prefix']}/" in file_str or file_str.endswith(f"/{rule['path_prefix']}"):
            for forbidden in rule['forbidden_imports']:
                if forbidden in content:
                    return {
                        "decision": "deny",
                        "reason": f"Architecture violation in {file_path.relative_to(Path.cwd())}: {rule['reason']}. Found forbidden import pattern: '{forbidden}'"
                    }

    return {"decision": "allow"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)

    file_path = sys.argv[1]
    result = check_file_for_violations(file_path)
    print(json.dumps(result))

    # Exit 0 even on deny (the JSON output controls the decision)
    sys.exit(0)


if __name__ == "__main__":
    main()
