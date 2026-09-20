"""Interactive breakpoint and step-through debugging for agent sessions.

Based on traditional debugger paradigms adapted for AI agent execution, this
module provides primitives for setting breakpoints, stepping through execution,
inspecting agent state, and branching from any breakpoint.

Key capabilities:
- Breakpoint model: markers on event types, tool names, confidence thresholds, safety outcomes
- StepControls: step_into (next decision), step_over (skip tool internals), step_out (return to parent)
- StateInspector: show agent context at each breakpoint
- BranchAndReplay: create alternative paths from any breakpoint
- CUSTOM_CONDITION breakpoints use a restricted predicate language (see
  ``validate_custom_condition``) evaluated without eval/exec, so breakpoint
  conditions can never execute arbitrary code in the host process.
  Predicates are validated pre-mutation at every materialization boundary
  (``AgentStepper.set_breakpoint`` and ``AgentStepper.import_state``), and
  evaluation is bounded (expression size, AST node count, exponents, and
  sequence repetition/concatenation sizes — see ``validate_custom_condition``)
"""

from __future__ import annotations

import ast
import operator
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core._compat import StrEnum
from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "BreakpointType",
    "StepAction",
    "Breakpoint",
    "StepperState",
    "StepResult",
    "BranchPoint",
    "AgentStepper",
    "validate_custom_condition",
    "evaluate_custom_condition",
]


class BreakpointType(StrEnum):
    """Types of breakpoints for agent execution."""

    EVENT_TYPE = "event_type"  # Break on specific event type
    TOOL_NAME = "tool_name"  # Break when specific tool is called
    CONFIDENCE_THRESHOLD = "confidence_threshold"  # Break on confidence below threshold
    SAFETY_OUTCOME = "safety_outcome"  # Break on specific safety outcome
    CUSTOM_CONDITION = "custom_condition"  # Break on restricted predicate over `event` (see validate_custom_condition)
    EVENT_ID = "event_id"  # Break at specific event ID


class StepAction(StrEnum):
    """Step actions for navigation through execution."""

    STEP_INTO = "step_into"  # Step into next decision/tool call
    STEP_OVER = "step_over"  # Skip over tool internals
    STEP_OUT = "step_out"  # Return to parent context
    CONTINUE = "continue"  # Continue to next breakpoint
    RUN_TO = "run_to"  # Run to specific event ID


# --- Restricted predicate language for CUSTOM_CONDITION breakpoints ------------
#
# CUSTOM_CONDITION breakpoints historically evaluated their condition string
# with eval(). That was a remote-code-execution vector for anyone able to reach
# the breakpoint API. Conditions are now parsed to an AST and checked against a
# strict allowlist before being evaluated by a small recursive interpreter, so
# eval/exec are never used and no unsupported construct can execute.

_MAX_CONDITION_LENGTH = 200
_MAX_CONDITION_NODES = 100
# Runtime caps so a grammatically valid expression still cannot make the
# interpreter do unbounded work or allocate unbounded memory:
# - sequence repetition count (``event.name * 5000``), applied symmetrically
#   to ``seq * int`` and ``int * seq``;
# - total length of any sequence produced by repetition or concatenation
#   (``+``/``*`` over str/bytes/list/tuple), so balanced ``a + a + ...`` trees
#   cannot double a large attribute value into gigabytes.
_MAX_SEQ_REPEAT = 10_000
_MAX_SEQ_LENGTH = 1_000_000

_UNSUPPORTED = "custom condition uses unsupported construct: {reason}"

_ALLOWED_COMPARE_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}

_ALLOWED_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNSUPPORTED_NODE_REASONS: dict[type[ast.AST], str] = {
    ast.Call: "function calls are not allowed",
    ast.Lambda: "lambda expressions are not allowed",
    ast.ListComp: "comprehensions are not allowed",
    ast.SetComp: "comprehensions are not allowed",
    ast.DictComp: "comprehensions are not allowed",
    ast.GeneratorExp: "comprehensions are not allowed",
    ast.JoinedStr: "f-strings are not allowed",
    ast.FormattedValue: "f-strings are not allowed",
    ast.Starred: "starred expressions are not allowed",
    ast.IfExp: "conditional expressions are not allowed",
    ast.NamedExpr: "assignment expressions are not allowed",
    ast.Await: "await expressions are not allowed",
    ast.Yield: "yield expressions are not allowed",
    ast.YieldFrom: "yield expressions are not allowed",
    ast.Dict: "dict literals are not allowed",
    ast.Import: "import is not allowed",
    ast.ImportFrom: "import is not allowed",
}


def _unsupported(reason: str) -> ValueError:
    return ValueError(_UNSUPPORTED.format(reason=reason))


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _validate_node(node: ast.AST) -> None:
    """Recursively check that an AST node only uses allowlisted constructs.

    Raises:
        ValueError: If the node (or any child) uses a forbidden construct.
    """
    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (bool, int, float, complex, str)):
            return
        raise _unsupported(f"constants of type {type(node.value).__name__} are not allowed")

    if isinstance(node, ast.Name):
        if node.id != "event":
            raise _unsupported(f"names other than 'event' are not allowed (got '{node.id}')")
        return

    if isinstance(node, ast.Attribute):
        _validate_node(node.value)
        # Dunder names are rejected at validation time so evaluation can rely on
        # plain getattr() without ever exposing __class__/__globals__/etc.
        if _is_dunder(node.attr):
            raise _unsupported(f"dunder attribute access is not allowed (.{node.attr})")
        return

    if isinstance(node, ast.Subscript):
        _validate_node(node.value)
        sl = node.slice
        if not (isinstance(sl, ast.Constant) and isinstance(sl.value, (str, int))):
            raise _unsupported("subscript index must be a literal string or number")
        return

    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _validate_node(value)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            raise _unsupported(f"unary operator {type(node.op).__name__} is not allowed")
        _validate_node(node.operand)
        return

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BINOPS:
            raise _unsupported(f"binary operator {type(node.op).__name__} is not allowed")
        _validate_node(node.left)
        _validate_node(node.right)
        return

    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _ALLOWED_COMPARE_OPS:
                raise _unsupported(f"comparison operator {type(op).__name__} is not allowed")
        _validate_node(node.left)
        for comparator in node.comparators:
            _validate_node(comparator)
        return

    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for element in node.elts:
            _validate_node(element)
        return

    reason = _UNSUPPORTED_NODE_REASONS.get(type(node))
    if reason is None:
        reason = f"{type(node).__name__} expressions are not allowed"
    raise _unsupported(reason)


def validate_custom_condition(condition: str) -> ast.Expression:
    """Validate a CUSTOM_CONDITION predicate against the supported grammar.

    The supported grammar is a strict subset of Python expressions:

    - boolean operators ``and`` / ``or`` and unary ``not``
    - comparisons ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``in``, ``not in``
      (``is`` / ``is not`` are not allowed)
    - arithmetic ``+``, ``-``, ``*``, ``/``, ``%``, ``**`` (no ``//``, shifts,
      or bitwise operators)
    - numeric and string constants, ``True`` / ``False`` / ``None``
    - attribute chains rooted at the single name ``event`` (no dunder names)
    - ``event.data['key']``-style subscripts with a literal string or number
    - tuple/list/set literals of the above (e.g. for ``in`` comparisons)

    Forbidden (raises ValueError): calls, lambdas, comprehensions, f-strings,
    starred/walrus/await/yield expressions, names other than ``event``, dunder
    attribute access, non-literal subscripts, and expressions longer than 200
    characters or containing more than 100 AST nodes.

    Runtime bounds (enforced by ``evaluate_custom_condition`` so a valid
    expression also cannot do unbounded work): every evaluation applies at
    most one operator per AST node (≤ 100 per evaluation); ``**`` exponents
    are capped at magnitude 10 000; sequence repetition (``*`` between a
    str/bytes/list/tuple and an int, in either operand order) is capped at a
    repeat count of 10 000 and a produced length of 1 000 000 elements; and
    sequence concatenation (``+``) is capped at a combined length of
    1 000 000 elements. Printf-style string formatting (``str % args``) is
    rejected at evaluation time — its width/precision can demand unbounded
    allocation — while numeric ``%`` modulo is unaffected. Over-cap
    operations raise OverflowError before the underlying Python operator
    runs (no oversized allocation is attempted);
    ``evaluate_custom_condition`` converts that to a no-match (False), like
    any other runtime failure.

    Args:
        condition: The custom condition expression string

    Returns:
        The parsed (and validated) expression AST

    Raises:
        ValueError: If the condition uses an unsupported construct
    """
    if not isinstance(condition, str):
        raise _unsupported("condition must be a string")
    if len(condition) > _MAX_CONDITION_LENGTH:
        raise _unsupported(f"expression exceeds {_MAX_CONDITION_LENGTH} characters")
    try:
        tree = ast.parse(condition, mode="eval")
    except SyntaxError as exc:
        raise _unsupported(f"invalid syntax ({exc.msg})") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_CONDITION_NODES:
        raise _unsupported(f"expression exceeds {_MAX_CONDITION_NODES} AST nodes")
    _validate_node(tree.body)
    return tree


_SEQUENCE_TYPES = (str, bytes, list, tuple)


def _cap_repetition(left: Any, right: Any) -> None:
    """Reject sequence repetition that would exceed the runtime caps.

    Applies to both ``seq * int`` and ``int * seq`` (Python repeats either
    way), bounding the repeat count by ``_MAX_SEQ_REPEAT`` and the produced
    length by ``_MAX_SEQ_LENGTH``. Raises before the operator is invoked so no
    oversized allocation is attempted.
    """
    if isinstance(left, int) and isinstance(right, _SEQUENCE_TYPES):
        count, seq = left, right
    elif isinstance(right, int) and isinstance(left, _SEQUENCE_TYPES):
        count, seq = right, left
    else:
        return
    if abs(count) > _MAX_SEQ_REPEAT:
        raise OverflowError("sequence repetition too large")
    if abs(count) * len(seq) > _MAX_SEQ_LENGTH:
        raise OverflowError("sequence repetition too large")


def _cap_concatenation(left: Any, right: Any) -> None:
    """Reject sequence concatenation beyond ``_MAX_SEQ_LENGTH`` total length.

    Without this, a balanced tree of ``+`` nodes over one large attribute
    value could double it on every level (up to ~2^50 copies within the
    100-node cap). Raises before the operator is invoked.
    """
    if isinstance(left, _SEQUENCE_TYPES) and isinstance(right, _SEQUENCE_TYPES):
        if len(left) + len(right) > _MAX_SEQ_LENGTH:
            raise OverflowError("sequence concatenation too large")


def _eval_node(node: ast.AST, event: TraceEvent) -> Any:
    """Evaluate a previously validated condition AST against an event."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        # Validation guarantees the only allowed name is "event".
        return event

    if isinstance(node, ast.Attribute):
        return getattr(_eval_node(node.value, event), node.attr)

    if isinstance(node, ast.Subscript):
        return _eval_node(node.value, event)[_eval_node(node.slice, event)]

    if isinstance(node, ast.BoolOp):
        is_and = isinstance(node.op, ast.And)
        result: Any = True
        for value in node.values:
            result = _eval_node(value, event)
            if is_and and not result:
                return result
            if not is_and and result:
                return result
        return result

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _eval_node(node.operand, event)
        if isinstance(node.op, ast.USub):
            return -_eval_node(node.operand, event)
        return +_eval_node(node.operand, event)

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, event)
        right = _eval_node(node.right, event)
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 10000:
            # Cap exponents so a literal like 10**10**10 cannot stall evaluation.
            raise OverflowError("exponent too large")
        if isinstance(node.op, ast.Mult):
            _cap_repetition(left, right)
        elif isinstance(node.op, ast.Add):
            _cap_concatenation(left, right)
        elif isinstance(node.op, ast.Mod) and isinstance(left, (str, bytes)):
            # ``str % args`` is printf-style formatting: a width like
            # '%999999999d' (attribute-driven, so not visible at validation
            # time) would allocate gigabytes inside the operator.
            raise OverflowError("string formatting is not allowed")
        return _ALLOWED_BINOPS[type(node.op)](left, right)

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, event)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, event)
            if not _ALLOWED_COMPARE_OPS[type(op)](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(element, event) for element in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(element, event) for element in node.elts]
    if isinstance(node, ast.Set):
        return {_eval_node(element, event) for element in node.elts}

    # Unreachable for trees that passed validate_custom_condition().
    raise _unsupported(f"{type(node).__name__} expressions are not allowed")


def evaluate_custom_condition(condition: str, event: TraceEvent) -> bool:
    """Evaluate a CUSTOM_CONDITION predicate against an event, without eval.

    Conditions must satisfy the grammar documented in
    ``validate_custom_condition``; unsupported constructs raise ValueError
    instead of being silently skipped. Runtime failures while evaluating a
    grammatically valid condition (missing attribute, missing mapping key,
    incomparable types, division by zero, ...) return False, matching the
    historical behavior.

    Args:
        condition: The custom condition expression string
        event: Event to evaluate the condition against

    Returns:
        Truthiness of the condition for this event

    Raises:
        ValueError: If the condition uses an unsupported construct
    """
    tree = validate_custom_condition(condition)
    try:
        return bool(_eval_node(tree.body, event))
    except Exception:
        return False


@dataclass(kw_only=True)
class Breakpoint:
    """A breakpoint in agent execution.

    Attributes:
        breakpoint_id: Unique identifier for this breakpoint
        breakpoint_type: Type of breakpoint condition
        condition_value: Value for the breakpoint condition; for CUSTOM_CONDITION
            this is a predicate string restricted to the grammar documented in
            ``validate_custom_condition`` (comparisons/boolean logic over
            ``event`` attributes — no calls, no names other than ``event``)
        description: Human-readable description
        enabled: Whether breakpoint is active
        hit_count: Number of times breakpoint was hit
        created_at: When breakpoint was created
    """

    breakpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    breakpoint_type: BreakpointType = BreakpointType.EVENT_TYPE
    condition_value: Any = None
    description: str = ""
    enabled: bool = True
    hit_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def should_trigger(self, event: TraceEvent) -> bool:
        """Check if breakpoint should trigger for an event.

        Args:
            event: Event to check against breakpoint condition

        Returns:
            True if breakpoint should trigger

        Raises:
            ValueError: If a CUSTOM_CONDITION predicate uses a construct
                outside the supported grammar (see ``validate_custom_condition``)
        """
        if not self.enabled:
            return False

        if self.breakpoint_type == BreakpointType.EVENT_TYPE:
            return str(event.event_type) == str(self.condition_value)

        elif self.breakpoint_type == BreakpointType.TOOL_NAME:
            tool_name = getattr(event, "tool_name", None) or event.data.get("tool_name")
            return tool_name == self.condition_value

        elif self.breakpoint_type == BreakpointType.CONFIDENCE_THRESHOLD:
            confidence = getattr(event, "confidence", None) or event.data.get("confidence")
            if confidence is not None:
                return float(confidence) < float(self.condition_value)
            return False

        elif self.breakpoint_type == BreakpointType.SAFETY_OUTCOME:
            outcome = getattr(event, "safety_outcome", None) or event.data.get("safety_outcome")
            return str(outcome) == str(self.condition_value)

        elif self.breakpoint_type == BreakpointType.EVENT_ID:
            return event.id == self.condition_value

        elif self.breakpoint_type == BreakpointType.CUSTOM_CONDITION:
            # Evaluate via the restricted predicate interpreter; unsupported
            # constructs raise ValueError rather than silently never matching.
            return evaluate_custom_condition(str(self.condition_value), event)

        return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "breakpoint_id": self.breakpoint_id,
            "breakpoint_type": str(self.breakpoint_type),
            "condition_value": self.condition_value,
            "description": self.description,
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(kw_only=True)
class StepperState:
    """Current state of the debugger stepper.

    Attributes:
        current_event_index: Index of current event in execution
        current_event_id: ID of current event
        breakpoints: Active breakpoints
        step_history: History of step actions taken
        paused: Whether execution is paused
        completed: Whether execution has completed
    """

    current_event_index: int = 0
    current_event_id: str = ""
    breakpoints: list[Breakpoint] = field(default_factory=list)
    step_history: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = True
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "current_event_index": self.current_event_index,
            "current_event_id": self.current_event_id,
            "breakpoints": [bp.to_dict() for bp in self.breakpoints],
            "step_history": list(self.step_history),
            "paused": self.paused,
            "completed": self.completed,
        }


@dataclass(kw_only=True)
class StepResult:
    """Result of a step action.

    Attributes:
        success: Whether step was successful
        current_event: Current event after step
        next_event: Next event to execute
        breakpoint_hit: Which breakpoint was hit (if any)
        state: Updated stepper state
        message: Human-readable message
    """

    success: bool = True
    current_event: TraceEvent | None = None
    next_event: TraceEvent | None = None
    breakpoint_hit: Breakpoint | None = None
    state: StepperState | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "current_event": self.current_event.to_dict() if self.current_event else None,
            "next_event": self.next_event.to_dict() if self.next_event else None,
            "breakpoint_hit": self.breakpoint_hit.to_dict() if self.breakpoint_hit else None,
            "state": self.state.to_dict() if self.state else None,
            "message": self.message,
        }


@dataclass(kw_only=True)
class BranchPoint:
    """A branch point in execution for alternative path exploration.

    Attributes:
        branch_id: Unique identifier for this branch
        parent_event_id: Event where branch starts
        name: Human-readable name for the branch
        description: What this branch explores
        created_at: When branch was created
        replay_events: Events to replay in this branch
        branch_result: Result of branching execution
    """

    branch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_event_id: str = ""
    name: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replay_events: list[TraceEvent] = field(default_factory=list)
    branch_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "branch_id": self.branch_id,
            "parent_event_id": self.parent_event_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "replay_events_count": len(self.replay_events),
            "branch_result": self.branch_result,
        }


class AgentStepper:
    """Interactive stepper for agent execution debugging.

    Provides breakpoint management, step-through execution, state inspection,
    and branching capabilities for debugging agent sessions.

    Example usage::

        stepper = AgentStepper(session_events)

        # Set a breakpoint
        stepper.set_breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
            description="Break on all decisions"
        )

        # Step through execution
        result = stepper.step(StepAction.STEP_INTO)
        while result.success:
            # Inspect state
            state = stepper.get_state_at_current_position()

            # Continue stepping
            result = stepper.step(StepAction.STEP_INTO)

        # Create branch from current position
        branch = stepper.create_branch(
            name="Alternative path",
            parent_event_id=stepper.state.current_event_id,
            description="Explore different decision"
        )
    """

    def __init__(self, events: list[TraceEvent] | None = None) -> None:
        """Initialize the agent stepper.

        Args:
            events: List of events from a session to debug
        """
        self.events: list[TraceEvent] = events or []
        self.state = StepperState()
        self.branches: dict[str, BranchPoint] = {}
        self._build_event_index()

    def _build_event_index(self) -> None:
        """Build index mapping event IDs to their positions."""
        self.event_index: dict[str, int] = {}
        for i, event in enumerate(self.events):
            self.event_index[event.id] = i

    def set_breakpoint(
        self,
        breakpoint_type: BreakpointType,
        condition_value: Any = None,
        description: str = "",
    ) -> Breakpoint:
        """Set a breakpoint for execution.

        Args:
            breakpoint_type: Type of breakpoint condition
            condition_value: Value for the breakpoint condition; for
                CUSTOM_CONDITION this must be a predicate in the restricted
                grammar documented in ``validate_custom_condition``
            description: Human-readable description

        Returns:
            The created Breakpoint

        Raises:
            ValueError: If a CUSTOM_CONDITION predicate is outside the
                supported grammar (see ``validate_custom_condition``) —
                raised *before* any state is mutated, so a rejected
                breakpoint is never appended.
        """
        if breakpoint_type == BreakpointType.CUSTOM_CONDITION:
            # Pre-mutation validation: reject at creation instead of failing
            # on every later step/continue evaluation.
            validate_custom_condition(str(condition_value))
        breakpoint = Breakpoint(
            breakpoint_type=breakpoint_type,
            condition_value=condition_value,
            description=description or f"Break on {breakpoint_type}: {condition_value}",
        )

        self.state.breakpoints.append(breakpoint)
        return breakpoint

    def clear_breakpoint(self, breakpoint_id: str) -> bool:
        """Clear a breakpoint by ID.

        Args:
            breakpoint_id: ID of breakpoint to clear

        Returns:
            True if breakpoint was found and cleared
        """
        for i, bp in enumerate(self.state.breakpoints):
            if bp.breakpoint_id == breakpoint_id:
                self.state.breakpoints.pop(i)
                return True
        return False

    def clear_all_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self.state.breakpoints.clear()

    def step(self, action: StepAction, target_event_id: str | None = None) -> StepResult:
        """Execute a step action.

        Args:
            action: Step action to perform
            target_event_id: Target event ID for STEP_OVER or RUN_TO

        Returns:
            StepResult with current event and state
        """
        if self.state.completed:
            return StepResult(
                success=False,
                state=self.state,
                message="Execution already completed",
            )

        current_event = None
        next_event = None
        breakpoint_hit = None

        if action == StepAction.STEP_INTO:
            # Step to next event
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                next_event = self.events[self.state.current_event_index + 1] if self.state.current_event_index + 1 < len(self.events) else None
                self.state.current_event_index += 1
                if next_event:
                    self.state.current_event_id = next_event.id
            else:
                self.state.completed = True

        elif action == StepAction.STEP_OVER:
            # Skip over tool internals
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                # Find next non-tool-result event
                i = self.state.current_event_index + 1
                while i < len(self.events):
                    next_event = self.events[i]
                    if next_event.event_type != EventType.TOOL_RESULT:
                        self.state.current_event_index = i
                        self.state.current_event_id = next_event.id
                        break
                    i += 1
                else:
                    self.state.completed = True
            else:
                self.state.completed = True

        elif action == StepAction.STEP_OUT:
            # Return to parent context
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                parent_id = current_event.parent_id
                if parent_id:
                    # Find parent event index
                    parent_index = self.event_index.get(parent_id)
                    if parent_index is not None:
                        self.state.current_event_index = parent_index
                        self.state.current_event_id = parent_id
                        # Next event after parent
                        next_event = self.events[parent_index + 1] if parent_index + 1 < len(self.events) else None
                else:
                    # Already at root, step normally
                    next_event = self.events[self.state.current_event_index + 1] if self.state.current_event_index + 1 < len(self.events) else None
                    self.state.current_event_index += 1
                    if next_event:
                        self.state.current_event_id = next_event.id
            else:
                self.state.completed = True

        elif action == StepAction.CONTINUE:
            # Continue to next breakpoint
            found_breakpoint = False
            for i in range(self.state.current_event_index, len(self.events)):
                event = self.events[i]
                for bp in self.state.breakpoints:
                    if bp.should_trigger(event):
                        bp.hit_count += 1
                        self.state.current_event_index = i
                        self.state.current_event_id = event.id
                        current_event = event
                        next_event = self.events[i + 1] if i + 1 < len(self.events) else None
                        breakpoint_hit = bp
                        found_breakpoint = True
                        break
                if found_breakpoint:
                    break
            else:
                # No breakpoint found, complete execution
                self.state.completed = True

        elif action == StepAction.RUN_TO:
            # Run to specific event
            if target_event_id:
                target_index = self.event_index.get(target_event_id)
                if target_index is not None:
                    current_event = self.events[self.state.current_event_index]
                    next_event = self.events[target_index]
                    self.state.current_event_index = target_index
                    self.state.current_event_id = target_event_id
                else:
                    return StepResult(
                        success=False,
                        state=self.state,
                        message=f"Event {target_event_id} not found",
                    )

        # Record step in history
        self.state.step_history.append({
            "action": str(action),
            "event_index": self.state.current_event_index,
            "event_id": self.state.current_event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return StepResult(
            success=True,
            current_event=current_event,
            next_event=next_event,
            breakpoint_hit=breakpoint_hit,
            state=self.state,
            message=f"Stepped to event {self.state.current_event_id}",
        )

    def get_state_at_current_position(self) -> dict[str, Any]:
        """Get agent state at current stepper position.

        Returns:
            Dictionary with agent context, events, and state
        """
        if self.state.current_event_index >= len(self.events):
            return {
                "completed": True,
                "current_position": self.state.current_event_index,
                "total_events": len(self.events),
            }

        current_event = self.events[self.state.current_event_index]

        # Get events up to current position
        events_up_to_current = self.events[: self.state.current_event_index + 1]

        # Extract agent state from current event
        agent_state = {
            "event_id": current_event.id,
            "event_type": str(current_event.event_type),
            "timestamp": current_event.timestamp.isoformat() if current_event.timestamp else None,
            "name": current_event.name,
            "data": dict(current_event.data) if current_event.data else {},
            "parent_id": current_event.parent_id,
        }

        # Add confidence if available
        if hasattr(current_event, "confidence"):
            agent_state["confidence"] = current_event.confidence

        # Add reasoning if available
        if hasattr(current_event, "reasoning"):
            agent_state["reasoning"] = current_event.reasoning

        # Add tool name if available
        if hasattr(current_event, "tool_name"):
            agent_state["tool_name"] = current_event.tool_name

        return {
            "completed": False,
            "current_position": self.state.current_event_index,
            "total_events": len(self.events),
            "current_event": agent_state,
            "events_count": len(events_up_to_current),
            "breakpoints_active": len([bp for bp in self.state.breakpoints if bp.enabled]),
            "paused": self.state.paused,
        }

    def create_branch(
        self,
        name: str,
        parent_event_id: str,
        description: str = "",
    ) -> BranchPoint:
        """Create a branch point for alternative path exploration.

        Args:
            name: Human-readable name for the branch
            parent_event_id: Event where this branch starts
            description: What this branch explores

        Returns:
            The created BranchPoint
        """
        # Find event index
        parent_index = self.event_index.get(parent_event_id, 0)

        # Get events from branch point onwards
        replay_events = self.events[parent_index:]

        branch = BranchPoint(
            name=name,
            parent_event_id=parent_event_id,
            description=description,
            replay_events=replay_events,
        )

        self.branches[branch.branch_id] = branch
        return branch

    def get_branch(self, branch_id: str) -> BranchPoint | None:
        """Get a branch by ID.

        Args:
            branch_id: ID of branch to retrieve

        Returns:
            BranchPoint if found, None otherwise
        """
        return self.branches.get(branch_id)

    def list_branches(self) -> list[BranchPoint]:
        """List all branches.

        Returns:
            List of all branches
        """
        return list(self.branches.values())

    def delete_branch(self, branch_id: str) -> bool:
        """Delete a branch by ID.

        Args:
            branch_id: ID of branch to delete

        Returns:
            True if branch was found and deleted
        """
        if branch_id in self.branches:
            del self.branches[branch_id]
            return True
        return False

    def reset(self) -> None:
        """Reset stepper to initial state."""
        self.state = StepperState()
        self.branches.clear()

    def get_execution_context(self) -> dict[str, Any]:
        """Get full execution context with state and branches.

        Returns:
            Complete execution context
        """
        return {
            "state": self.state.to_dict(),
            "events_count": len(self.events),
            "branches": [branch.to_dict() for branch in self.branches.values()],
            "breakpoints": [bp.to_dict() for bp in self.state.breakpoints],
        }

    def export_state(self) -> dict[str, Any]:
        """Export stepper state for persistence.

        Returns:
            JSON-serializable state representation
        """
        return {
            "state": self.state.to_dict(),
            "branches": [branch.to_dict() for branch in self.branches.values()],
            "events_count": len(self.events),
        }

    def import_state(self, state_data: dict[str, Any]) -> None:
        """Import stepper state from exported data.

        Args:
            state_data: Exported state data

        Raises:
            ValueError: If any CUSTOM_CONDITION breakpoint in the imported
                state uses a predicate outside the supported grammar (see
                ``validate_custom_condition``) — raised *before* any state is
                mutated, so a rejected import leaves the stepper untouched.
        """
        # Pre-mutation validation: serialized breakpoints arrive as dicts
        # (see ``Breakpoint.to_dict``), already-created ones as Breakpoint.
        candidate_state = StepperState(**state_data.get("state", {}))
        for bp in candidate_state.breakpoints:
            if isinstance(bp, dict):
                is_custom = str(bp.get("breakpoint_type")) == str(BreakpointType.CUSTOM_CONDITION)
                condition = bp.get("condition_value")
            else:
                is_custom = str(bp.breakpoint_type) == str(BreakpointType.CUSTOM_CONDITION)
                condition = bp.condition_value
            if is_custom:
                validate_custom_condition(str(condition))

        self.state = candidate_state
        self.branches.clear()
        for branch_data in state_data.get("branches", []):
            branch = BranchPoint(
                branch_id=branch_data["branch_id"],
                parent_event_id=branch_data["parent_event_id"],
                name=branch_data["name"],
                description=branch_data["description"],
                created_at=datetime.fromisoformat(branch_data["created_at"]),
                branch_result=branch_data.get("branch_result"),
            )
            self.branches[branch.branch_id] = branch
