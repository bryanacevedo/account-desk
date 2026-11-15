-- Country email rules you can edit (bl_130, decision 85; SPEC 23.1). Risk: legal. Counsel to confirm the starting list.
--
-- The starting rules move here from the generators, so every build (demo, legacy, live, world) starts from the same rows.
-- They are exactly what src/outbound/seed/catalog.py REGION_RULES, CALL_RULES, REGION_NOTES and INDIVIDUAL_CONSENT held
-- (a test fails if the two differ). Seeded only when the table is empty: a desk that already holds any rows keeps exactly
-- those, because no row for a country means no cold email to it, and filling a gap here would make a refused country sendable.
insert into region_rules (country, rule, call_rule, dnc_register, note, individual_consent)
select * from (values
  ('US', 'allowed', 'allowed', 'National Do Not Call Registry', 'Counsel to confirm.', false),
  ('CA', 'consent_required', 'allowed', 'National Do Not Call List', 'Counsel to confirm.', false),
  ('GB', 'basis_required', 'allowed', 'TPS and CTPS', 'Counsel to confirm.', true),
  ('DE', 'consent_required', 'blocked', null, 'Counsel to confirm.', false),
  ('FR', 'basis_required', 'allowed', 'Bloctel', 'Counsel to confirm.', false),
  ('NL', 'consent_required', 'blocked', null, 'Counsel to confirm.', false),
  ('ES', 'consent_required', 'allowed', 'Lista Robinson', 'Counsel to confirm.', false),
  ('IE', 'basis_required', 'allowed', 'National Directory Database opt-out', 'Counsel to confirm.', false),
  ('BR', 'basis_required', 'allowed', 'Nao Me Perturbe', 'Counsel to confirm.', false),
  ('SG', 'blocked', 'blocked', null, 'Counsel to confirm.', false),
  ('IT', 'consent_required', 'blocked', null, 'Opt-in for email (Codice privacy art. 130(1)-(2)); the soft opt-in of art. 130(4) covers customers only. Counsel to confirm.', false),
  ('CH', 'consent_required', 'blocked', null, 'Opt-in for mass email (UWG art. 3(1)(o)), companies included; opt-out link and correct sender in each email. Counsel to confirm.', false),
  ('SE', 'consent_required', 'blocked', null, 'Opt-in for a natural person (Marknadsforingslagen 19 s.); a named work address read as a natural person. Counsel to confirm.', false),
  ('DK', 'consent_required', 'blocked', null, 'Opt-in for anyone, companies included (Markedsforingsloven 10(1)); an address to stop messages in each email. Counsel to confirm.', false),
  ('BE', 'consent_required', 'blocked', null, 'Opt-in (CDE art. XII.13); only an impersonal company address (info@) is exempt (Royal Decree 4 April 2003). Counsel to confirm.', false),
  ('AT', 'consent_required', 'blocked', null, 'Opt-in for any recipient (TKG 2021 s. 174(3)), no B2B exception; a real address to stop messages (s. 174(5)). Counsel to confirm.', false),
  ('NO', 'consent_required', 'blocked', null, 'Opt-in for every natural person, a work address in a person''s name included (Markedsforingsloven 15 s.). Counsel to confirm.', false),
  ('FI', 'basis_required', 'blocked', null, 'Opt-out for companies (Act 917/2014 s. 202), opt-in for natural persons, sole traders included (s. 200). Counsel to confirm.', true),
  ('PT', 'basis_required', 'blocked', null, 'Opt-out for companies, with the DGC list (Lei 41/2004 art. 13-A(2), 13-B); opt-in for natural persons. Counsel to confirm.', true),
  ('MX', 'allowed', 'blocked', null, 'Opt-out: allowed with an unsubscribe in each email; no source settles what a cold B2B email needs under the 2025 privacy law. Counsel to confirm.', false)
) as v (country, rule, call_rule, dnc_register, note, individual_consent)
where not exists (select 1 from region_rules);

-- Every change of a rule, who made it and why. No row for a country means its rule is still the starting list.
-- changed_by is null for a change the desk itself made (the setup config).
create table region_rule_changes (
  id bigserial primary key,
  country text not null,
  at timestamptz not null default app_now(),
  changed_by bigint references users,
  from_rule text not null,
  to_rule text not null check (to_rule in ('allowed', 'basis_required', 'consent_required', 'blocked')),
  from_individual_consent boolean not null default false,
  to_individual_consent boolean not null default false,
  reason text not null check (length(trim(reason)) >= 10)
);
create index region_rule_changes_country on region_rule_changes (country, id desc);

-- The one way to change a rule: the history row and the rule in one call. A country with no row gets one (from 'none').
create function change_region_rule(p_country text, p_rule text, p_individual_consent boolean, p_reason text,
                                   p_changed_by bigint, p_note text default 'Counsel to confirm.',
                                   p_call_rule text default 'blocked', p_dnc_register text default null)
returns void language plpgsql as $$
declare
  old record;
begin
  select rule, individual_consent into old from region_rules where country = p_country for update;
  perform set_config('outbound.rule_change', p_country || '|' || p_rule || '|' || p_individual_consent::text, true);
  insert into region_rule_changes (country, changed_by, from_rule, to_rule, from_individual_consent, to_individual_consent, reason)
    values (p_country, p_changed_by, coalesce(old.rule, 'none'), p_rule, coalesce(old.individual_consent, false),
            p_individual_consent, p_reason);
  if old.rule is null then
    insert into region_rules (country, rule, individual_consent, note, call_rule, dnc_register)
      values (p_country, p_rule, p_individual_consent, p_note, p_call_rule, p_dnc_register);
  else
    update region_rules set rule = p_rule, individual_consent = p_individual_consent where country = p_country;
  end if;
  perform set_config('outbound.rule_change', '', true);
end $$;

-- No silent change: a rule or its individual-consent flag can be inserted or updated only inside change_region_rule, which
-- sets a transaction-local flag naming the country, the new rule and the new consent flag, and clears it when done. A flag
-- (not the history row's xmin) so it holds inside savepoints. A row is never deleted; call fields are not guarded.
-- Maintenance that must bypass it runs with session_replication_role = replica.
create function region_rule_change_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'a region rule is never deleted' using errcode = 'P0001';
  end if;
  if tg_op = 'UPDATE' and new.rule is not distinct from old.rule
     and new.individual_consent is not distinct from old.individual_consent then
    return new;
  end if;
  if current_setting('outbound.rule_change', true) is distinct from
     new.country || '|' || new.rule || '|' || new.individual_consent::text then
    raise exception 'a region rule changes only with a recorded reason (region_rule_changes)' using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger region_rules_change_guard before insert or delete or update of rule, individual_consent on region_rules
  for each row execute function region_rule_change_guard();
