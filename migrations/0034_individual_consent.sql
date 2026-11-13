-- Where the law splits subscribers into companies and natural persons, a sole trader or partnership is a natural person,
-- so a cold email to one needs consent even where a company may be emailed on a recorded basis. The United Kingdom
-- (PECR) had this rule written for it alone, in the contact gate and in message_pecr_guard (migration 0028); it is now a
-- flag on the country's region rule, set for Finland and Portugal too in the starting rules (decision 72). A country
-- with the flag set needs a subscriber type of corporate on the account, or consent on the person.
alter table region_rules add column individual_consent boolean not null default false;
update region_rules set individual_consent = true where country = 'GB';

create or replace function message_pecr_guard() returns trigger language plpgsql as $$
declare
  p record;
begin
  if new.channel <> 'email' or new.status not in ('sending', 'sent') then return new; end if;
  if tg_op = 'UPDATE' and (old.status = new.status or old.status in ('sending', 'send_unknown')) then return new; end if;
  select pe.id, pe.country, a.hq_country, a.subscriber_type into p
    from enrollments e join people pe on pe.id = e.person_id left join accounts a on a.id = pe.account_id
   where e.id = new.enrollment_id;
  if p.id is not null and coalesce(p.subscriber_type, 'unknown') <> 'corporate'
     and exists (select 1 from region_rules rr where rr.individual_consent and rr.country in (p.country, p.hq_country))
     and not exists (select 1 from contact_basis cb where cb.person_id = p.id and cb.basis = 'consent') then
    raise exception 'send refused: a subscriber that is not a limited company needs consent in this country'
      using errcode = 'P0001';
  end if;
  return new;
end $$;
