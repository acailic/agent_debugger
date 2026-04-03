"""Minimal LangChain-compatible test doubles for optional-dependency tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeHumanMessage:
    content: str

    def __repr__(self) -> str:
        return self.content


@dataclass
class FakeAIMessage:
    content: str

    def __repr__(self) -> str:
        return self.content
