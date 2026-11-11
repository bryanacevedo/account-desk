-- Outbound Desk core schema.
-- Rules the database enforces live here as constraints and triggers, so the bad state cannot be written.
-- Everything about time reads app_now(), which is the simulated clock in demo mode and now() otherwise.

create table sim_clock (
  id boolean primary key default true check (id),
  enabled boolean not null default false,
  at timestamptz not null default now()
);
insert into sim_clock (id) values (true);

create function app_now() returns timestamptz language sql stable as $$
  select case when c.enabled then c.at else now() end from sim_clock c
$$;

create table settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now(),
  updated_by bigint
);

create function setting_bool(k text) returns boolean language sql stable as $$
  select coalesce((select (value)::text = 'true' from settings where key = k), false)
$$;

create table users (
  id bigint generated always as identity primary key,
  name text not null,
  email text not null unique,
  role text not null check (role in ('rep', 'manager', 'gtm')),
  slack_id text,
  timezone text not null default 'America/New_York',
  heyreach_consent boolean not null default false,
  active boolean not null default true
);

-- ------------------------------------------------------------------ ICP and accounts

create table icp_versions (
  id bigint generated always as identity primary key,
  rules jsonb not null,
  note text,
  published_by bigint references users,
  published_at timestamptz not null default now()
);

create table accounts (
  id bigint generated always as identity primary key,
  name text not null,
  parent_id bigint references accounts on delete set null,
  primary_domain text not null unique check (primary_domain = lower(primary_domain)),
  name_key text not null default '',
  industry text,
  employees integer check (employees is null or employees >= 0),
  revenue_band text,
  hq_country text,
  region text,
  tech text[] not null default '{}',
  description text,
  lifecycle text not null default 'prospect'
    check (lifecycle in ('prospect', 'customer', 'open_opp', 'churned', 'competitor', 'partner')),
  owner_id bigint references users,
  crm_id text unique,
  fit_score integer check (fit_score between 0 and 100),
  fit_tier text check (fit_tier in ('A', 'B', 'C', 'X')),
  fit_breakdown jsonb,
  fit_icp_version bigint references icp_versions,
  source text not null default 'crm',
  created_at timestamptz not null default app_now()
);

create index accounts_name_key on accounts (name_key);

create table account_domains (
  domain text primary key check (domain = lower(domain) and domain not like 'www.%'),
  account_id bigint not null references accounts on delete cascade
);
create index on account_domains (account_id);

create table personas (
  key text primary key,
  label text not null,
  title_patterns text[] not null,
  seniority text[] not null default '{}',
  committee_role text not null check (committee_role in ('economic_buyer', 'champion', 'user', 'technical', 'blocker')),
  angle text not null
);

create table people (
  id bigint generated always as identity primary key,
  account_id bigint references accounts on delete set null,
  full_name text not null,
  first_name text,
  last_name text,
  title text,
  seniority text,
  function text,
  persona_key text references personas,
  email text check (email is null or email = lower(email)),
  email_status text not null default 'unknown' check (email_status in ('unknown', 'valid', 'risky', 'invalid')),
  email_verified_at timestamptz,
  email_verified_by text,
  linkedin_url text,
  phone text,
  phone_status text not null default 'unknown' check (phone_status in ('unknown', 'valid', 'invalid')),
  phone_verified_at timestamptz,
  is_champion boolean not null default false,
  country text,
  timezone text,
  status text not null default 'active' check (status in ('active', 'left', 'unreachable')),
  source text not null,
  crm_id text,
  created_at timestamptz not null default app_now(),
  check (email_status = 'unknown' or email_verified_at is not null)
);
create unique index people_email_uq on people (email) where email is not null;
create unique index people_linkedin_uq on people (linkedin_url) where linkedin_url is not null;
create index on people (account_id);

-- Evidence. A brief or a draft may cite only these ids.
create table facts (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  person_id bigint references people on delete cascade,
  kind text not null,
  text text not null check (length(text) > 0),
  source text not null,
  source_url text,
  observed_at timestamptz not null,
  created_at timestamptz not null default app_now()
);
create index on facts (account_id, observed_at desc);

-- ------------------------------------------------------------------ signals

create table signal_types (
  key text primary key,
  label text not null,
  because text not null check (length(because) > 10),
  level text not null check (level in ('account', 'person')),
  weight numeric not null,
  half_life_days numeric not null check (half_life_days > 0),
  enabled boolean not null default true
);

create table signal_sources (
  key text primary key,
  label text not null,
  adapter text not null,
  cadence_minutes integer not null check (cadence_minutes > 0),
  enabled boolean not null default true,
  paid boolean not null default false
);

create table source_runs (
  id bigint generated always as identity primary key,
  source_key text not null references signal_sources,
  started_at timestamptz not null default app_now(),
  finished_at timestamptz,
  fetched integer not null default 0,
  matched integer not null default 0,
  unmatched integer not null default 0,
  duplicates integer not null default 0,
  error text
);
create index on source_runs (source_key, started_at desc);

create table signals (
  id bigint generated always as identity primary key,
  type_key text not null references signal_types,
  source text not null references signal_sources,
  external_id text not null,
  account_id bigint references accounts on delete cascade,
  person_id bigint references people on delete set null,
  raw_domain text,
  raw_company text,
  observed_at timestamptz not null,
  ingested_at timestamptz not null default app_now(),
  strength numeric not null check (strength between 0 and 1),
  evidence jsonb not null check (evidence ? 'summary' and (evidence ? 'url' or evidence ? 'quote')),
  status text not null check (status in ('matched', 'unmatched', 'ignored')),
  status_reason text,
  unique (source, external_id),
  check (status <> 'matched' or account_id is not null),
  check (status = 'matched' or status_reason is not null)
);
create index on signals (account_id, observed_at desc);
create index on signals (status, ingested_at desc);

-- ------------------------------------------------------------------ scoring

create table account_scores (
  account_id bigint primary key references accounts on delete cascade,
  computed_at timestamptz not null,
  fit integer not null,
  intent integer not null,
  engagement integer not null,
  priority integer not null,
  inputs jsonb not null,      -- everything needed to recompute: signals with ages, weights, icp version
  breakdown jsonb not null,
  reason_signal_id bigint references signals on delete set null
);
create index on account_scores (priority desc);

create table score_history (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  at timestamptz not null,
  priority integer not null,
  previous integer,
  reason_signal_id bigint references signals on delete set null
);
create index on score_history (account_id, at desc);

-- ------------------------------------------------------------------ plays

create table plays (
  id bigint generated always as identity primary key,
  key text not null unique,
  name text not null,
  hypothesis text not null,
  trigger jsonb not null,
  personas text[] not null,
  max_people integer not null default 3 check (max_people between 1 and 6),
  sequence jsonb not null,
  angle text not null,
  autonomy text not null default 'draft' check (autonomy in ('research', 'draft', 'supervised', 'autonomous')),
  status text not null default 'draft' check (status in ('draft', 'live', 'paused', 'retired')),
  holdout_pct integer not null default 10 check (holdout_pct between 0 and 50),
  positive_floor numeric not null default 0.02,
  owner_id bigint references users,
  launched_by bigint references users,
  launched_at timestamptz,
  sla_hours integer not null default 4,
  latency_hours integer not null default 48,
  urgent boolean not null default false,
  version integer not null default 1,
  created_by bigint references users,
  lia_ref text,
  check (status <> 'live' or (launched_by is not null and launched_at is not null)),
  check (launched_by is null or created_by is null or launched_by <> created_by)
);

create table play_stage_changes (
  id bigint generated always as identity primary key,
  play_id bigint not null references plays,
  at timestamptz not null default app_now(),
  from_stage text not null,
  to_stage text not null,
  reason text not null,
  decided_by bigint references users
);

create table account_plays (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  play_id bigint not null references plays,
  trigger_signal_id bigint not null references signals,
  arm text not null check (arm in ('treated', 'holdout')),
  state text not null check (state in ('proposed', 'accepted', 'researching', 'approving', 'active', 'engaged',
                                        'meeting', 'converted', 'lost', 'stopped', 'skipped', 'expired', 'held_out')),
  why_now jsonb not null,
  owner_id bigint references users,
  brief jsonb,
  proposed_at timestamptz not null default app_now(),
  decided_at timestamptz,
  decided_by bigint references users,
  closed_at timestamptz,
  close_reason text,
  check (state not in ('lost', 'stopped', 'skipped', 'expired') or close_reason is not null),
  check (arm = 'treated' or state = 'held_out')
);
create unique index account_plays_one_open on account_plays (account_id)
  where state in ('proposed', 'accepted', 'researching', 'approving', 'active', 'engaged', 'meeting');
create index on account_plays (play_id, state);
create index on account_plays (owner_id, state);

create table committee_gaps (
  account_play_id bigint not null references account_plays on delete cascade,
  persona_key text not null references personas,
  reason text not null,
  primary key (account_play_id, persona_key)
);

-- ------------------------------------------------------------------ deliverability

create table sending_domains (
  domain text primary key,
  spf boolean not null default false,
  dkim boolean not null default false,
  dmarc boolean not null default false,
  dmarc_policy text check (dmarc_policy in ('none', 'quarantine', 'reject')),
  dmarc_aligned boolean not null default false,
  daily_cap integer not null default 60,
  spam_rate numeric,
  spam_rate_at timestamptz,
  postmaster_status text,
  registered_at date not null,
  blocklisted boolean not null default false,
  checked_at timestamptz,
  is_primary_brand boolean not null default false
);

create table mailboxes (
  id bigint generated always as identity primary key,
  address text not null unique check (address = lower(address)),
  domain text not null references sending_domains,
  provider text not null,
  display_name text not null,
  user_id bigint not null references users,
  warmup_started date not null,
  ramp_start date not null,
  status text not null default 'active' check (status in ('active', 'paused', 'retired')),
  pause_reason text,
  check (status = 'active' or pause_reason is not null)
);

-- ------------------------------------------------------------------ outreach

create table enrollments (
  id bigint generated always as identity primary key,
  account_play_id bigint not null references account_plays on delete cascade,
  person_id bigint not null references people on delete cascade,
  persona_key text not null references personas,
  state text not null check (state in ('pending', 'active', 'paused', 'stopped', 'done')),
  step_index integer not null default 0,
  next_at timestamptz,
  pause_until timestamptz,
  pause_reason text,
  stop_reason text,
  mailbox_id bigint references mailboxes,
  via_referral boolean not null default false,
  started_at timestamptz,
  created_at timestamptz not null default app_now(),
  check (state <> 'stopped' or stop_reason is not null),
  check (state <> 'paused' or pause_reason is not null)
);
create unique index enrollments_one_live_per_person on enrollments (person_id)
  where state in ('pending', 'active', 'paused');
create index on enrollments (account_play_id);
create index on enrollments (state, next_at);

create table messages (
  id bigint generated always as identity primary key,
  enrollment_id bigint not null references enrollments on delete cascade,
  step_index integer not null,
  channel text not null check (channel in ('email', 'linkedin', 'call', 'task')),
  subject text,
  body text not null,
  citations jsonb not null default '[]',
  body_hash text not null,
  status text not null check (status in ('draft', 'failed_gate', 'awaiting_approval', 'approved', 'rejected',
                                         'scheduled', 'sending', 'sent', 'send_unknown', 'failed', 'cancelled')),
  gate jsonb,
  attempts jsonb not null default '[]',
  approved_hash text,
  approved_by bigint references users,
  approval_mode text check (approval_mode in ('person', 'auto_supervised', 'auto_autonomous')),
  approved_at timestamptz,
  rejected_reason text,
  scheduled_for timestamptz,
  sent_at timestamptz,
  mailbox_id bigint references mailboxes,
  provider_id text,
  thread_key text,
  template_key text,
  edited boolean not null default false,
  planned_for timestamptz,
  created_at timestamptz not null default app_now(),
  unique (enrollment_id, step_index),
  check (status <> 'rejected' or rejected_reason is not null),
  check (status not in ('approved', 'scheduled', 'sending', 'sent', 'send_unknown')
         or (approved_hash is not null and approved_at is not null and approval_mode is not null)),
  check (status not in ('sent', 'send_unknown') or (sent_at is not null and mailbox_id is not null or channel <> 'email'))
);
create index on messages (status, scheduled_for);
create index on messages (mailbox_id, sent_at);

create function message_hash() returns trigger language plpgsql as $$
begin
  new.body_hash := encode(sha256(convert_to(coalesce(new.subject, '') || E'\n' || new.body, 'UTF8')), 'hex');
  return new;
end $$;
create trigger messages_hash before insert or update of subject, body on messages
  for each row execute function message_hash();

create table suppressions (
  id bigint generated always as identity primary key,
  kind text not null check (kind in ('email', 'domain', 'person', 'account', 'email_hash', 'phone')),
  value text not null,
  reason text not null,
  source text not null,
  created_at timestamptz not null default app_now(),
  expires_at timestamptz
);
create index on suppressions (kind, value);

create table holds (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  person_id bigint references people on delete cascade,
  reason text not null,
  until timestamptz not null,
  set_by text not null,
  created_at timestamptz not null default app_now()
);
create index on holds (account_id, until);

-- The last line of defence. A message can only become 'sending' or 'sent' when every rule below holds at that moment.
create function message_send_guard() returns trigger language plpgsql as $$
declare
  e record; ap record; p record; a record;
begin
  if new.status not in ('sending', 'sent') or old.status = new.status then return new; end if;
  if new.approved_hash is distinct from new.body_hash then
    raise exception 'send refused: body changed after approval (message %)', new.id using errcode = 'P0001';
  end if;
  if setting_bool('kill_switch') then
    raise exception 'send refused: kill switch is on' using errcode = 'P0001';
  end if;
  select * into e from enrollments where id = new.enrollment_id;
  if e.state <> 'active' then
    raise exception 'send refused: enrollment % is %', e.id, e.state using errcode = 'P0001';
  end if;
  select * into ap from account_plays where id = e.account_play_id;
  if ap.arm <> 'treated' then
    raise exception 'send refused: holdout account' using errcode = 'P0001';
  end if;
  if ap.state not in ('active', 'engaged') then
    raise exception 'send refused: account play is %', ap.state using errcode = 'P0001';
  end if;
  select * into p from people where id = e.person_id;
  select * into a from accounts where id = ap.account_id;
  if a.lifecycle in ('customer', 'open_opp', 'competitor') or exists (
       select 1 from accounts par where par.id = a.parent_id and par.lifecycle in ('customer', 'open_opp', 'competitor')) then
    raise exception 'send refused: account is %', a.lifecycle using errcode = 'P0001';
  end if;
  if exists (select 1 from suppressions s
             where (s.expires_at is null or s.expires_at > app_now())
               and ((s.kind = 'email' and s.value = p.email)
                 or (s.kind = 'email_hash' and s.value = encode(sha256(convert_to(coalesce(p.email, ''), 'UTF8')), 'hex'))
                 or (s.kind = 'domain' and p.email is not null and s.value = split_part(p.email, '@', 2))
                 or (s.kind = 'person' and s.value = p.id::text)
                 or (s.kind = 'account' and s.value = a.id::text))) then
    raise exception 'send refused: suppressed' using errcode = 'P0001';
  end if;
  if exists (select 1 from holds h where h.account_id = a.id and (h.person_id is null or h.person_id = p.id)
             and h.until > app_now()) then
    raise exception 'send refused: on hold' using errcode = 'P0001';
  end if;
  if new.channel = 'email' and (p.email is null or p.email_status <> 'valid') then
    raise exception 'send refused: email not valid' using errcode = 'P0001';
  end if;
  if new.channel = 'email' and exists (select 1 from region_rules rr where rr.country = p.country and rr.rule = 'blocked') then
    raise exception 'send refused: region blocked' using errcode = 'P0001';
  end if;
  if new.channel = 'email' and exists (select 1 from region_rules rr where rr.country = p.country
                                           and rr.rule in ('basis_required', 'consent_required'))
     and not exists (select 1 from contact_basis cb where cb.person_id = p.id
                     and (cb.basis = 'consent' or not exists (select 1 from region_rules r2 where r2.country = p.country
                                                               and r2.rule = 'consent_required'))) then
    raise exception 'send refused: no contact basis recorded' using errcode = 'P0001';
  end if;
  if p.status <> 'active' then
    raise exception 'send refused: person is %', p.status using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger messages_send_guard before update of status on messages
  for each row execute function message_send_guard();

-- No more than the account's cap of people active at once.
create function enrollment_cap_guard() returns trigger language plpgsql as $$
declare cap integer; n integer; acct bigint;
begin
  if new.state <> 'active' or (tg_op = 'UPDATE' and old.state = 'active') then return new; end if;
  select ap.account_id,
         case when a.fit_tier = 'A' and pl.max_people > 3
              then coalesce((select (value)::text::integer from settings where key = 'account_max_active_wide'), 5)
              else coalesce((select (value)::text::integer from settings where key = 'account_max_active'), 3) end
    into acct, cap
    from account_plays ap join accounts a on a.id = ap.account_id join plays pl on pl.id = ap.play_id
   where ap.id = new.account_play_id;
  perform 1 from accounts where id = acct for update;   -- serialise activations per account
  select count(*) into n from enrollments en join account_plays ap on ap.id = en.account_play_id
   where ap.account_id = acct and en.state = 'active' and en.id <> new.id;
  if n >= cap then
    raise exception 'account % already has % people active (cap %)', acct, n, cap using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger enrollments_cap before insert or update of state on enrollments
  for each row execute function enrollment_cap_guard();

-- ------------------------------------------------------------------ touches, replies, meetings

create table touches (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  person_id bigint references people on delete cascade,
  account_play_id bigint references account_plays on delete set null,
  channel text not null check (channel in ('email', 'linkedin', 'call', 'meeting', 'other')),
  direction text not null check (direction in ('out', 'in')),
  kind text not null,
  at timestamptz not null,
  source text not null,
  message_id bigint references messages on delete set null,
  dedup_key text not null unique
);
create index on touches (person_id, at desc);
create index on touches (account_id, at desc);

create table replies (
  id bigint generated always as identity primary key,
  message_id bigint references messages on delete set null,
  person_id bigint references people on delete set null,
  account_id bigint references accounts on delete set null,
  channel text not null default 'email',
  received_at timestamptz not null,
  from_addr text not null,
  subject text,
  raw text not null,
  cleaned text not null,
  language text,
  label text check (label in ('interested', 'meeting_request', 'question', 'not_now', 'not_interested', 'referral',
                              'left_company', 'out_of_office', 'unsubscribe', 'wrong_person', 'bounce', 'auto_reply', 'other')),
  confidence numeric,
  same_person boolean,
  extracted jsonb not null default '{}',
  classified_by text check (classified_by in ('rules', 'model', 'person')),
  needs_review boolean not null default false,
  review_reason text,
  hot boolean not null default false,
  sla_due_at timestamptz,
  escalated_at timestamptz,
  handled_by bigint references users,
  handled_at timestamptz,
  outcome text,
  provider_id text unique,
  check (not needs_review or review_reason is not null)
);
create index on replies (account_id, received_at desc);
create index on replies (needs_review) where needs_review;

create table meetings (
  id bigint generated always as identity primary key,
  account_play_id bigint references account_plays on delete set null,
  account_id bigint not null references accounts on delete cascade,
  person_id bigint references people on delete set null,
  owner_id bigint references users,
  booked_at timestamptz not null,
  starts_at timestamptz not null,
  status text not null check (status in ('booked', 'held', 'no_show', 'cancelled')),
  source text not null,
  external_id text unique
);
create index on meetings (account_id);

create table call_notes (
  id bigint generated always as identity primary key,
  meeting_id bigint not null references meetings on delete cascade,
  text text not null,
  worth_learning boolean,
  marked_by bigint references users,
  created_at timestamptz not null default app_now()
);

create table learnings (
  id bigint generated always as identity primary key,
  call_note_id bigint not null references call_notes on delete cascade,
  kind text not null check (kind in ('objection', 'competitor', 'reason_to_buy', 'reason_not', 'quote')),
  text text not null,
  quote text not null,
  play_id bigint references plays,
  signal_type text references signal_types
);

create table opportunities (
  id bigint generated always as identity primary key,
  account_id bigint not null references accounts on delete cascade,
  crm_id text unique,
  name text not null,
  amount_cents bigint not null check (amount_cents >= 0),
  stage text not null,
  created_at timestamptz not null,
  closed_at timestamptz,
  won boolean,
  source_play_id bigint references plays,
  account_play_id bigint references account_plays on delete set null,
  attribution text not null default 'none' check (attribution in ('sourced', 'influenced', 'none'))
);

create table tasks (
  id bigint generated always as identity primary key,
  account_play_id bigint references account_plays on delete cascade,
  person_id bigint references people on delete cascade,
  message_id bigint references messages on delete set null,
  reply_id bigint references replies on delete cascade,
  kind text not null check (kind in ('call', 'linkedin_connect', 'linkedin_message', 'research', 'reply', 'referral', 'review_reply')),
  title text not null,
  due_at timestamptz not null,
  owner_id bigint references users,
  status text not null default 'open' check (status in ('open', 'done', 'skipped')),
  note text,
  done_at timestamptz
);
create index on tasks (owner_id, status, due_at);

-- ------------------------------------------------------------------ operations

create table jobs (
  id bigint generated always as identity primary key,
  kind text not null,
  payload jsonb not null default '{}',
  run_at timestamptz not null default app_now(),
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed', 'dead')),
  attempts integer not null default 0,
  max_attempts integer not null default 5,
  locked_at timestamptz,
  locked_by text,
  last_error text,
  dedupe_key text,
  created_at timestamptz not null default app_now(),
  finished_at timestamptz
);
create unique index jobs_dedupe on jobs (dedupe_key) where dedupe_key is not null and status in ('queued', 'running');
create index jobs_ready on jobs (run_at) where status = 'queued';

create table crm_outbox (
  id bigint generated always as identity primary key,
  kind text not null,
  payload jsonb not null,
  idempotency_key text not null unique,
  status text not null default 'pending' check (status in ('pending', 'done', 'dead')),
  attempts integer not null default 0,
  next_at timestamptz not null default app_now(),
  last_error text,
  created_at timestamptz not null default app_now(),
  done_at timestamptz
);
create index on crm_outbox (status, next_at);

create table adapter_calls (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  adapter text not null,
  operation text not null,
  paid boolean not null,
  ok boolean not null,
  ms integer,
  detail jsonb
);

create table ledger (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  vendor text not null,
  unit text not null check (unit in ('credits', 'tokens', 'calls')),
  qty numeric not null check (qty >= 0),
  cost_cents numeric not null check (cost_cents >= 0),
  purpose text not null,
  account_id bigint references accounts on delete set null,
  adapter_call_id bigint references adapter_calls on delete set null
);
create index on ledger (vendor, at);

create table budgets (
  vendor text primary key,
  monthly_cap_cents bigint not null check (monthly_cap_cents >= 0)
);

create table llm_calls (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  task text not null,
  model text not null,
  input_hash text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cost_cents numeric not null default 0,
  output jsonb not null,
  source text not null check (source in ('live', 'recorded', 'sim'))
);

create table alerts (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  kind text not null,
  severity text not null check (severity in ('info', 'warn', 'urgent')),
  channel text not null,
  target_user bigint references users,
  object_kind text,
  object_id bigint,
  title text not null,
  body text not null,
  delivered_at timestamptz,
  delivery_error text,
  acked_at timestamptz,
  dedup_key text unique
);
create index on alerts (delivered_at) where delivered_at is null;

create table monitor_runs (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  monitor text not null,
  ok boolean not null,
  found integer not null,
  sample jsonb,
  error text
);
create index on monitor_runs (monitor, at desc);

create table audit_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default app_now(),
  actor_id bigint references users,
  actor text not null,
  action text not null,
  object_kind text not null,
  object_id bigint,
  detail jsonb not null default '{}'
);
create index on audit_log (object_kind, object_id);

create table holidays (
  country text not null,
  day date not null,
  name text not null,
  primary key (country, day)
);

create table region_rules (
  country text primary key,
  rule text not null check (rule in ('allowed', 'basis_required', 'consent_required', 'blocked')),
  note text not null default 'Counsel to confirm.'
);

create table contact_basis (
  person_id bigint primary key references people on delete cascade,
  basis text not null,
  recorded_by bigint references users,
  recorded_at timestamptz not null default app_now()
);

create table deliveries (
  id bigint generated always as identity primary key,
  message_id bigint references messages on delete cascade,
  mailbox_id bigint references mailboxes,
  event text not null check (event in ('sent', 'delivered', 'bounced_hard', 'bounced_soft', 'complaint')),
  at timestamptz not null,
  email_source text,
  detail jsonb not null default '{}'
);
create index on deliveries (mailbox_id, at);
create index on deliveries (event, at);

create table research_cache (
  domain text not null,
  kind text not null,
  content jsonb not null,
  fetched_at timestamptz not null,
  primary key (domain, kind)
);

create table person_moves (
  id bigint generated always as identity primary key,
  person_id bigint not null references people on delete cascade,
  from_account_id bigint references accounts on delete set null,
  to_account_id bigint references accounts on delete set null,
  at timestamptz not null,
  corroborated_by text not null
);

create table placement_tests (
  id bigint generated always as identity primary key,
  mailbox_id bigint not null references mailboxes on delete cascade,
  at timestamptz not null,
  provider text not null,
  inbox_pct numeric not null check (inbox_pct between 0 and 100),
  detail jsonb not null default '{}'
);

create table play_step_watch (
  template_key text primary key,
  sends integer not null default 0,
  hard_bounces integer not null default 0,
  complaints integer not null default 0,
  paused boolean not null default false,
  paused_reason text,
  check (not paused or paused_reason is not null)
);
