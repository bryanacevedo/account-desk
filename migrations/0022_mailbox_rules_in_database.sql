-- The database refuses an email from a mailbox the desk would never send from: paused or retired, on a domain whose
-- authentication is incomplete, that is blocklisted, younger than 30 days, still warming up, or at a spam rate of
-- 0.3% or more. Until now only the sending code checked these; any other path that sent got only the cap.
create or replace function message_mailbox_guard() returns trigger language plpgsql as $$
declare
  mb record; d record;
begin
  if new.channel <> 'email' or new.status not in ('sending', 'sent') then return new; end if;
  if tg_op = 'UPDATE' and (old.status = new.status or old.status in ('sending', 'send_unknown')) then return new; end if;
  select * into mb from mailboxes where id = new.mailbox_id;
  if mb is null then
    raise exception 'send refused: no mailbox (message %)', new.id using errcode = 'P0001';
  end if;
  if mb.status <> 'active' then
    raise exception 'send refused: mailbox % is %', mb.address, mb.status using errcode = 'P0001';
  end if;
  if (app_now()::date - mb.warmup_started) < 14 then
    raise exception 'send refused: mailbox % is still warming up', mb.address using errcode = 'P0001';
  end if;
  select * into d from sending_domains where domain = mb.domain;
  if d is null or not (d.spf and d.dkim and d.dmarc and d.dmarc_aligned) then
    raise exception 'send refused: domain % authentication incomplete', mb.domain using errcode = 'P0001';
  end if;
  if d.blocklisted then
    raise exception 'send refused: domain % is on a blocklist', mb.domain using errcode = 'P0001';
  end if;
  if (app_now()::date - d.registered_at) < 30 then
    raise exception 'send refused: domain % is younger than 30 days', mb.domain using errcode = 'P0001';
  end if;
  if d.spam_rate is not null and d.spam_rate >= 0.003 then
    raise exception 'send refused: domain % spam rate at or above 0.3%%', mb.domain using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger messages_mailbox_guard before update of status on messages
  for each row execute function message_mailbox_guard();
create trigger messages_mailbox_guard_insert before insert on messages
  for each row when (new.status in ('sending', 'sent')) execute function message_mailbox_guard();
