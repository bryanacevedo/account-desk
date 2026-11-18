"""A job keeps the trace of the request that queued it (bl_148). With tracing off (every other test) the column stays
NULL and the worker runs as before. With an in-memory exporter, the job runs under a "job <kind>" span in the trace of
the span that queued it, and an HTTPX call made by the handler carries that trace id in its traceparent header."""
from __future__ import annotations

import httpx
import pytest

from outbound import db, jobs, telemetry

KIND = "wk2fix_probe"
LONG_AGO = "2000-01-01"  # first in the worker's order, whatever else the shared test database holds


def _enqueue_committed(**kw) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as c:
            return jobs.enqueue(c, KIND, {}, run_at=LONG_AGO, **kw)


def _forget(job_id: int) -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as c:
            db.run(c, "delete from jobs where id = %s", job_id)


def _stored(job_id: int):
    with db.pool().connection() as conn:
        with conn.cursor() as c:
            return db.one(c, "select status, trace_parent from jobs where id = %s", job_id)


def _calls_crm(headers: list):
    def handler(cur, payload):
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        transport = httpx.MockTransport(lambda r: (headers.append(r.headers.get("traceparent")), httpx.Response(200))[1])
        with httpx.Client(transport=transport) as client:
            # the real clients are instrumented by telemetry.setup; a MockTransport is wrapped the same way here
            HTTPXClientInstrumentor.instrument_client(client)
            client.get("http://crm.invalid/ping")
    return handler


@pytest.fixture
def tracing(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    pytest.importorskip("opentelemetry.instrumentation.httpx")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)  # put back by monkeypatch; nothing else is left global
    monkeypatch.setattr(telemetry, "_on", True)
    yield provider, exporter


def test_tracing_off_stores_null_and_the_job_runs_as_before(database, monkeypatch):
    ran = []
    monkeypatch.setitem(jobs.HANDLERS, KIND, lambda c, p: ran.append(p))
    assert telemetry.current_traceparent() is None
    with telemetry.job_span(KIND, "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"):
        pass  # a no-op while tracing is off
    job_id = _enqueue_committed()
    try:
        assert _stored(job_id)["trace_parent"] is None
        assert jobs.run_ready(limit=1) == 1
        assert ran == [{}] and _stored(job_id)["status"] == "done"
    finally:
        _forget(job_id)


def test_a_job_runs_in_the_trace_of_the_request_that_queued_it(database, tracing, monkeypatch):
    from opentelemetry import trace
    provider, exporter = tracing
    headers: list = []
    monkeypatch.setitem(jobs.HANDLERS, KIND, _calls_crm(headers))
    with provider.get_tracer("test").start_as_current_span("POST /api/thing") as request:
        trace_id = f"{request.get_span_context().trace_id:032x}"
        job_id = _enqueue_committed(dedupe_key=KIND)
        stored = _stored(job_id)["trace_parent"]
        assert telemetry.current_traceparent() == stored and stored.split("-")[1] == trace_id
        with telemetry.job_span("noop", None):  # no parent given: a root span of its own, nothing breaks
            pass
        assert _enqueue_committed(dedupe_key=KIND) is None  # a no-op keeps the first value
    try:
        assert trace.get_current_span().get_span_context().trace_id == 0  # the worker runs outside any request
        assert jobs.run_ready(limit=1) == 1
        assert _stored(job_id)["trace_parent"] == stored  # kept as it is
    finally:
        _forget(job_id)
    spans = {s.name: s for s in exporter.get_finished_spans()}
    job = spans[f"job {KIND}"]
    assert f"{job.context.trace_id:032x}" == trace_id
    assert job.parent.span_id == spans["POST /api/thing"].context.span_id
    assert job.kind == trace.SpanKind.CONSUMER
    assert len(headers) == 1 and headers[0].split("-")[1] == trace_id
