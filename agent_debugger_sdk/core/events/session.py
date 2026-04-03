"""Session dataclass for agent execution tracking."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .base import SessionStatus


@dataclass(kw_only=True)
class Session:
    """Dataclass representing a complete agent execution session.

    A session encompasses the entire execution of an agent from start
    to finish, including all events, metrics, and configuration.

    Attributes:
        id: Unique session identifier (UUID)
        agent_name: Name/identifier of the agent
        framework: The agent framework used (pydantic_ai, langchain, autogen)
        started_at: When the session started
        ended_at: When the session ended (None if still running)
        status: Current session status (running, completed, error)
        total_tokens: Total tokens used across all LLM calls
        total_cost_usd: Total estimated cost in USD
        tool_calls: Number of tool calls made
        llm_calls: Number of LLM API calls made
        errors: Number of errors encountered
        config: Agent configuration settings
        tags: Tags for categorizing and filtering sessions
        fix_note: Developer notes on how a failure was fixed
        search_similarity: Semantic similarity score from search queries
        search_highlights: Highlight snippets from matched search results
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    framework: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    status: SessionStatus = SessionStatus.RUNNING
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0
    replay_value: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    fix_note: str | None = None
    search_similarity: float | None = None
    search_highlights: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = SessionStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a dictionary."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "framework": self.framework,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": str(self.status),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
            "replay_value": self.replay_value,
            "config": self.config,
            "tags": self.tags,
            "fix_note": self.fix_note,
            "search_similarity": self.search_similarity,
            "search_highlights": self.search_highlights,
        }
