"""Tests for the OTel-optional telemetry module."""

import logging
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_opentelemetry(monkeypatch):
    """Install fake opentelemetry modules into sys.modules so the
    telemetry module's success-path branches (normally unreachable
    without the real, optional dependency) can be exercised.

    Each fake package module gets a `__path__` (even if empty) and is
    wired onto its parent as an attribute, so it behaves like a real
    package: submodules already registered here resolve via the
    sys.modules cache, and anything NOT registered here (e.g. a
    genuinely installed opentelemetry.exporter.* on the test machine)
    fails with a clean ImportError against the empty __path__ instead
    of falling through to whatever is actually on disk.
    """
    otel_mod = ModuleType("opentelemetry")
    otel_mod.__path__ = []

    trace_mod = ModuleType("opentelemetry.trace")
    trace_mod.set_tracer_provider = MagicMock()
    trace_mod.get_tracer = MagicMock(return_value="real-tracer")
    otel_mod.trace = trace_mod

    sdk_mod = ModuleType("opentelemetry.sdk")
    sdk_mod.__path__ = []
    otel_mod.sdk = sdk_mod

    sdk_trace_mod = ModuleType("opentelemetry.sdk.trace")
    sdk_trace_mod.__path__ = []
    sdk_trace_mod.TracerProvider = MagicMock(
        return_value=MagicMock(add_span_processor=MagicMock())
    )
    sdk_mod.trace = sdk_trace_mod

    export_mod = ModuleType("opentelemetry.sdk.trace.export")
    export_mod.BatchSpanProcessor = MagicMock()
    export_mod.ConsoleSpanExporter = MagicMock()
    sdk_trace_mod.export = export_mod

    modules = {
        "opentelemetry": otel_mod,
        "opentelemetry.trace": trace_mod,
        "opentelemetry.sdk": sdk_mod,
        "opentelemetry.sdk.trace": sdk_trace_mod,
        "opentelemetry.sdk.trace.export": export_mod,
    }
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    return {
        "otel": otel_mod,
        "trace": trace_mod,
        "provider_cls": sdk_trace_mod.TracerProvider,
        "batch_processor": export_mod.BatchSpanProcessor,
        "console_exporter": export_mod.ConsoleSpanExporter,
    }


@pytest.fixture
def no_opentelemetry(monkeypatch):
    """Force `from opentelemetry import ...` to fail with ImportError,
    regardless of whether opentelemetry is actually installed in the
    environment running the tests. A bare, path-less module with no
    attributes makes `from opentelemetry import trace` raise ImportError
    deterministically (no __path__ means Python won't try to resolve
    `trace` as a real submodule, it just does a failed getattr)."""
    dummy = ModuleType("opentelemetry")
    monkeypatch.setitem(sys.modules, "opentelemetry", dummy)
    for name in list(sys.modules):
        if name.startswith("opentelemetry."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    return dummy


def test_telemetry_module_importable():
    """Telemetry module should be importable and expose its public API."""
    from agent_debugger_sdk import telemetry

    assert hasattr(telemetry, "init_telemetry")
    assert hasattr(telemetry, "get_tracer")
    assert hasattr(telemetry, "is_telemetry_enabled")


def test_is_telemetry_enabled_false_before_init():
    """is_telemetry_enabled should reflect the module-level _initialized flag."""
    import agent_debugger_sdk.telemetry as telemetry

    telemetry._initialized = False
    assert telemetry.is_telemetry_enabled() is False


def test_init_telemetry_noop_when_opentelemetry_not_installed(caplog, no_opentelemetry):
    """init_telemetry should no-op and log when opentelemetry-sdk is unavailable."""
    import agent_debugger_sdk.telemetry as telemetry

    telemetry._initialized = False

    with caplog.at_level(logging.INFO, logger="agent_debugger_sdk.telemetry"):
        result = telemetry.init_telemetry(service_name="test-agent")

    assert result is None
    assert telemetry.is_telemetry_enabled() is False
    assert "opentelemetry-sdk not installed" in caplog.text


def test_init_telemetry_accepts_otlp_args_without_crashing(no_opentelemetry):
    """init_telemetry should not raise when called with an otlp exporter/endpoint,
    even though opentelemetry is not installed (falls back to the no-op path)."""
    import agent_debugger_sdk.telemetry as telemetry

    telemetry._initialized = False

    telemetry.init_telemetry(
        service_name="test-agent",
        endpoint="http://localhost:4318",
        exporter="otlp",
    )

    assert telemetry.is_telemetry_enabled() is False


def test_get_tracer_returns_noop_tracer_when_opentelemetry_not_installed(no_opentelemetry):
    """get_tracer should fall back to _NoOpTracer when opentelemetry is unavailable."""
    from agent_debugger_sdk.telemetry import _NoOpTracer, get_tracer

    tracer = get_tracer("my-service")
    assert isinstance(tracer, _NoOpTracer)


def test_noop_tracer_start_as_current_span_is_usable_as_context_manager():
    """The no-op tracer's span context manager should work like a real one."""
    from agent_debugger_sdk.telemetry import _NoOpTracer

    tracer = _NoOpTracer()
    with tracer.start_as_current_span("my-span") as span:
        assert span is not None


def test_noop_context_manager_enter_returns_self():
    """_NoOpContextManager.__enter__ should return itself."""
    from agent_debugger_sdk.telemetry import _NoOpContextManager

    cm = _NoOpContextManager()
    assert cm.__enter__() is cm


def test_noop_context_manager_exit_suppresses_nothing_and_returns_none():
    """_NoOpContextManager.__exit__ should accept any args and return None."""
    from agent_debugger_sdk.telemetry import _NoOpContextManager

    cm = _NoOpContextManager()
    assert cm.__exit__(None, None, None) is None
    assert cm.__exit__(ValueError, ValueError("boom"), None) is None


def test_init_telemetry_console_export_when_opentelemetry_installed(fake_opentelemetry):
    """init_telemetry should set up a console exporter and mark itself
    initialized when opentelemetry is importable and no otlp args given."""
    import agent_debugger_sdk.telemetry as telemetry

    telemetry._initialized = False
    telemetry.init_telemetry(service_name="test-agent")

    assert telemetry.is_telemetry_enabled() is True
    fake_opentelemetry["trace"].set_tracer_provider.assert_called_once()
    fake_opentelemetry["console_exporter"].assert_called_once()
    fake_opentelemetry["batch_processor"].assert_called_once()


def test_init_telemetry_otlp_export_with_endpoint(fake_opentelemetry, monkeypatch):
    """init_telemetry with exporter='otlp' and an endpoint should use the
    OTLP gRPC exporter when it is importable."""
    import agent_debugger_sdk.telemetry as telemetry

    otlp_exporter_mod = ModuleType(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
    )
    otlp_exporter_mod.OTLPSpanExporter = MagicMock()
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        otlp_exporter_mod,
    )

    telemetry._initialized = False
    telemetry.init_telemetry(
        service_name="test-agent",
        endpoint="http://localhost:4318",
        exporter="otlp",
    )

    assert telemetry.is_telemetry_enabled() is True
    otlp_exporter_mod.OTLPSpanExporter.assert_called_once_with(
        endpoint="http://localhost:4318"
    )


def test_init_telemetry_otlp_export_falls_back_to_console_when_exporter_missing(
    fake_opentelemetry, monkeypatch
):
    """If the otlp exporter package isn't installed, init_telemetry should
    fall back to the console exporter instead of raising."""
    import agent_debugger_sdk.telemetry as telemetry

    monkeypatch.delitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        raising=False,
    )

    telemetry._initialized = False
    telemetry.init_telemetry(
        service_name="test-agent",
        endpoint="http://localhost:4318",
        exporter="otlp",
    )

    assert telemetry.is_telemetry_enabled() is True
    assert fake_opentelemetry["console_exporter"].call_count >= 1


def test_get_tracer_returns_real_tracer_when_opentelemetry_installed(fake_opentelemetry):
    """get_tracer should delegate to opentelemetry.trace.get_tracer when available."""
    from agent_debugger_sdk.telemetry import get_tracer

    tracer = get_tracer("my-service", version="2.0.0")

    assert tracer == "real-tracer"
    fake_opentelemetry["trace"].get_tracer.assert_called_once_with("my-service", "2.0.0")
