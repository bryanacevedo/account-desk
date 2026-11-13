-- The account book and the contact check when a CRM runs beside this desk (shared-world DESIGN.md 5, 6.2, 7 steps 2, 4, 5).
-- Nothing here is read unless a CRM that has the optional methods is configured; alone, every column stays null.

-- A tier and a segment read from the CRM (Market Desk writes them there). When crm_tier is set, the account's fit tier
-- follows it; when it is null the desk's own fit decides, as before.
alter table accounts add column crm_tier text check (crm_tier is null or crm_tier in ('A', 'B', 'C', 'X'));
alter table accounts add column crm_segment text;
alter table accounts add column crm_fit_score integer check (crm_fit_score is null or crm_fit_score between 0 and 100);
alter table accounts add column crm_icp_version text;
alter table accounts add column crm_read_at timestamptz;

-- The CRM's answer to "may this person be contacted", kept per person. One row per person: the check runs once, before
-- the first touch, and a wait (the CRM did not answer) is counted here so a long outage raises an alert.
create table crm_contact_checks (
  person_id bigint primary key references people on delete cascade,
  state text not null check (state in ('ok', 'waiting', 'stopped', 'erased')),
  checked_at timestamptz,
  waits integer not null default 0,
  last_error text,
  answer jsonb
);
