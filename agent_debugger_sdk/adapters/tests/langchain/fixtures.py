"""Tests for LangChain adapter."""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer

class MockGeneration:
    """Mock LangChain generation."""

    def __init__(self, text: str):
        self.text = text


class MockLLMResult:
    """Mock LangChain LLM result."""

    def __init__(self, text: str = "Hello!"):
        self.generations = [[MockGeneration(text)]]
        self.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}

