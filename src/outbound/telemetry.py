"""Optional tracing with OpenTelemetry, for the workday simulation. Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set.

It sends only to this machine (a local OpenObserve): any other endpoint is refused, so a hosted collector can never be
used by mistake. The span of a request carries the W3C `traceparent` header across HTTP, so a call from one desk to another
shows as one trace. Install the packages with `uv sync --extra otel`; without them the call does nothing and says so once.
Setup and a start script: workday-sim-plan/observability/README."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from urllib.parse import urlsplit

LOCAL = {"127.0.0.1", "localhost", "::1"}
_on = False


def setup(service: str, app=None) -> bool:
    """Start tracing for this process as `service`; instrument `app` (FastAPI) when given. Safe to call twice."""
    global _on
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    for var in ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"):  # the exporter prefers the traces one
        if os.environ.get(var) and urlsplit(os.environ[var]).hostname not in LOCAL:
            raise SystemExit("Telemetry goes to this machine only: the OTLP endpoint must be localhost.")
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


def current_traceparent() -> str | None:
    """The W3C `traceparent` of the span recording now, or None (tracing off, no recording span, or anything goes wrong).
    A job stores it when it is queued, so the job can run later under the trace of the request that queued it."""
    if not _on:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        if not trace.get_current_span().is_recording():
            return None
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier.get("traceparent")
    except Exception:
        return None


@contextmanager
def job_span(kind: str, trace_parent: str | None):
    """Run a job's handler inside a span "job <kind>" (CONSUMER) whose parent is the stored `traceparent`, so the job
    and the request that queued it are one trace. A no-op when tracing is off (and when the packages are missing)."""
    if not _on:
        yield
        return
    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        parent = TraceContextTextMapPropagator().extract({"traceparent": trace_parent}) if trace_parent else None
        cm = trace.get_tracer("jobs").start_as_current_span(f"job {kind}", context=parent, kind=trace.SpanKind.CONSUMER)
    except Exception:
        yield
        return
    with cm:
        yield


@contextmanager
def linked_span(name: str, trace_parent: str | None):
    """Run a block inside a span `name` that carries an OpenTelemetry span LINK to the stored `traceparent`, not a parent:
    a CRM push or a send's CRM check is one piece of work caused by a person's earlier request, and one such call can
    stand for several requests, so the two traces are joined by a link. With no stored traceparent (the request was not
    traced, or tracing is off) it is an ordinary span, and with tracing off it does nothing."""
    if not _on:
        yield
        return
    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        links = []
        if trace_parent:
            ctx = trace.get_current_span(TraceContextTextMapPropagator().extract({"traceparent": trace_parent})).get_span_context()
            if ctx.is_valid:
                links.append(trace.Link(ctx))
        cm = trace.get_tracer("crm").start_as_current_span(name, links=links, kind=trace.SpanKind.CLIENT)
    except Exception:
        yield
        return
    with cm:
        yield
