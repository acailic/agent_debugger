"""Python version compatibility shims for the SDK.

Provides a single source of truth for version-dependent types
so individual modules don't duplicate compat boilerplate.
"""

from __future__ import annotations

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    from enum import StrEnum  # type: ignore[assignment]
else:

    class StrEnum(str, Enum):  # type: ignore[misc]
        """Compatibility shim for StrEnum in Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
