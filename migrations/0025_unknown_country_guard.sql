-- A country with no region rule, or a person whose country is not known, is treated as needing consent: no cold
-- email goes there until a manager adds a rule for it. The contact gate says so in words ("Email in Australia needs
-- a region rule first"); this is the database's half of the same rule, so no other path can send it.
create or replace function message_region_guard() returns trigger language plpgsql as $$
declare
  p record;
begin
  if new.channel <> 'email' or new.status not in ('sending', 'sent') then return new; end if;
  if tg_op = 'UPDATE' and (old.status = new.status or old.status in ('sending', 'send_unknown')) then return new; end if;
  select pe.id, pe.country into p from enrollments e join people pe on pe.id = e.person_id where e.id = new.enrollment_id;
  if p.id is not null and not exists (select 1 from region_rules rr where rr.country = p.country)
     and not exists (select 1 from contact_basis cb where cb.person_id = p.id and cb.basis = 'consent') then
    raise exception 'send refused: no region rule for %', coalesce(p.country, 'an unknown country') using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger messages_region_guard before update of status on messages
  for each row execute function message_region_guard();
create trigger messages_region_guard_insert before insert on messages
  for each row when (new.status in ('sending', 'sent')) execute function message_region_guard();
