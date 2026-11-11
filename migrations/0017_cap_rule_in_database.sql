-- The daily cap is computed by the database from its own rule, not read from a value the sending code wrote:
-- the ramp (5 a day, plus 5 a week from ramp start, up to the desk's maximum), held at 10 while the domain's spam
-- rate is unknown, old or at 0.1% and above, and while the mailbox's seed tests are missing, old or below the hold
-- line. The sending code reads the same function, so there is one rule.

create or replace function setting_num(k text, fallback numeric) returns numeric language sql stable as $$
  select coalesce((select (value #>> '{}')::numeric from settings where key = k), fallback)
$$;

create or replace function mailbox_cap(mb_id bigint) returns integer language plpgsql stable as $$
declare
  mb record; d record; cap integer; n integer; worst numeric; oldest timestamptz;
begin
  select * into mb from mailboxes where id = mb_id;
  if not found then return 0; end if;
  cap := least(setting_num('mailbox_max_daily', 30)::integer,
               5 + 5 * greatest(0, (app_now()::date - mb.ramp_start) / 7));
  select * into d from sending_domains where domain = mb.domain;
  if d.spam_rate is null or coalesce(d.spam_rate_at, '-infinity'::timestamptz) < app_now() - interval '7 days'
     or d.spam_rate >= 0.001 then
    cap := least(cap, 10);
  end if;
  select count(*), min(rate), min(at) into n, worst, oldest from (
    select distinct on (provider) inbox::numeric / seeds as rate, at from placement_tests
    where mailbox_id = mb_id order by provider, at desc) latest;
  if n = 0 or oldest < app_now() - make_interval(days => setting_num('placement_max_age_days', 10)::integer)
     or worst < setting_num('placement_hold_below', 0.8) then
    cap := least(cap, 10);
  end if;
  return cap;
end $$;

create or replace function message_send_guard() returns trigger language plpgsql as $$
declare
  e record; ap record; p record; a record;
begin
  if new.status not in ('sending', 'sent') or old.status = new.status then return new; end if;
  -- Recording the outcome of a send already under way is not a new send: the email has left (or may have).
  if old.status in ('sending', 'send_unknown') then return new; end if;
  if new.approved_hash is distinct from new.body_hash then
    raise exception 'send refused: body changed after approval (message %)', new.id using errcode = 'P0001';
  end if;
  if setting_bool('kill_switch') then
    raise exception 'send refused: kill switch is on' using errcode = 'P0001';
  end if;
  select * into e from enrollments where id = new.enrollment_id;
  -- A LinkedIn note or a call is done by hand after the sequence moved on, so a finished sequence may still
  -- record it. Paused or stopped never may: someone replied, or the play ended.
  if e.state <> 'active' and not (new.channel <> 'email' and e.state = 'done') then
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
                 or (s.kind = 'account' and s.value = a.id::text)
                 or (s.kind = 'linkedin_hash' and p.linkedin_url is not null and s.value = encode(sha256(convert_to(
                       rtrim(regexp_replace(regexp_replace(lower(trim(p.linkedin_url)), '^[a-z]+://', ''), '^www\.', ''), '/'),
                       'UTF8')), 'hex')))) then
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
  -- Guarantee 20: nobody is emailed after engaging on another channel in the same account play (a LinkedIn reply,
  -- a call where they spoke). An accepted connection is not engagement (docs/SPEC.md 22.19).
  if new.channel = 'email' and exists (select 1 from touches t where t.person_id = p.id and t.account_play_id = ap.id
       and t.channel in ('linkedin', 'call') and (t.direction = 'in' or t.kind = 'call_connected')
       and t.kind <> 'linkedin_accepted') then
    raise exception 'send refused: engaged on another channel' using errcode = 'P0001';
  end if;
  -- Guarantee 8: no mailbox sends past its cap for the day, and no domain past its own. The desk sets the day's cap
  -- under a row lock just before sending; a cap not set today means nothing sends from that mailbox.
  if new.channel = 'email' then
    -- Take the mailbox's and the domain's locks here, so two sends can never both count the last free slot,
    -- whichever code path sends them.
    perform 1 from mailboxes where id = new.mailbox_id for update;
    perform 1 from sending_domains where domain = (select domain from mailboxes where id = new.mailbox_id) for update;
    if (select count(*) from messages x where x.mailbox_id = new.mailbox_id and x.id <> new.id
          and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
       >= mailbox_cap(new.mailbox_id) then
      raise exception 'send refused: mailbox at its daily cap' using errcode = 'P0001';
    end if;
    if (select count(*) from messages x join mailboxes mb on mb.id = x.mailbox_id
          where mb.domain = (select domain from mailboxes where id = new.mailbox_id) and x.id <> new.id
          and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
       >= (select d.daily_cap from sending_domains d join mailboxes mb on mb.domain = d.domain where mb.id = new.mailbox_id) then
      raise exception 'send refused: domain at its daily cap' using errcode = 'P0001';
    end if;
  end if;
  -- Guarantee 6: nobody is emailed after replying since their sequence started. Out-of-office and automatic
  -- replies do not count; a reply not yet labelled does (stop first, read after).
  if new.channel = 'email' and exists (select 1 from replies r where r.person_id = p.id
       and r.received_at >= coalesce(e.started_at, e.created_at)
       and coalesce(r.label, 'unlabelled') not in ('out_of_office', 'auto_reply', 'bounce')) then
    raise exception 'send refused: they replied' using errcode = 'P0001';
  end if;
  if p.status <> 'active' then
    raise exception 'send refused: person is %', p.status using errcode = 'P0001';
  end if;
  return new;
end $$;
