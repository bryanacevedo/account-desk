-- An erased person is kept out by a fingerprint of their LinkedIn address as well as their email, so a people
-- search that finds them again by profile cannot bring them back.
alter table suppressions drop constraint suppressions_kind_check;
alter table suppressions add constraint suppressions_kind_check
  check (kind in ('email', 'domain', 'person', 'account', 'email_hash', 'phone', 'linkedin_hash'));
