"""Tests for agent_debugger_sdk.auto_patch.frame_capture.

Covers the auto_capture_function decorator, in particular its
module_filter param (a documented public API param that previously had
no runtime effect and no test coverage).
"""

from __future__ import annotations

import pytest

from agent_debugger_sdk.auto_patch.frame_capture import (
    FrameCaptureConfig,
    auto_capture_function,
    disable_frame_capture,
    enable_frame_capture,
    get_active_session,
)

# A filter token that will never appear in a real module path, so the
# decorated function is guaranteed NOT to be captured under this filter.
_NO_MATCH_FILTER = "definitely_not_a_real_module_xyz"

# A filter token that matches the test module's own qualified path. The
# module path of these module-level test helpers is built from __module__,
# which contains "test_frame_capture".
_MATCH_FILTER = "test_frame_capture"


@auto_capture_function(module_filter=_MATCH_FILTER)
def _captured_adder(a: int, b: int) -> int:
    return a + b


@auto_capture_function(module_filter=_NO_MATCH_FILTER)
def _skipped_adder(a: int, b: int) -> int:
    return a + b


@auto_capture_function()
def _unfiltered_adder(a: int, b: int) -> int:
    return a + b


@pytest.fixture()
def active_session():
    """Enable frame capture for one test and always tear it down."""
    trace_id = enable_frame_capture(config=FrameCaptureConfig(enabled=True))
    assert trace_id, "enable_frame_capture should return a non-empty trace id"
    try:
        yield get_active_session()
    finally:
        disable_frame_capture()


def test_passthrough_when_no_session_active() -> None:
    """With no session active the decorator is a transparent passthrough."""
    # Guard: ensure no leftover active session from another test.
    assert get_active_session() is None
    assert _captured_adder(2, 3) == 5


def test_module_filter_match_captures_frame(active_session) -> None:  # type: ignore[no-untyped-def]
    """When module_filter matches the function's module, a frame is captured."""
    before = active_session.frames_captured
    assert _captured_adder(2, 3) == 5
    assert active_session.frames_captured == before + 1


def test_module_filter_mismatch_skips_capture_but_runs(active_session) -> None:  # type: ignore[no-untyped-def]
    """A non-matching module_filter suppresses capture but still runs the fn."""
    before = active_session.frames_captured
    assert _skipped_adder(4, 6) == 10
    assert active_session.frames_captured == before, "non-matching filter must not capture"


def test_no_module_filter_uses_session_decision(active_session) -> None:  # type: ignore[no-untyped-def]
    """Without a decorator-level filter, the session's own decision applies."""
    before = active_session.frames_captured
    assert _unfiltered_adder(1, 1) == 2
    assert active_session.frames_captured == before + 1
