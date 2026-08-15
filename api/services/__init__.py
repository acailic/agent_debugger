"""Backward-compatible facade over the services package.

The implementation lives in cohesive submodules (sessions, ingestion,
similarity, causal, analysis). Import from `api.services` as before;
new code may import from the submodules directly.
"""

from api.services.analysis import (
    analyze_redundancy,
    analyze_session_safety_report,
)
from api.services.causal import (
    analyze_causal_graph,
    extract_workflow_graph,
)
from api.services.ingestion import (
    DEFAULT_SSE_TIMEOUT,
    event_generator,
    persist_checkpoint,
    persist_event,
    persist_session_start,
    persist_session_update,
)
from api.services.sessions import (
    SESSION_ANALYSIS_CAP,
    analysis_summary,
    analyze_session,
    build_live_summary,
    compute_checkpoint_deltas,
    compute_dict_delta,
    enrich_sessions_for_listing,
    load_session_artifacts,
    normalize_checkpoint,
    normalize_event,
    normalize_session,
    require_session,
    should_refresh_replay_value,
)
from api.services.similarity import (
    FAILURE_SIMILARITY_THRESHOLD,
    find_similar_failures,
)

__all__ = [
    "SESSION_ANALYSIS_CAP",
    "normalize_session",
    "normalize_event",
    "normalize_checkpoint",
    "should_refresh_replay_value",
    "analysis_summary",
    "require_session",
    "load_session_artifacts",
    "analyze_session",
    "build_live_summary",
    "compute_dict_delta",
    "compute_checkpoint_deltas",
    "enrich_sessions_for_listing",
    "SESSION_ANALYSIS_CAP",
    "DEFAULT_SSE_TIMEOUT",
    "persist_session_start",
    "persist_session_update",
    "persist_event",
    "persist_checkpoint",
    "event_generator",
    "FAILURE_SIMILARITY_THRESHOLD",
    "find_similar_failures",
    "analyze_causal_graph",
    "extract_workflow_graph",
    "analyze_session_safety_report",
    "analyze_redundancy",
]
