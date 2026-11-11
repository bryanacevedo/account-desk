-- The CRM becomes a source the desk reads, not only a place it writes. Deals arrive by reading the CRM; their
-- attribution is recomputed whenever the deal or a meeting it rests on changes.

alter table opportunities add column updated_at timestamptz;
alter table opportunities add column loss_reason text;
alter table opportunities add column contact_email text;
alter table opportunities add column attribution_meeting_id bigint references meetings on delete set null;
alter table opportunities add column attributed_at timestamptz;
create index on opportunities (account_id);

alter table meetings add column notes_at timestamptz;
create index on meetings (account_play_id);

-- The simulated CRM: what a real one would hold. The desk only ever sees it through the CRM adapter's pull.
create table sim_crm_deals (
  id bigint generated always as identity primary key,
  crm_id text not null unique,
  account_id bigint not null references accounts on delete cascade,
  name text not null,
  amount_cents bigint not null,
  stage text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  closed_at timestamptz,
  won boolean,
  loss_reason text,
  contact_email text,
  -- hidden: how this deal will end
  close_on timestamptz not null,
  will_win boolean not null
);
create index on sim_crm_deals (updated_at);
