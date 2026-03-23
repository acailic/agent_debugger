"""Compatibility wrapper for importance scoring.

The scorer now lives in the SDK so trace emission does not import collector
modules. Re-export it here to preserve the existing collector import path.
"""

from agent_debugger_sdk.core.scorer import ImportanceScorer
from agent_debugger_sdk.core.scorer import get_importance_scorer

__all__ = ["ImportanceScorer", "get_importance_scorer"]
