-- A reply to someone in a blocked country is allowed (Bryan, 2026-11-15, decision 92): they wrote to us first.
-- The reply send guard no longer checks the region. A first email keeps the rule (message_send_guard is unchanged).
-- Risk: legal, high. Counsel to confirm.
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
