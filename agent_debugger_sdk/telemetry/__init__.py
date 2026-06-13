"""
OpenTelemetry integration for Peaky Peek.

Provides optional OTel span export for agent traces, allowing
Peaky Peek sessions to be ingested by Jaeger, Grafana Tempo,
Honeycomb, or any OTel-compatible backend.

Usage::

    from agent_debugger_sdk.telemetry import init_telemetry

    init_telemetry(
        service_name="my-agent",
        endpoint="http://localhost:4318",  # OTLP gRPC exporter
    )

This is entirely optional — if opentelemetry-api is not installed,
all functions are no-ops.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_initialized = False


def init_telemetry(
    service_name: str = "peaky-peek-agent",
    endpoint: str | None = None,
    exporter: str = "console",
) -> None:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Name of the traced service.
        endpoint: OTLP exporter endpoint URL. If None, uses console export.
        exporter: Exporter type — "console" or "otlp".

    If opentelemetry-api/opentelemetry-sdk are not installed, this is a no-op.
    """
    global _initialized

    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-untyped]
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        logger.info("opentelemetry-sdk not installed — telemetry is disabled")
        return

    provider = TracerProvider()
    trace.set_tracer_provider(provider)

    if exporter == "otlp" and endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-untyped]
                OTLPSpanExporter as GRPCExporter,
            )
            provider.add_span_processor(
                BatchSpanProcessor(GRPCExporter(endpoint=endpoint))
            )
        except ImportError:
            logger.warning("opentelemetry-exporter-otlp not installed — falling back to console export")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    _initialized = True
    logger.info("Telemetry initialized: service=%s, exporter=%s", service_name, exporter)


def get_tracer(name: str = "peaky-peek", version: str = "1.0.0"):
    """Get an OpenTelemetry tracer.

    Returns a no-op tracer if opentelemetry is not installed.
    """
    try:
        from opentelemetry import trace  # type: ignore[import-untyped]

        return trace.get_tracer(name, version)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Minimal no-op tracer for when OTel is not installed."""

    def start_as_current_span(self, name: str, **kwargs):  # type: ignore[misc]
        return _NoOpContextManager()


class _NoOpContextManager:
    """No-op context manager for spans."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def is_telemetry_enabled() -> bool:
    """Check if telemetry was successfully initialized."""
    return _initialized
