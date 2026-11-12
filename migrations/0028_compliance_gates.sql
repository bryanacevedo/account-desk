-- Compliance gates from the final review. Each one fails closed: a value nobody has set blocks contact.

-- Spain and the Netherlands ask for opt-in before commercial email, to businesses too. A desk that still has them
-- as basis_required moves to consent_required; a desk that chose something stricter keeps it.
update region_rules set rule = 'consent_required', note = 'Opt-in needed for commercial email, businesses included. Counsel to confirm.'
  where country in ('ES', 'NL') and rule = 'basis_required';

-- UK PECR: sole traders and partnerships are individual subscribers, so cold email to them needs consent. Only a
-- limited company (a corporate subscriber) may be emailed on legitimate interest. Unknown is treated as individual.
alter table accounts add column subscriber_type text not null default 'unknown'
  check (subscriber_type in ('corporate', 'individual', 'unknown'));

-- The legitimate-interest assessment behind a play: its reference (lia_ref, already there) and the date it is due
-- for review. A play that relies on it cannot launch without both, or once the review date has passed.
alter table plays add column lia_review_due date;

-- Calls follow their own rule per country, and name the do-not-call register screened before a call. A country
-- with no call rule is not called.
alter table region_rules
  add column call_rule text not null default 'blocked' check (call_rule in ('allowed', 'blocked')),
  add column dnc_register text;
alter table tasks add column dnc_register text;
-- The starting rules (src/outbound/seed/catalog.py CALL_RULES). Germany needs presumed consent for a business call
-- (UWG section 7) and the Netherlands keeps no register for business lines, so neither is called by default.
update region_rules r set call_rule = c.call_rule, dnc_register = c.register
  from (values ('US', 'allowed', 'National Do Not Call Registry'), ('CA', 'allowed', 'National Do Not Call List'),
               ('GB', 'allowed', 'TPS and CTPS'), ('FR', 'allowed', 'Bloctel'), ('ES', 'allowed', 'Lista Robinson'),
               ('IE', 'allowed', 'National Directory Database opt-out'), ('BR', 'allowed', 'Nao Me Perturbe'))
       as c(country, call_rule, register)
 where r.country = c.country;

-- Where a person's details came from, beyond the kind of source: the vendor, the file, the feed.
alter table people add column source_origin text;

-- An opt-out outlives the person's record: when the record is purged, their phone stays blocked by its hash.
alter table suppressions drop constraint suppressions_kind_check;
alter table suppressions add constraint suppressions_kind_check
  check (kind in ('email', 'domain', 'person', 'account', 'email_hash', 'phone', 'phone_hash', 'linkedin_hash'));

-- The database's half of the PECR rule, beside the region guard: no cold email to a UK individual or unknown
-- subscriber without consent, whatever path tries to send it.
create or replace function message_pecr_guard() returns trigger language plpgsql as $$
declare
  p record;
begin
  if new.channel <> 'email' or new.status not in ('sending', 'sent') then return new; end if;
  if tg_op = 'UPDATE' and (old.status = new.status or old.status in ('sending', 'send_unknown')) then return new; end if;
  select pe.id, pe.country, a.hq_country, a.subscriber_type into p
    from enrollments e join people pe on pe.id = e.person_id left join accounts a on a.id = pe.account_id
   where e.id = new.enrollment_id;
  if p.id is not null and (p.country = 'GB' or p.hq_country = 'GB') and coalesce(p.subscriber_type, 'unknown') <> 'corporate'
     and not exists (select 1 from contact_basis cb where cb.person_id = p.id and cb.basis = 'consent') then
    raise exception 'send refused: a UK subscriber that is not a limited company needs consent' using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger messages_pecr_guard before update of status on messages
  for each row execute function message_pecr_guard();
create trigger messages_pecr_guard_insert before insert on messages
  for each row when (new.status in ('sending', 'sent')) execute function message_pecr_guard();
