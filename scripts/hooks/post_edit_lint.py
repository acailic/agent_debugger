#!/usr/bin/env python3
"""
PostToolUse hook: Post-Edit Lint Validation

Runs targeted linters after file edits.
- For .py files: runs ruff check
- For .ts/.tsx files: runs eslint in frontend
- For other files: silently passes

This is informational only (exit 0 always) - just prints warnings.
"""

import subprocess
import sys
from pathlib import Path


def lint_file(file_path: str) -> list[str]:
    """
    Run appropriate linter for the file type.

    Returns list of warning messages (empty if no issues).
    """
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        return []

    suffix = file_path.suffix
    warnings = []

    if suffix == ".py":
        # Run ruff check for Python files
        try:
            result = subprocess.run(
                ["ruff", "check", "--select=E,F,I", str(file_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0 and result.stdout:
                warnings.append(f"Ruff issues in {file_path.name}:\n{result.stdout}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    elif suffix in {".ts", ".tsx"}:
        # Run eslint for TypeScript files
        try:
            # Get frontend directory (go up from hooks dir to repo root, then into frontend)
            repo_root = Path(__file__).parent.parent.parent
            frontend_dir = repo_root / "frontend"

            if frontend_dir.exists():
                result = subprocess.run(
                    ["npx", "eslint", str(file_path)],
                    capture_output=True,
                    text=True,
                    cwd=str(frontend_dir),
                    timeout=15
                )
                if result.returncode != 0 and (result.stdout or result.stderr):
                    output = result.stdout or result.stderr
                    warnings.append(f"ESLint issues in {file_path.name}:\n{output}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return warnings


def main():
    if len(sys.argv) < 2:
        sys.exit(0)

    file_path = sys.argv[1]
    warnings = lint_file(file_path)

    if warnings:
        for warning in warnings:
            print(f"\n⚠️  {warning}", file=sys.stderr)

    # Always exit 0 - this is informational only
    sys.exit(0)


if __name__ == "__main__":
    main()
