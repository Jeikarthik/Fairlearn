"""Optional OpenTelemetry instrumentation.

Enabled automatically when the OTEL_EXPORTER_OTLP_ENDPOINT environment
variable is set.  When the variable is absent (or the opentelemetry
packages are not installed) this module is a no-op — the rest of the
application is completely unaffected.

Supported exporters (configured via standard OTEL env vars):
  - OTLP/gRPC  → Jaeger, Grafana Tempo, Honeycomb, Lightstep, …
  - Console     → set OTEL_TRACES_EXPORTER=console for local debugging

Environment variables:
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://jaeger:4317
  OTEL_SERVICE_NAME              defaults to "fairlens"
  OTEL_TRACES_EXPORTER           "otlp" (default) or "console"

Usage — all automatic once setup_telemetry() is called in create_app():
  - Every FastAPI request becomes a root span
  - SQLAlchemy queries are child spans (with sqlalchemy instrumentation)
  - Manual spans: `with tracer.start_as_current_span("my-operation") as span:`
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("fairlens.telemetry")


def setup_telemetry() -> None:
    """Configure OpenTelemetry if the endpoint is set. Silent no-op otherwise."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.getenv("OTEL_SERVICE_NAME", "fairlens")
        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        exporter_name = os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower()

        if exporter_name == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            exporter = ConsoleSpanExporter()
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Instrument FastAPI + SQLAlchemy automatically
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor().instrument()
        except ImportError:
            pass

        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
        except ImportError:
            pass

        logger.info(
            "OpenTelemetry enabled — service=%s endpoint=%s exporter=%s",
            service_name, endpoint, exporter_name,
        )

    except ImportError:
        logger.debug(
            "opentelemetry packages not installed — tracing disabled. "
            "Install opentelemetry-sdk and opentelemetry-exporter-otlp to enable."
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenTelemetry setup failed (non-fatal): %s", exc)


def get_tracer(name: str = "fairlens"):
    """Return a tracer for manual instrumentation. Returns a no-op tracer if OTel is not set up."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Minimal no-op tracer so callers don't need to guard against missing OTel."""

    class _NoOpSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def set_attribute(self, *_):
            pass

        def record_exception(self, *_):
            pass

    def start_as_current_span(self, name: str, **_):
        return self._NoOpSpan()
