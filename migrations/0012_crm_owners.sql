-- Account ownership comes from the CRM: a reassignment there moves the account, its open play and its open work.
alter table accounts add column crm_owner_email text;

-- The simulated CRM's ownership changes (territory rebalancing), read by the desk like any CRM change.
create table sim_crm_owner_changes (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  owner_email text not null,
  updated_at timestamptz not null
);
create index on sim_crm_owner_changes (updated_at);
