"""Session-level trace analysis and adaptive ranking.

This package provides a facade for analyzing agent session events.
The main entry point is the :class:`TraceIntelligence` class.
"""

from .facade import TraceIntelligence
from .helpers import event_value as _event_value, mean as _mean

__all__ = [
    "TraceIntelligence",
    "_event_value",
    "_mean",
]
