-- A CRM deal on an account the desk does not know yet is held, not passed over: it is read again whenever accounts
-- arrive (an import, an account added from a signal) and on every CRM read, and attributed once its account exists.
create table crm_held_deals (
  crm_id text primary key,
  account_domain text not null,
  deal jsonb not null,
  first_seen timestamptz not null default app_now(),
  last_tried timestamptz not null default app_now()
);
create index on crm_held_deals (account_domain);
