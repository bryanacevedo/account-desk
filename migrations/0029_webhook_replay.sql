-- A signed webhook is accepted once. Its signature is kept for the five minutes its timestamp is valid (and a little
-- longer), so the same request sent again inside that window is refused. Real time, not the demo's clock: the
-- timestamp a sender signs is real.
create table webhook_signatures (
  digest text primary key,
  seen_at timestamptz not null default now()
);
create index on webhook_signatures (seen_at);
