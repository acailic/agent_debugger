"""Frame capture integration for auto-patch system.

This module extends the auto-patch system to optionally capture frame-level
traces when enabled via configuration. It integrates with the existing
TraceContext and transport mechanisms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.auto_patch._transport import SyncTransport

from agent_debugger_sdk.core.frame_tracer import (
    FrameCaptureContext,
    FrameLifetimeTrace,
    get_frame_context,
    set_frame_context,
)

logger = logging.getLogger("agent_debugger.auto_patch.frame_capture")


@dataclass(kw_only=True)
class FrameCaptureConfig:
    """Configuration for frame-level capture.

    Attributes:
        enabled: Whether to enable frame-level capture
        capture_args: Whether to capture function arguments
        capture_return: Whether to capture return values
        capture_exception: Whether to capture exception information
        max_frames: Maximum number of frames to capture (0 = unlimited)
        include_standard_lib: Whether to include standard library calls
        module_filters: List of module patterns to include (None = all)
    """

    enabled: bool = False
    capture_args: bool = True
    capture_return: bool = True
    capture_exception: bool = True
    max_frames: int = 0  # 0 = unlimited
    include_standard_lib: bool = False
    module_filters: list[str] | None = None


class FrameCaptureSession:
    """Manages a single frame capture session.

    This class integrates frame capture with the auto-patch system's
    session management and transport mechanisms.
    """

    def __init__(
        self,
        trace_id: str,
        config: FrameCaptureConfig,
        transport: SyncTransport | None = None,
    ) -> None:
        """Initialize a frame capture session.

        Args:
            trace_id: Unique identifier for this trace
            config: Frame capture configuration
            transport: Optional transport for event delivery
        """
        self.trace_id = trace_id
        self.config = config
        self.transport = transport
        self.context = FrameCaptureContext(trace_id=trace_id)
        self.frames_captured = 0

    def start(self) -> None:
        """Start the frame capture session."""
        set_frame_context(self.context)
        logger.debug(f"Started frame capture session: {self.trace_id}")

    def stop(self) -> FrameLifetimeTrace:
        """Stop the frame capture and return the complete trace.

        Returns:
            Complete FrameLifetimeTrace with all captured frames
        """
        trace = self.context.build_trace()
        set_frame_context(None)
        logger.debug(
            f"Stopped frame capture session: {self.trace_id}, "
            f"captured {len(trace.frames)} frames"
        )
        return trace

    def should_capture_module(self, module_path: str) -> bool:
        """Determine if a module should be captured based on filters.

        Args:
            module_path: The module path to check

        Returns:
            True if the module should be captured
        """
        # Skip standard library unless configured to include
        if not self.config.include_standard_lib:
            if self._is_standard_lib(module_path):
                return False

        # Apply module filters if configured
        if self.config.module_filters:
            return any(pattern in module_path for pattern in self.config.module_filters)

        return True

    def _is_standard_lib(self, module_path: str) -> bool:
        """Check if a module is from the standard library.

        Args:
            module_path: The module path to check

        Returns:
            True if the module appears to be from standard library
        """
        # Common standard library prefixes
        stdlib_prefixes = (
            "builtins.",
            "_",
            "abc.",
            "argparse.",
            "ast.",
            "asyncio.",
            "collections.",
            "contextlib.",
            "dataclasses.",
            "datetime.",
            "enum.",
            "functools.",
            "importlib.",
            "inspect.",
            "io.",
            "json.",
            "logging.",
            "pathlib.",
            "re.",
            "threading.",
            "time.",
            "traceback.",
            "types.",
            "typing.",
            "uuid.",
        )

        return any(module_path.startswith(prefix) for prefix in stdlib_prefixes)

    def maybe_transport_frame_trace(self, trace: FrameLifetimeTrace) -> None:
        """Transport the frame trace if configured.

        Args:
            trace: The frame trace to transport
        """
        if self.transport:
            try:
                # Create an event-like structure for transport
                event_data = {
                    "event_type": "frame_lifetime_trace",
                    "trace_id": trace.trace_id,
                    "timestamp": self.context.frames[0].start_time if self.context.frames else 0,
                    "data": trace.to_dict(),
                }
                self.transport.send_event(event_data)
                logger.debug(f"Transported frame trace: {trace.trace_id}")
            except Exception as e:
                logger.warning(f"Failed to transport frame trace: {e}")


_active_session: FrameCaptureSession | None = None


def get_active_session() -> FrameCaptureSession | None:
    """Get the currently active frame capture session."""
    return _active_session


def enable_frame_capture(
    transport: SyncTransport | None = None,
    config: FrameCaptureConfig | None = None,
) -> str:
    """Enable frame-level instrumentation.

    This function activates frame capture for the current session.
    When enabled, functions decorated with @capture_function_call
    will have their execution captured as frame events.

    Args:
        transport: Optional transport for event delivery
        config: Optional frame capture configuration

    Returns:
        Trace ID for the capture session

    Example:
        transport = SyncTransport(server_url="http://localhost:8000")
        trace_id = enable_frame_capture(
            transport=transport,
            config=FrameCaptureConfig(
                enabled=True,
                capture_args=True,
                max_frames=1000,
            )
        )
        # ... run agent code ...
        trace = disable_frame_capture()
    """
    global _active_session

    if config is None:
        config = FrameCaptureConfig()

    if not config.enabled:
        logger.warning("enable_frame_capture called with disabled config")
        return ""

    if _active_session is not None:
        logger.warning("Frame capture already active, using existing session")
        return _active_session.trace_id

    import uuid
    trace_id = str(uuid.uuid4())
    _active_session = FrameCaptureSession(
        trace_id=trace_id,
        config=config,
        transport=transport,
    )
    _active_session.start()

    logger.info(f"Frame capture enabled with trace_id: {trace_id}")
    return trace_id


def disable_frame_capture() -> FrameLifetimeTrace | None:
    """Disable frame-level instrumentation and return the trace.

    Returns:
        Complete FrameLifetimeTrace if capture was active, None otherwise
    """
    global _active_session

    if _active_session is None:
        logger.warning("No active frame capture session to disable")
        return None

    trace = _active_session.stop()
    _active_session.maybe_transport_frame_trace(trace)

    _active_session = None
    logger.info("Frame capture disabled")

    return trace


def is_frame_capture_enabled() -> bool:
    """Check if frame capture is currently enabled.

    Returns:
        True if frame capture is active
    """
    return get_active_session() is not None


def get_current_trace_id() -> str | None:
    """Get the current frame capture trace ID.

    Returns:
        Trace ID if capture is active, None otherwise
    """
    session = get_active_session()
    return session.trace_id if session else None


# Decorator factory that respects session configuration
def auto_capture_function(
    func: Any | None = None,
    *,
    module_filter: str | None = None,
) -> Any:
    """Decorator that automatically captures function calls when frame capture is enabled.

    This decorator only captures when frame capture is enabled and the module
    matches the current session's filters. It's designed to be applied broadly
    to functions that might be captured, with filtering happening at runtime.

    Args:
        func: The function to decorate
        module_filter: Optional module pattern filter

    Returns:
        Decorated function that respects frame capture configuration

    Example:
        @auto_capture_function(module_filter="my_agent")
        def my_function(arg1, arg2):
            return arg1 + arg2
    """
    import functools

    def decorator(f: Any) -> Any:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            session = get_active_session()
            if not session:
                # No frame capture active, just call the function
                return f(*args, **kwargs)

            # Check if we should capture this module
            module_path = f.__qualname__
            if hasattr(f, "__module__"):
                module_path = f"{f.__module__}.{f.__qualname__}"

            # Apply decorator-level module filter as an additional restriction.
            # Matches the substring semantics of session.should_capture_module
            # so a decorated function is only captured when its own filter agrees.
            if module_filter is not None and module_filter not in module_path:
                return f(*args, **kwargs)

            if not session.should_capture_module(module_path):
                return f(*args, **kwargs)

            # Check max frames limit
            if session.config.max_frames > 0 and session.frames_captured >= session.config.max_frames:
                logger.debug(f"Max frames limit reached: {session.config.max_frames}")
                return f(*args, **kwargs)

            # Use the base capture_function_call with current config
            import inspect
            import time
            import uuid

            from agent_debugger_sdk.core.frame_tracer import ExceptionInfo, FrameEvent, _serialize_value

            frame_id = str(uuid.uuid4())
            context = get_frame_context()
            if not context:
                return f(*args, **kwargs)

            context.enter_frame(frame_id)

            function_name = f.__name__
            start_time = time.time()
            exception_info = None
            return_value = None

            try:
                return_value = f(*args, **kwargs)
                return return_value
            except Exception as e:
                if session.config.capture_exception:
                    import traceback
                    exception_info = ExceptionInfo(
                        exception_type=type(e).__name__,
                        message=str(e),
                        traceback=traceback.format_exc(),
                    )
                raise
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                # Serialize arguments if requested
                call_args = {}
                if session.config.capture_args:
                    try:
                        sig = inspect.signature(f)
                        bound_args = sig.bind(*args, **kwargs)
                        bound_args.apply_defaults()
                        for name, value in bound_args.arguments.items():
                            call_args[name] = _serialize_value(value)
                    except Exception:
                        call_args = {"args": str(args), "kwargs": str(kwargs)}

                # Serialize return value if requested
                serialized_return = None
                if session.config.capture_return and return_value is not None:
                    serialized_return = _serialize_value(return_value)

                frame = FrameEvent(
                    frame_id=frame_id,
                    function_name=function_name,
                    module_path=module_path,
                    call_args=call_args,
                    return_value=serialized_return,
                    exception=exception_info,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    depth=context._current_depth,
                )

                context.add_frame(frame)
                session.frames_captured += 1
                context.exit_frame(frame_id)

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)
