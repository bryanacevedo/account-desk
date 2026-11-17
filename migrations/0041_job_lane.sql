-- Work a person asks for (Accept on a proposal) runs in the background and shows its progress.
-- `lane` says whose work a job is: 'request' for what a person asked for, 'system' for everything else (the default).
-- `request_ref` names what the person asked for ('account_play:12'); work a request's jobs queue inherits both.
-- With the simulated clock on, the API process's worker drains only the 'request' lane, so it never takes the
-- simulation's own jobs from the simulation.
alter table jobs
  add column lane text not null default 'system' check (lane in ('system', 'request')),
  add column request_ref text,
  add column requested_by bigint references users (id);
create index jobs_request_ref on jobs (request_ref) where request_ref is not null;
create index jobs_ready_request on jobs (run_at) where status = 'queued' and lane = 'request';
