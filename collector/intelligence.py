"""Session-level trace analysis and adaptive ranking.

This module re-exports the TraceIntelligence facade from the intelligence
subpackage for backward compatibility. All new code should import from
collector.intelligence.facade directly.
"""

from __future__ import annotations

from .intelligence.facade import TraceIntelligence
from .intelligence.helpers import event_value as _event_value
from .intelligence.helpers import mean as _mean

__all__ = ["TraceIntelligence", "_event_value", "_mean"]
