-- An email's number among the emails of its sequence, not its step: in "email, LinkedIn, email, call, email" the last
-- one is Email 3, not Email 5. One rule, used by every screen that names an email.
create or replace function email_no(enrollment bigint, step int) returns int language sql stable as $$
  select coalesce((
    select count(*)::int from enrollments e
      join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id,
      jsonb_array_elements(pl.sequence) with ordinality as s(v, i)
    where e.id = enrollment and s.i - 1 <= step and s.v->>'channel' = 'email'), step + 1)
$$;
