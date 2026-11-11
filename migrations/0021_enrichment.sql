-- Enrichment, made deep: who each field came from and how sure we are, company data from a vendor, catch-all
-- addresses resolved instead of stuck, phones typed and checked against do-not-call, one identity per LinkedIn
-- profile however the URL is written, and paid results kept even when the job that bought them rolls back.

-- People: what an enrichment vendor knows beyond a name and a title.
alter table people
  add column linkedin_key text,             -- the profile with no scheme, no www, no trailing slash, lower case
  add column departments text[] not null default '{}',
  add column role_started_at date,          -- when they started in the current role
  add column city text,
  add column headline text,
  add column match_confidence text check (match_confidence is null or match_confidence in ('high', 'medium', 'low')),
  add column email_found_by text,            -- which finder in the waterfall returned the address
  add column email_found_at timestamptz,
  add column email_confidence numeric check (email_confidence is null or email_confidence between 0 and 1),
  add column phone_type text check (phone_type is null or phone_type in ('mobile', 'direct', 'office', 'unknown')),
  add column phone_dnc boolean not null default false,
  add column enriched_at timestamptz;

update people set linkedin_key = rtrim(regexp_replace(regexp_replace(lower(trim(linkedin_url)), '^[a-z]+://', ''), '^www\.', ''), '/')
  where linkedin_url is not null;
-- Two rows for one profile (a trailing slash, a www) keep the older one's key; the newer is left unkeyed for a person.
with d as (select id, row_number() over (partition by linkedin_key order by id) as n from people where linkedin_key is not null)
update people p set linkedin_key = null from d where d.id = p.id and d.n > 1;
create unique index people_linkedin_key_uq on people (linkedin_key) where linkedin_key is not null;

-- A catch-all server accepts every address, so a check proves nothing: 'catch_all' is its own state, resolved by a
-- second vendor when one is set, and never sent to unless resolved.
alter table people drop constraint people_email_status_check;
alter table people add constraint people_email_status_check
  check (email_status in ('unknown', 'valid', 'risky', 'catch_all', 'invalid'));

-- Accounts: company data from a vendor, filling what the CRM and imports left blank.
alter table accounts
  add column keywords text[] not null default '{}',
  add column founded_year integer,
  add column total_funding_cents bigint,
  add column latest_funding_round text,
  add column latest_funding_at date,
  add column enriched_at timestamptz,
  add column enriched_by text;

-- Each company read is kept, so growth and changes are measured between two reads, not guessed from one.
create table account_snapshots (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  at timestamptz not null default app_now(),
  vendor text not null,
  data jsonb not null       -- headcount by department, technologies, open roles, funding
);
create index on account_snapshots (account_id, at desc);

-- Where every enriched field came from: the vendor, when, and how sure it was.
create table field_sources (
  id bigint generated always as identity primary key,
  object_kind text not null check (object_kind in ('person', 'account')),
  object_id bigint not null,
  field text not null,
  value text,
  vendor text not null,
  confidence numeric check (confidence is null or confidence between 0 and 1),
  at timestamptz not null default app_now()
);
create index on field_sources (object_kind, object_id, field, at desc);

-- A paid answer, kept outside the job that bought it: a job that rolls back and runs again reads it here instead of
-- buying it twice. Written on its own connection, like the ledger.
create table enrichment_results (
  kind text not null,       -- people_search | email_finder:<provider> | email_verifier | email_resolver | phone_finder | company
  key text not null,
  result jsonb not null,
  at timestamptz not null default now(),
  primary key (kind, key)
);

-- Which departments each persona sits in, matched before titles when the vendor says.
alter table personas add column departments text[] not null default '{}';
update personas set departments = '{finance}' where key = 'cfo';
update personas set departments = '{finance,accounting}' where key = 'controller';
update personas set departments = '{sales_operations,revenue_operations}' where key = 'revops';
update personas set departments = '{data,information_technology}' where key = 'data';

-- Enrichment is a source of signals of its own: a new person in a role, a team growing, a tool added or dropped.
insert into signal_sources (key, label, adapter, cadence_minutes, enabled, paid)
  values ('enrichment', 'Company and people data', 'enrichment', 1440, true, true) on conflict do nothing;
