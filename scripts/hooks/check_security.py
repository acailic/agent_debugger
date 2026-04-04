#!/usr/bin/env python3
"""
Security validation hook for file edits.

Checks for:
- Hardcoded secrets (passwords, API keys, tokens, etc.)
- Dangerous patterns (eval, exec, pickle.load, subprocess with shell=True, etc.)
- Path traversal vulnerabilities (os.path.join with user input, unvalidated paths)

Usage: check_security.py <file_path>
Output: {"decision":"allow"} on pass, {"decision":"deny","reason":"..."} on violation
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Security patterns to detect
SECURITY_PATTERNS = {
    "hardcoded_secrets": [
        # Common secret patterns
        r'password\s*=\s*["\'][^"\']+["\']',
        r'api_key\s*=\s*["\'][^"\']+["\']',
        r'apikey\s*=\s*["\'][^"\']+["\']',
        r'token\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']+["\']',
        r'private_key\s*=\s*["\'][^"\']+["\']',
        r'AWS_ACCESS_KEY_ID\s*=\s*["\'][^"\']+["\']',
        r'AWS_SECRET_ACCESS_KEY\s*=\s*["\'][^"\']+["\']',
        r'GITHUB_TOKEN\s*=\s*["\'][^"\']+["\']',
        r'SLACK_TOKEN\s*=\s*["\'][^"\']+["\']',
        r'DATABASE_URL\s*=\s*["\'][^"\']+["\']',
        r'CONNECTION_STRING\s*=\s*["\'][^"\']+["\']',
        # Base64-like secrets (often encoded credentials)
        r'(?:password|secret|token|api_key)\s*=\s*["\'][A-Za-z0-9+/=]{20,}["\']',
    ],
    "dangerous_patterns": [
        # Code execution risks
        r'\beval\s*\(',
        r'\bexec\s*\(',
        r'\b__import__\s*\(',
        # Deserialization risks
        r'pickle\.load\s*\(',
        r'pickle\.loads\s*\(',
        r'shelve\.open\s*\(',
        r'yaml\.load\s*\([^)]*\)',  # yaml.load without SafeLoader
        r'marshal\.load\s*\(',
        # Command injection risks
        r'subprocess\.(?:call|run|Popen)\s*\([^)]*\bshell\s*=\s*True',
        r'os\.system\s*\(',
        r'os\.popen\s*\(',
        r'commands\.(?:getoutput|getstatusoutput)\s*\(',
        # SQL injection risks (basic patterns)
        r'\.execute\s*\([^)]*\+[^)]*\)',  # String concatenation in execute
        r'\.execute\s*\([^)]*%[^)]*\)',    # String formatting in execute
        r'\.execute\s*\([^)]*f["\']',      # f-string in execute (risky)
    ],
    "path_traversal": [
        # Path traversal patterns
        r'open\s*\([^)]*\+\s*[^)]*\)',  # open with concatenated path
        r'Path\s*\([^)]*\+\s*[^)]*\)',  # Path with concatenated string
        r'os\.path\.join\s*\([^)]*\+\s*[^)]*\)',  # os.path.join with concatenation
        r'open\s*\([^,]*request\.',  # open with user request input
        r'open\s*\([^,]*form\.',     # open with form data
        r'open\s*\([^,]*args\.',     # open with args
    ]
}


# File extensions to check
CODE_EXTENSIONS = {
    '.py', '.pyi',  # Python
    '.ts', '.tsx', '.js', '.jsx',  # JavaScript/TypeScript
    '.json', '.yaml', '.yml',  # Config files
}


def should_check_file(file_path: Path) -> bool:
    """Check if file should be scanned for security issues."""
    if not file_path.exists():
        return False

    # Check file extension
    if file_path.suffix.lower() not in CODE_EXTENSIONS:
        return False

    return True


def check_content(content: str, file_path: Path) -> tuple[bool, list[str]]:
    """
    Check file content for security issues.

    Returns:
        (is_safe, list of issues found)
    """
    issues = []

    # Skip empty files
    if not content or not content.strip():
        return True, []

    for category, patterns in SECURITY_PATTERNS.items():
        for pattern in patterns:
            try:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    # Get line number
                    line_num = content[:match.start()].count('\n') + 1
                    line_content = content.split('\n')[line_num - 1].strip()

                    issues.append(
                        f"{category}: {pattern} at line {line_num}: '{line_content[:80]}'"
                    )
            except re.error:
                # Skip invalid regex patterns
                continue

    return len(issues) == 0, issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Security validation for file edits")
    parser.add_argument("file_path", help="Path to file to check")
    args = parser.parse_args()

    file_path = Path(args.file_path)

    # Handle missing or non-code files gracefully
    if not should_check_file(file_path):
        print('{"decision":"allow"}')
        return

    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        is_safe, issues = check_content(content, file_path)

        if is_safe:
            print('{"decision":"allow"}')
        else:
            reason = f"Security issues detected in {file_path.name}: " + "; ".join(issues[:3])
            if len(issues) > 3:
                reason += f" (and {len(issues) - 3} more)"
            print(json.dumps({"decision": "deny", "reason": reason}))

    except (OSError, IOError) as e:
        # On read errors, allow the operation
        print('{"decision":"allow"}')
        return


if __name__ == "__main__":
    main()
