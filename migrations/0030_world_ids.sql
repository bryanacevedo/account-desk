-- The shared world's ids (shared-world DESIGN.md 6.1): a company's world id and a person's `pe_` id, as the demo's
-- company-data and people vendors deliver them. Nothing in the desk depends on them existing: a real install has none,
-- and its accounts match by CRM id, domain and each vendor's own id.
alter table accounts add column world_id text;
create unique index accounts_world_id on accounts (world_id) where world_id is not null;
alter table people add column world_id text;
create unique index people_world_id on people (world_id) where world_id is not null;

-- A person who changed address (the roster renames Grace Osei to Leah Ahn): the old address still names her when a
-- CRM or a webhook uses it. Lower case.
create table user_aliases (
  alias text primary key check (alias = lower(alias)),
  user_id bigint not null references users on delete cascade
);
