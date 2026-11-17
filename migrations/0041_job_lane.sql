-- Work a person asks for (Accept on a proposal) runs in the background and shows its progress.
-- `lane` says whose work a job is: 'request' for what a person asked for, 'system' for everything else (the default).
-- `request_ref` names what the person asked for ('account_play:12'); work a request's jobs queue inherits both.
-- With the simulated clock on, the API process's worker drains only the 'request' lane, so it never takes the
-- simulation's own jobs from the simulation.
-- Safe to run twice (if not exists). To take it back: drop index jobs_ready_request, jobs_request_ref; alter table jobs
-- drop column requested_by, drop column request_ref, drop column lane (every job is then the 'system' lane it was).
alter table jobs
  add column if not exists lane text not null default 'system' check (lane in ('system', 'request')),
  add column if not exists request_ref text,
  add column if not exists requested_by bigint references users (id);
create index if not exists jobs_request_ref on jobs (request_ref) where request_ref is not null;
create index if not exists jobs_ready_request on jobs (run_at) where status = 'queued' and lane = 'request';
