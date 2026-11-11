-- The simulated world's hidden truth. Only the simulator reads these; the desk never does.
create table sim_accounts (
  account_id bigint primary key references accounts on delete cascade,
  need numeric not null check (need between 0 and 1),
  pages jsonb not null,          -- what a research agent would read on the company's site
  story jsonb not null default '{}'
);
create table sim_people (
  person_id bigint primary key references people on delete cascade,
  true_email text,
  email_truth text not null check (email_truth in ('valid', 'invalid', 'catch_all')),
  responsiveness numeric not null,
  phone_truth text,
  moves_to bigint references accounts
);
create table sim_events (
  id bigint generated always as identity primary key,
  at timestamptz not null,
  kind text not null,
  payload jsonb not null,
  done boolean not null default false
);
create index on sim_events (done, at);

-- People who exist in the world but are not yet in the desk's records. Only the simulated people search reads it.
create table sim_hidden_people (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  full_name text not null, first_name text not null, last_name text not null,
  title text not null, seniority text, linkedin_url text not null, country text, timezone text,
  true_email text not null, email_truth text not null, responsiveness numeric not null, phone_truth text,
  is_champion boolean not null default false,
  found_person_id bigint references people on delete set null
);
create index on sim_hidden_people (account_id);
alter table sim_hidden_people add column photo_url text;
