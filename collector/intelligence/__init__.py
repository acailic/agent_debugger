"""Session-level trace analysis and adaptive ranking.

This package provides a facade for analyzing agent session events.
The main entry point is the :class:`TraceIntelligence` class.
"""

from .facade import TraceIntelligence

__all__ = [
    "TraceIntelligence",
]
