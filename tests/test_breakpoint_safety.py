"""Safety tests for CUSTOM_CONDITION breakpoint predicates.

CUSTOM_CONDITION breakpoints must never execute arbitrary code. Conditions are
validated against a restricted grammar (see
``agent_debugger_sdk.core.stepper.validate_custom_condition``) and evaluated by
a recursive interpreter instead of eval(). These tests pin down both sides:
allowed predicates keep working through ``Breakpoint.should_trigger`` and every
forbidden construct fails with an explicit ValueError.
"""

import ast
from datetime import datetime, timezone

import pytest

import agent_debugger_sdk.core.stepper as stepper_module
from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.stepper import (
    AgentStepper,
    Breakpoint,
    BreakpointType,
    StepAction,
    _eval_node,
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


class TestPreMutationValidation:
    """Breakpoints are rejected at creation/import time, not during evaluation."""

    def test_set_breakpoint_rejects_invalid_condition_without_mutating_state(self):
        stepper = AgentStepper([make_event()])
        with pytest.raises(ValueError, match="custom condition uses unsupported construct"):
            stepper.set_breakpoint(
                breakpoint_type=BreakpointType.CUSTOM_CONDITION,
                condition_value="len(event.data) > 0",
            )
        assert stepper.state.breakpoints == [], "rejected breakpoint must not be appended"

    def test_set_breakpoint_accepts_valid_condition(self):
        stepper = AgentStepper([make_event()])
        bp = stepper.set_breakpoint(
            breakpoint_type=BreakpointType.CUSTOM_CONDITION,
            condition_value="event.importance > 0.5",
        )
        assert bp.condition_value == "event.importance > 0.5"
        assert len(stepper.state.breakpoints) == 1

    @staticmethod
    def _state_with_breakpoint(condition: str) -> dict:
        return {
            "state": {
                "current_event_index": 0,
                "current_event_id": "",
                "breakpoints": [
                    {
                        "breakpoint_id": "bp-import",
                        "breakpoint_type": "custom_condition",
                        "condition_value": condition,
                        "description": "",
                        "enabled": True,
                        "hit_count": 0,
                        "created_at": "2026-09-20T00:00:00+00:00",
                    }
                ],
                "step_history": [],
                "paused": True,
                "completed": False,
            },
            "branches": [],
            "events_count": 1,
        }

    def test_import_state_rejects_invalid_condition_without_mutating_state(self):
        stepper = AgentStepper([make_event()])
        with pytest.raises(ValueError, match="custom condition uses unsupported construct"):
            stepper.import_state(self._state_with_breakpoint("len(event.data) > 0"))
        assert stepper.state.breakpoints == [], "rejected import must leave state untouched"

    def test_import_state_accepts_valid_condition_round_trip(self):
        source = AgentStepper([make_event()])
        source.set_breakpoint(
            breakpoint_type=BreakpointType.CUSTOM_CONDITION,
            condition_value="event.importance > 0.5",
        )
        target = AgentStepper([make_event()])
        target.import_state(source.export_state())
        imported = target.state.breakpoints[0]
        assert imported["condition_value"] == "event.importance > 0.5"


class TestBoundedEvaluation:
    """Runtime caps close the residual unbounded-work vectors.

    Size/node caps bound the expression text, not the work an evaluation can
    do. These tests pin the operator-level caps (repetition count, produced
    sequence length) and prove each rejection happens *before* the real
    Python operator runs, using a recording operator stub that fails the test
    if it is ever invoked.
    """

    @staticmethod
    def _forbidden_operator(calls: list):
        """Replace a binop entry: record and fail if the real operator runs."""

        def _op(left, right):
            calls.append((left, right))
            raise AssertionError("operator invoked before bound check")

        return _op

    def test_repetition_count_cap_is_symmetric(self, monkeypatch):
        # Historically only `seq * int` was capped; `int * seq` repeated too.
        calls: list = []
        monkeypatch.setitem(
            stepper_module._ALLOWED_BINOPS, ast.Mult, self._forbidden_operator(calls)
        )
        event = make_event(name="n" * 16)

        tree = validate_custom_condition("20000 * event.name")
        with pytest.raises(OverflowError, match="sequence repetition too large"):
            _eval_node(tree.body, event)
        assert calls == [], "bound check must fire before the multiplication"

    def test_repetition_result_length_cap(self, monkeypatch):
        calls: list = []
        monkeypatch.setitem(
            stepper_module._ALLOWED_BINOPS, ast.Mult, self._forbidden_operator(calls)
        )
        # 500 repeats of a 600k-char attribute value -> 300M chars: the
        # repeat count is small, only the produced length is over budget.
        event = make_event(data={"pad": "a" * 600_000})

        tree = validate_custom_condition("event.data['pad'] * 500")
        with pytest.raises(OverflowError, match="sequence repetition too large"):
            _eval_node(tree.body, event)
        assert calls == []

    def test_concatenation_length_cap_blocks_balanced_doubling(self, monkeypatch):
        calls: list = []
        monkeypatch.setitem(
            stepper_module._ALLOWED_BINOPS, ast.Add, self._forbidden_operator(calls)
        )
        # Without a total-length cap, a balanced tree of `+` nodes could
        # double one large attribute value on every level (~2^50 copies).
        event = make_event(data={"pad": "a" * 600_000})

        tree = validate_custom_condition("event.data['pad'] + event.data['pad']")
        with pytest.raises(OverflowError, match="sequence concatenation too large"):
            _eval_node(tree.body, event)
        assert calls == []

    def test_printf_style_formatting_is_rejected_before_the_operator(self, monkeypatch):
        calls: list = []
        monkeypatch.setitem(
            stepper_module._ALLOWED_BINOPS, ast.Mod, self._forbidden_operator(calls)
        )
        # An attribute-driven format string like '%999999999d' would allocate
        # gigabytes inside str.__mod__; the grammar cannot see operand types,
        # so the runtime rejects str/bytes % outright.
        event = make_event(data={"fmt": "%" + "9" * 9 + "d"})

        tree = validate_custom_condition("event.data['fmt'] % 2")
        with pytest.raises(OverflowError, match="string formatting is not allowed"):
            _eval_node(tree.body, event)
        assert calls == []

    def test_numeric_modulo_still_works(self):
        event = make_event(importance=0.5)
        assert evaluate_custom_condition("event.importance % 2 == 0.5", event) is True

    def test_over_cap_operations_are_no_match_not_crash(self):
        event = make_event(name="n" * 16, data={"pad": "a" * 600_000})
        # evaluate_custom_condition treats runtime failures as no-match.
        assert evaluate_custom_condition("20000 * event.name", event) is False
        assert evaluate_custom_condition("event.data['pad'] * 500", event) is False
        assert evaluate_custom_condition("event.data['pad'] + event.data['pad']", event) is False
        assert (
            Breakpoint(
                breakpoint_type=BreakpointType.CUSTOM_CONDITION,
                condition_value="20000 * event.name",
            ).should_trigger(event)
            is False
        )

    def test_small_repetition_and_concatenation_still_work(self):
        event = make_event(name="Decision")
        assert evaluate_custom_condition("'ab' * 3 == 'ababab'", event) is True
        assert evaluate_custom_condition("event.name + '!' == 'Decision!'", event) is True
        assert evaluate_custom_condition("event.name * 2 == 'DecisionDecision'", event) is True
