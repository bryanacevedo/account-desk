-- A job keeps the W3C traceparent of the request that queued it, so its run (and the calls it makes) join that trace.
-- NULL when tracing is off. Safe to run twice. To take it back: alter table jobs drop column trace_parent.
alter table jobs add column if not exists trace_parent text;
