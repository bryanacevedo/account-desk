-- Inbox placement. Postmaster says how a domain is doing; it never says where one mailbox's mail lands.
-- A seed test sends to a list of test inboxes at each provider and reports inbox, spam or missing.

-- 0001 reserved a placement_tests table that nothing ever wrote to; this replaces it with counts per provider.
drop table placement_tests;
create table placement_tests (
  id bigint generated always as identity primary key,
  mailbox_id bigint not null references mailboxes on delete cascade,
  at timestamptz not null default app_now(),
  provider text not null check (provider in ('gmail', 'outlook')),
  seeds integer not null check (seeds > 0),
  inbox integer not null check (inbox >= 0),
  spam integer not null check (spam >= 0),
  missing integer not null check (missing >= 0),
  check (inbox + spam + missing = seeds)
);
create index on placement_tests (mailbox_id, at desc);

-- The simulated truth a seed test samples from, and that simulated buyers see. Hidden from the desk.
create table sim_mailboxes (
  mailbox_id bigint primary key references mailboxes on delete cascade,
  gmail numeric not null,
  outlook numeric not null,
  worsens_from timestamptz,
  worse_outlook numeric
);
