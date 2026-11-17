"""Optional tracing with OpenTelemetry, for the workday simulation. Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set.

It sends only to this machine (a local OpenObserve): any other endpoint is refused, so a hosted collector can never be
used by mistake. The span of a request carries the W3C `traceparent` header across HTTP, so a call from one desk to another
shows as one trace. Install the packages with `uv sync --extra otel`; without them the call does nothing and says so once.
Setup and a start script: workday-sim-plan/observability/README."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

LOCAL = {"127.0.0.1", "localhost", "::1"}
_on = False


def setup(service: str, app=None) -> bool:
    """Start tracing for this process as `service`; instrument `app` (FastAPI) when given. Safe to call twice."""
    global _on
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    if urlsplit(endpoint).hostname not in LOCAL:
        raise SystemExit("Telemetry goes to this machine only: OTEL_EXPORTER_OTLP_ENDPOINT must be localhost.")
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        print("Telemetry is set but the OpenTelemetry packages are not installed (uv sync --extra otel).", file=sys.stderr)
        return False
    if not _on:
        provider = TracerProvider(resource=Resource.create({"service.name": service}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # endpoint and headers from the OTEL_* environment
        trace.set_tracer_provider(provider)
        PsycopgInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        _on = True
    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")
    return True
