"""Curated enrichment metadata for demo benchmark sessions."""

from __future__ import annotations

SESSION_ENRICHMENT = {
    "seed-prompt-injection": {
        "total_tokens": 856,
        "total_cost_usd": 0.0042,
        "retention_tier": "summarized",
        "fix_note": "Added input sanitization and prompt boundary checks",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-evidence-grounding": {
        "total_tokens": 140,
        "total_cost_usd": 0.0021,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-multi-agent-dialogue": {
        "total_tokens": 412,
        "total_cost_usd": 0.0038,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-prompt-policy-shift": {
        "total_tokens": 164,
        "total_cost_usd": 0.0028,
        "retention_tier": "summarized",
        "fix_note": "Added policy consistency checks across turns",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-safety-escalation": {
        "total_tokens": 1987,
        "total_cost_usd": 0.0142,
        "retention_tier": "full",
        "fix_note": "Added output validation after tool call",
        "errors": 1,
        "behavior_alerts": 1,
    },
    "seed-looping-behavior": {
        "total_tokens": 1245,
        "total_cost_usd": 0.0089,
        "retention_tier": "summarized",
        "fix_note": "Added max iteration limit with circuit breaker",
        "errors": 0,
        "behavior_alerts": 2,
    },
    "seed-failure-cluster": {
        "total_tokens": 1567,
        "total_cost_usd": 0.0112,
        "retention_tier": "full",
        "fix_note": "Added pre-call validation and error recovery",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-replay-determinism": {
        "total_tokens": 289,
        "total_cost_usd": 0.0031,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-replay-breakpoints": {
        "total_tokens": 618,
        "total_cost_usd": 0.0049,
        "retention_tier": "full",
        "fix_note": "Replay presets now stop at the low-confidence refund decision before the blocked tool action.",
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-retention-recent-failure": {
        "total_tokens": 354,
        "total_cost_usd": 0.0029,
        "retention_tier": "summarized",
        "fix_note": "Recent refusal kept for investigation because the underlying balance snapshot race is still active.",
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-retention-stale-failure": {
        "total_tokens": 354,
        "total_cost_usd": 0.0029,
        "retention_tier": "downsampled",
        "fix_note": "Older refusal retained only as a compact digest after the balance snapshot issue cooled off.",
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-repair-memory": {
        "total_tokens": 934,
        "total_cost_usd": 0.0067,
        "retention_tier": "full",
        "fix_note": "Successful fix used approval preflight checks plus exponential backoff.",
        "errors": 1,
        "behavior_alerts": 0,
    },
}


def validate_session_enrichment(session_id: str, enrichment: dict[str, object]) -> None:
    """Validate curated enrichment metrics for demo seed sessions."""
    total_tokens = enrichment.get("total_tokens")
    total_cost_usd = enrichment.get("total_cost_usd")

    if not isinstance(total_tokens, int) or total_tokens <= 0:
        raise ValueError(f"Seed enrichment for {session_id} must define positive total_tokens")

    if not isinstance(total_cost_usd, (int, float)) or float(total_cost_usd) <= 0:
        raise ValueError(f"Seed enrichment for {session_id} must define positive total_cost_usd")
