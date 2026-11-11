-- A play's monthly spend cap, set by the manager who launches it (SPEC 22.16), and every charge tagged with the play
-- it was for, so the cap can be held.
alter table plays add column monthly_cap jsonb;  -- {"people_search": credits, ..., "anthropic_cents": cents}
alter table ledger add column play_id bigint references plays on delete set null;
create index on ledger (play_id, at);
