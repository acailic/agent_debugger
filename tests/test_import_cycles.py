"""Regression tests for package import boundaries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_collector_buffer_imports_without_circular_dependency():
    """collector.buffer should import cleanly in a fresh interpreter."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ("import sys, types; sys.modules['aiofiles'] = types.ModuleType('aiofiles'); import collector.buffer"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
