-- BL-172: a weekly cap on the accounts the desk proposes to one SDR. A manager sets it; null means no cap, the default, so a
-- desk that sets none behaves exactly as before. An account the cap holds back waits in proposal_waits, highest priority
-- released first (src/outbound/budget.py). Every change of a cap is kept with who made it and why.
-- To take it back: drop table proposal_waits, proposal_cap_changes; alter table users drop column weekly_proposal_cap.
alter table users add column if not exists weekly_proposal_cap integer check (weekly_proposal_cap is null or weekly_proposal_cap between 1 and 500);

create table if not exists proposal_cap_changes (
  id bigint generated always as identity primary key,
  user_id bigint not null references users,
  old_cap integer,
  new_cap integer,
  reason text not null,
  changed_by bigint not null references users,
  at timestamptz not null default app_now()
);
create index if not exists proposal_cap_changes_user on proposal_cap_changes (user_id, at desc);

create table if not exists proposal_waits (
  account_id bigint primary key references accounts,
  owner_id bigint not null references users,
  play_id bigint not null references plays,
  trigger_signal_id bigint references signals,
  since timestamptz not null default app_now()
);
create index if not exists proposal_waits_owner on proposal_waits (owner_id, since);
