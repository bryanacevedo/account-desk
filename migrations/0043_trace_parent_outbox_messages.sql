-- The W3C traceparent of the request that queued a CRM write (crm_outbox) or approved a message (messages), so the CRM
-- call it causes can be linked to the person's action (OpenTelemetry span links, decision 107). NULL when tracing is off,
-- and for work no request started. Safe to run twice. To take it back: alter table crm_outbox drop column trace_parent;
-- alter table messages drop column trace_parent.
set local lock_timeout = '5s';   -- a busy table fails the deploy fast instead of stalling the desk behind the ALTER
alter table crm_outbox add column if not exists trace_parent text;
alter table messages add column if not exists trace_parent text;
