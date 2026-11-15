-- Alerts at the top of Inboxes and Health (bl_125, decision 86; SPEC 23.2).
--
-- An alert can now end (resolved_at), says which tab it belongs on (scope) and can name a text object (object_key),
-- because a sending domain is keyed by its name, not by a number. Nothing already written changes: the columns are new
-- and the three that matter to the coverage count (kind, object_kind, object_id) are left as they were.
alter table alerts
  add column resolved_at timestamptz,
  add column scope text not null default 'health' check (scope in ('health', 'inboxes', 'both')),
  add column object_key text;

-- Rows written before this migration: scope from kind (the same list as alerts.KIND_SCOPE; anything else is Health).
update alerts set scope = 'inboxes' where kind in ('complaint', 'mailbox_paused', 'mailbox_warn', 'placement_hold',
  'placement_pause', 'spam_rate', 'spam_rate_warn', 'dns_broken', 'dns_fixed', 'no_mailbox', 'reply_drop',
  'watch_paused', 'send_unknown');
-- A domain alert's name was only in its dedup key ("dns:<domain>:<date>", "spam:<domain>:<date>").
update alerts set object_key = split_part(dedup_key, ':', 2),
                  object_kind = coalesce(object_kind, 'domain')
  where kind in ('dns_broken', 'dns_fixed', 'spam_rate', 'spam_rate_warn') and dedup_key is not null and object_id is null;
-- A paused step is named by its template key, which holds colons ("watch:<play>:<step>").
update alerts set object_key = substr(dedup_key, 7), object_kind = 'play_step'
  where kind = 'watch_paused' and dedup_key like 'watch:%' and object_kind is null;

-- Rows whose condition had already ended before this migration are closed, so a desk that has run for weeks does not open
-- on a wall of old alerts. The same tests the code applies when it resolves them from now on.
update alerts a set resolved_at = app_now() where a.resolved_at is null and a.acked_at is null and (
     (a.kind in ('hot_reply', 'sla_missed') and a.object_kind = 'reply'
        and exists (select 1 from replies r where r.id = a.object_id and r.handled_at is not null))
  or (a.kind in ('mailbox_paused', 'mailbox_warn', 'placement_pause') and a.object_kind = 'mailbox'
        and exists (select 1 from mailboxes m where m.id = a.object_id and m.status = 'active'))
  or (a.kind in ('placement_hold', 'mailbox_paused', 'mailbox_warn', 'placement_pause') and a.object_kind = 'mailbox'
        and exists (select 1 from mailboxes m where m.id = a.object_id and m.status = 'retired'))
  or (a.kind = 'dns_broken' and exists (select 1 from sending_domains d where d.domain = a.object_key
        and d.spf and d.dkim and d.dmarc and d.dmarc_aligned and not d.blocklisted))
  or (a.kind = 'spam_rate_warn' and exists (select 1 from sending_domains d where d.domain = a.object_key
        and d.spam_rate < 0.001))
  or (a.kind = 'spam_rate' and exists (select 1 from sending_domains d where d.domain = a.object_key
        and d.spam_rate < 0.003 and coalesce(d.postmaster_status, '') <> 'needs_work'))
  or (a.kind = 'no_mailbox' and exists (select 1 from mailboxes m where m.user_id = a.target_user and m.status = 'active'))
  or (a.kind = 'send_unknown' and a.object_kind = 'message'
        and exists (select 1 from messages m where m.id = a.object_id and m.status <> 'send_unknown'))
);

-- One group per condition, however many days it raised a row: kind and what it is about (an alert that is about
-- nothing in particular is told apart by who it is for and its title).
alter table alerts add column gkey text generated always as (
  kind || '|' || coalesce(object_kind, '') || '|' || coalesce(object_id::text, '') || '|' || coalesce(object_key, '')
  || case when object_kind is null and object_id is null and object_key is null
          then '|' || coalesce(target_user::text, '') || '|' || title else '' end) stored;

create index alerts_open_idx on alerts (scope, severity, at desc) where acked_at is null and resolved_at is null;
create index alerts_open_kind_idx on alerts (kind) where acked_at is null and resolved_at is null;
