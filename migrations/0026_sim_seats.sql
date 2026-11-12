-- The simulated world keeps who sits in which seat and since when, so an announcement, a people-data read and the
-- people on record agree: a new finance leader exists, holds the announced title and started on the announced day,
-- and the one they replaced has left. Only the simulator reads these; the desk never does.
alter table sim_people add column role_started date, add column left_at timestamptz;
alter table sim_hidden_people add column role_started date, add column left_at timestamptz;
alter table sim_accounts add column billing text, add column billing_dropped boolean not null default false;
create table sim_seat_changes (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  at timestamptz not null,
  hidden_person_id bigint not null references sim_hidden_people on delete cascade,
  announced boolean not null  -- some appointments never make the news; people data finds those later
);
create index on sim_seat_changes (at);
