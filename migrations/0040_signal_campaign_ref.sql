-- Events Desk step 6 part 3 (decision 94): a signal made from a campaign member names its campaign, so the desk can say
-- how many plays started from one event's signals without reading names. Null for every other signal and for member
-- signals made before this migration (they are not counted by the campaign read).
alter table signals add column campaign_ref text;
create index signals_campaign_ref on signals (campaign_ref) where campaign_ref is not null;
-- A person who declined an event is remembered by a row in the audit log, so an older row still in the member feed cannot
-- make a signal for them afterwards.
create index audit_log_member_declined on audit_log ((detail ->> 'key')) where action = 'member_declined';
