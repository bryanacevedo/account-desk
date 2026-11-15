-- Reply studio (bl_121, decision 90; SPEC 23.4). A reply is a person writing back, not a sequence step: `messages`
-- needs an enrollment and a step. Their answer goes in its own table, with its own send guard, and counts against the
-- same mailbox and domain caps as any send (the message guard below now counts both).
--
-- Risk: legal, high. The guard keeps the blocked-country rule for replies as for any send (a region set to blocked
-- refuses a reply too) until Bryan decides whether answering someone who wrote to us should be allowed there.
create table reply_sends (
  id bigint generated always as identity primary key,
  reply_id bigint not null references replies on delete cascade,
  user_id bigint not null references users,
  person_id bigint references people on delete cascade,
  mailbox_id bigint references mailboxes,
  subject text,
  body text not null,
  body_hash text not null,
  approved_hash text not null,
  status text not null default 'queued' check (status in ('queued', 'sending', 'sent', 'send_unknown', 'failed', 'cancelled')),
  provider_id text,
  thread_key text,
  in_reply_to text,
  error text,
  sent_at timestamptz,
  created_at timestamptz not null default app_now(),
  unique (reply_id, body_hash)
);
create index on reply_sends (mailbox_id, sent_at) where status in ('sending', 'sent', 'send_unknown');

create or replace function reply_send_hash() returns trigger language plpgsql as $$
begin
  new.body_hash := encode(sha256(convert_to(coalesce(new.subject, '') || E'\n' || new.body, 'UTF8')), 'hex');
  if tg_op = 'INSERT' then new.approved_hash := new.body_hash; end if;
  return new;
end $$;
create trigger reply_send_hash_t before insert or update of subject, body on reply_sends
  for each row execute function reply_send_hash();

create or replace function reply_send_guard() returns trigger language plpgsql as $$
declare
  r record; p record;
begin
  if new.status not in ('sending', 'sent') then return new; end if;
  if tg_op = 'UPDATE' and (old.status = new.status or old.status in ('sending', 'send_unknown')) then return new; end if;
  if new.approved_hash is distinct from new.body_hash then
    raise exception 'send refused: body changed after it was queued (reply send %)', new.id using errcode = 'P0001';
  end if;
  if setting_bool('kill_switch') then
    raise exception 'send refused: kill switch is on' using errcode = 'P0001';
  end if;
  select * into r from replies where id = new.reply_id;
  if coalesce(r.label, 'unlabelled') in ('unsubscribe', 'bounce', 'out_of_office', 'auto_reply') then
    raise exception 'send refused: this reply is %', r.label using errcode = 'P0001';
  end if;
  select * into p from people where id = new.person_id;
  if p.id is null then
    raise exception 'send refused: no person on this reply' using errcode = 'P0001';
  end if;
  if p.status <> 'active' then
    raise exception 'send refused: person is %', p.status using errcode = 'P0001';
  end if;
  if p.email_status = 'invalid' then
    raise exception 'send refused: the address bounced' using errcode = 'P0001';
  end if;
  -- Stop first, read after: a newer message from them that is unlabelled or asks to stop holds this answer.
  if exists (select 1 from replies x where x.person_id = p.id and x.received_at > r.received_at and x.id <> r.id
             and (x.label is null or x.label = 'unsubscribe' or x.needs_review)) then
    raise exception 'send refused: they wrote again' using errcode = 'P0001';
  end if;
  if erasure_key() is null and exists (select 1 from suppressions s
       where s.kind in ('email_hmac', 'linkedin_hmac', 'phone_hmac') and (s.expires_at is null or s.expires_at > app_now())) then
    raise exception 'send refused: erasure key not set in this session' using errcode = 'P0001';
  end if;
  if exists (select 1 from suppressions s
             where (s.expires_at is null or s.expires_at > app_now())
               and ((s.kind = 'email' and s.value in (p.email, r.from_addr))
                 or (s.kind = 'email_hash' and s.value in (encode(sha256(convert_to(coalesce(p.email, ''), 'UTF8')), 'hex'),
                                                          encode(sha256(convert_to(coalesce(r.from_addr, ''), 'UTF8')), 'hex')))
                 or (s.kind = 'domain' and s.value = split_part(coalesce(p.email, r.from_addr), '@', 2))
                 or (s.kind = 'person' and s.value = p.id::text)
                 or (s.kind = 'account' and s.value = r.account_id::text)
                 or (s.kind = 'email_hmac' and s.value in (erasure_hmac(lower(btrim(coalesce(p.email, '')))),
                                                          erasure_hmac(lower(btrim(coalesce(r.from_addr, '')))))))) then
    raise exception 'send refused: suppressed' using errcode = 'P0001';
  end if;
  if exists (select 1 from region_rules rr where rr.country = p.country and rr.rule = 'blocked') then
    raise exception 'send refused: region blocked' using errcode = 'P0001';
  end if;
  perform 1 from mailboxes where id = new.mailbox_id for update;
  perform 1 from sending_domains where domain = (select domain from mailboxes where id = new.mailbox_id) for update;
  if (select count(*) from messages x where x.mailbox_id = new.mailbox_id
        and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
     + (select count(*) from reply_sends rs where rs.mailbox_id = new.mailbox_id and rs.id <> new.id
        and rs.status in ('sending', 'sent', 'send_unknown') and rs.sent_at >= date_trunc('day', app_now()))
     >= mailbox_cap(new.mailbox_id) then
    raise exception 'send refused: mailbox at its daily cap' using errcode = 'P0001';
  end if;
  if (select count(*) from messages x join mailboxes mb on mb.id = x.mailbox_id
        where mb.domain = (select domain from mailboxes where id = new.mailbox_id)
        and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
     + (select count(*) from reply_sends rs join mailboxes mb on mb.id = rs.mailbox_id
        where mb.domain = (select domain from mailboxes where id = new.mailbox_id) and rs.id <> new.id
        and rs.status in ('sending', 'sent', 'send_unknown') and rs.sent_at >= date_trunc('day', app_now()))
     >= (select d.daily_cap from sending_domains d join mailboxes mb on mb.domain = d.domain where mb.id = new.mailbox_id) then
    raise exception 'send refused: domain at its daily cap' using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger reply_send_guard_t before insert or update of status on reply_sends
  for each row when (new.status in ('sending', 'sent')) execute function reply_send_guard();

-- The message guard now counts reply sends in both caps.
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
  -- Erasure hashes are keyed (HMAC) with this install's key, which the application puts in the session setting
  -- outbound.erasure_key on every connection. A session without it cannot check those rows, so it refuses to send
  -- at all while any exist: failing closed, never silently skipping them. A desk with none of them is unaffected.
  if erasure_key() is null and exists (select 1 from suppressions s
       where s.kind in ('email_hmac', 'linkedin_hmac', 'phone_hmac') and (s.expires_at is null or s.expires_at > app_now())) then
    raise exception 'send refused: erasure key not set in this session' using errcode = 'P0001';
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
                       'UTF8')), 'hex'))
                 or (s.kind = 'email_hmac' and p.email is not null and s.value = erasure_hmac(lower(btrim(p.email))))
                 or (s.kind = 'linkedin_hmac' and p.linkedin_url is not null and s.value = erasure_hmac(
                       rtrim(regexp_replace(regexp_replace(lower(btrim(p.linkedin_url)), '^[a-z]+://', ''), '^www\.', ''), '/')))
                 or (s.kind = 'phone_hmac' and new.channel = 'call' and p.phone is not null
                       and s.value = erasure_hmac(regexp_replace(p.phone, '\D', '', 'g'))))) then
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
  -- Guarantee 8: no mailbox sends past its cap for the day (mailbox_cap() computes it here), and no domain past its own.
  if new.channel = 'email' then
    -- Take the mailbox's and the domain's locks here, so two sends can never both count the last free slot,
    -- whichever code path sends them.
    perform 1 from mailboxes where id = new.mailbox_id for update;
    perform 1 from sending_domains where domain = (select domain from mailboxes where id = new.mailbox_id) for update;
    if (select count(*) from messages x where x.mailbox_id = new.mailbox_id and x.id <> new.id
          and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
       + (select count(*) from reply_sends rs where rs.mailbox_id = new.mailbox_id
          and rs.status in ('sending', 'sent', 'send_unknown') and rs.sent_at >= date_trunc('day', app_now()))
       >= mailbox_cap(new.mailbox_id) then
      raise exception 'send refused: mailbox at its daily cap' using errcode = 'P0001';
    end if;
    if (select count(*) from messages x join mailboxes mb on mb.id = x.mailbox_id
          where mb.domain = (select domain from mailboxes where id = new.mailbox_id) and x.id <> new.id
          and x.status in ('sending', 'sent', 'send_unknown') and x.sent_at >= date_trunc('day', app_now()))
       + (select count(*) from reply_sends rs join mailboxes mb on mb.id = rs.mailbox_id
          where mb.domain = (select domain from mailboxes where id = new.mailbox_id)
          and rs.status in ('sending', 'sent', 'send_unknown') and rs.sent_at >= date_trunc('day', app_now()))
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
