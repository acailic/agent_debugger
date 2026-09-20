"""Safety tests for CUSTOM_CONDITION breakpoint predicates.

CUSTOM_CONDITION breakpoints must never execute arbitrary code. Conditions are
validated against a restricted grammar (see
``agent_debugger_sdk.core.stepper.validate_custom_condition``) and evaluated by
a recursive interpreter instead of eval(). These tests pin down both sides:
allowed predicates keep working through ``Breakpoint.should_trigger`` and every
forbidden construct fails with an explicit ValueError.
"""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.stepper import (
    AgentStepper,
    Breakpoint,
    BreakpointType,
    StepAction,
    evaluate_custom_condition,
    validate_custom_condition,
)


def make_event(
    importance: float = 0.5,
    data: dict | None = None,
    event_type: EventType = EventType.DECISION,
    name: str = "Decision",
) -> TraceEvent:
    """Create a single TraceEvent for predicate tests."""
    return TraceEvent(
        id="event_1",
        session_id="session_1",
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        event_type=event_type,
        name=name,
        data=data if data is not None else {},
        metadata={},
        importance=importance,
        upstream_event_ids=[],
        parent_id=None,
    )


def custom_breakpoint(condition: str) -> Breakpoint:
    """Create a CUSTOM_CONDITION breakpoint for the given predicate."""
    return Breakpoint(
        breakpoint_type=BreakpointType.CUSTOM_CONDITION,
        condition_value=condition,
    )


class TestAllowedPredicates:
    """Predicates within the supported grammar evaluate as plain Python would."""

    def test_numeric_comparison(self):
        event = make_event(importance=0.8)
        assert custom_breakpoint("event.importance > 0.7").should_trigger(event) is True
        assert custom_breakpoint("event.importance > 0.9").should_trigger(event) is False

    def test_string_equality_against_event_type(self):
        event = make_event(event_type=EventType.ERROR)
        assert custom_breakpoint("event.event_type == 'error'").should_trigger(event) is True
        assert custom_breakpoint("event.event_type == 'decision'").should_trigger(event) is False

    def test_mapping_subscript_and_and(self):
        event = make_event(importance=0.6, data={"status": "failed"})
        condition = "event.data['status'] == 'failed' and event.importance >= 0.5"
        assert custom_breakpoint(condition).should_trigger(event) is True
        assert custom_breakpoint(condition).should_trigger(make_event(importance=0.4, data={"status": "failed"})) is False
        assert custom_breakpoint(condition).should_trigger(make_event(importance=0.6, data={"status": "ok"})) is False

    def test_not_or_and_membership(self):
        event = make_event(importance=0.8, event_type=EventType.ERROR)
        assert custom_breakpoint("not event.importance < 0.5 or 'err' in event.event_type").should_trigger(event) is True

    def test_in_against_tuple_literal(self):
        event = make_event(event_type=EventType.DECISION)
        assert custom_breakpoint("event.event_type in ('decision', 'error')").should_trigger(event) is True
        assert custom_breakpoint("event.event_type not in ('decision', 'error')").should_trigger(event) is False

    def test_arithmetic_on_attributes(self):
        event = make_event(importance=0.8)
        assert custom_breakpoint("event.importance * 2 > 1.5").should_trigger(event) is True
        assert custom_breakpoint("event.importance ** 2 > 0.6").should_trigger(event) is True
        assert custom_breakpoint("event.importance % 2 == 0.5").should_trigger(make_event(importance=0.5)) is True

    def test_negative_numbers(self):
        event = make_event(importance=-0.5)
        assert custom_breakpoint("event.importance < -0.1").should_trigger(event) is True

    def test_chained_comparison(self):
        event = make_event(importance=0.6)
        assert custom_breakpoint("0.5 < event.importance < 0.7").should_trigger(event) is True

    def test_truthiness_matches_bool(self):
        event = make_event(data={"reasoning": "because"})
        assert custom_breakpoint("event.data['reasoning']").should_trigger(event) is True
        assert custom_breakpoint("event.data['reasoning']").should_trigger(make_event(data={"reasoning": ""})) is False
        assert custom_breakpoint("event").should_trigger(event) is True


class TestForbiddenConstructs:
    """Every construct outside the grammar raises an explicit ValueError."""

    @pytest.mark.parametrize(
        "condition",
        [
            # dunder / class escape hatches
            "event.__class__",
            "event.data['x'].__class__",
            "event.__dict__",
            # calls (the historical RCE vector)
            "event.foo()",
            "__import__('os')",
            "open('/etc/passwd')",
            "eval('1 + 1')",
            "len(event.name) > 2",
            # names other than event
            "x > 1",
            "event.importance > confidence",
            # lambdas / walrus
            "lambda x: x",
            "(x := 1)",
            # comprehensions
            "[x for x in event.data]",
            "{k: v for k, v in event.data.items()}",
            # f-strings
            "f'{event.importance}'",
            # subscripts with non-literal index
            "event.data[event.name]",
            "event.data[event.importance]",
            # disallowed operators
            "event.importance // 2",
            "event.importance >> 1",
            "event.importance << 1",
            "event.importance | 2",
            "event.importance & 2",
            "event.importance ^ 2",
            "~event.importance",
            "event is event",
            "event is not None",
            # starred / ternary / dict literals
            "[*event.data]",
            "event.importance if event.importance else 0",
            "{'a': 1}['a']",
            # size caps
            "event.importance > 0.5 and " * 9,  # 207 chars
            "0" + "+1" * 99,  # 199 chars but > 100 AST nodes
            # syntax errors surface the same way
            "event.importance >",
            "import os",
        ],
    )
    def test_unsupported_construct_raises(self, condition):
        with pytest.raises(ValueError, match="custom condition uses unsupported construct"):
            validate_custom_condition(condition)

    def test_should_trigger_propagates_error(self):
        # The explicit error must surface through should_trigger, not be
        # silently swallowed into False.
        breakpoint = custom_breakpoint("__import__('os').system('id')")
        with pytest.raises(ValueError, match="custom condition uses unsupported construct: function calls"):
            breakpoint.should_trigger(make_event())

    def test_non_string_condition_raises(self):
        with pytest.raises(ValueError, match="custom condition uses unsupported construct"):
            validate_custom_condition(42)  # type: ignore[arg-type]


class TestBehaviorPreservation:
    """Valid conditions keep the exact trigger semantics of the old evaluator."""

    def test_runtime_failures_return_false(self):
        # Missing attributes / keys / incomparable types / division by zero
        # used to be swallowed by the old `except Exception: return False`.
        event = make_event(importance=0.5, data={"status": "ok"})
        assert custom_breakpoint("event.missing > 1").should_trigger(event) is False
        assert custom_breakpoint("event.data['nope'] == 1").should_trigger(event) is False
        assert custom_breakpoint("event.name > 5").should_trigger(event) is False
        assert custom_breakpoint("event.importance / 0 > 1").should_trigger(event) is False

    def test_none_condition_value_is_falsy(self):
        # condition_value=None stringifies to "None" -> falsy, as before.
        breakpoint = Breakpoint(breakpoint_type=BreakpointType.CUSTOM_CONDITION)
        assert breakpoint.should_trigger(make_event()) is False

    def test_disabled_breakpoint_never_triggers(self):
        breakpoint = custom_breakpoint("event.importance > 0.1")
        breakpoint.enabled = False
        assert breakpoint.should_trigger(make_event(importance=0.9)) is False

    def test_continue_hits_breakpoint_exactly_like_event_type(self):
        events = [
            make_event(importance=0.5, event_type=EventType.AGENT_START, name="Start"),
            make_event(importance=0.8, event_type=EventType.DECISION, name="Decision"),
        ]
        events[1].id = "event_2"

        stepper = AgentStepper(events)
        stepper.set_breakpoint(
            breakpoint_type=BreakpointType.CUSTOM_CONDITION,
            condition_value="event.importance > 0.7",
        )
        result = stepper.step(StepAction.CONTINUE)

        assert result.breakpoint_hit is not None
        assert result.current_event is not None
        assert result.current_event.id == "event_2"
        assert result.breakpoint_hit.hit_count == 1

    def test_continue_completes_when_condition_matches_nothing(self):
        stepper = AgentStepper([make_event(importance=0.2)])
        stepper.set_breakpoint(
            breakpoint_type=BreakpointType.CUSTOM_CONDITION,
            condition_value="event.importance > 0.7",
        )
        result = stepper.step(StepAction.CONTINUE)
        assert result.breakpoint_hit is None
        assert stepper.state.completed is True

    def test_evaluate_custom_condition_helper(self):
        event = make_event(importance=0.9)
        assert evaluate_custom_condition("event.importance > 0.7", event) is True
        assert evaluate_custom_condition("event.importance < 0.7", event) is False
