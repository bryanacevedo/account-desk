-- BL-171: the Supervised stage's automatic approval of follow-up emails becomes an owned policy: a named manager, a reason, an end
-- date. src/outbound/standing.py holds the rules. A desk upgrading gets one carried-over policy per play now at Supervised, owned by
-- the manager of its latest promotion (signed_by_person false: nobody signed it, sign again to confirm), and every follow-up already
-- queued under the old rule is linked to it. To take it back: alter table messages drop column standing_approval_id; drop table standing_approvals.
create table if not exists standing_approvals (
  id bigint generated always as identity primary key,
  play_id bigint not null references plays,
  play_version integer not null,
  tiers text[] not null default '{A,B}',
  steps integer[],
  owner_id bigint not null references users,
  reason text not null,
  signed_by_person boolean not null default true,
  regions text not null default 'allowed_only' check (regions in ('allowed_only', 'carried_over')),
  signed_at timestamptz not null default app_now(),
  ends_on date not null,
  revoked_at timestamptz,
  revoked_by bigint references users,
  revoke_reason text,
  revoke_kind text check (revoke_kind in ('person', 'complaint', 'bounces', 'editing', 'play_changed', 'replaced', 'expired')),
  check (revoked_at is null or revoke_kind is not null)
);
create index if not exists standing_approvals_play on standing_approvals (play_id, signed_at desc);
alter table messages add column if not exists standing_approval_id bigint references standing_approvals;

insert into standing_approvals (play_id, play_version, owner_id, reason, signed_by_person, ends_on)
select p.id, p.version,
       coalesce((select c.decided_by from play_stage_changes c where c.play_id = p.id and c.to_stage = 'supervised' and c.decided_by is not null
                 order by c.at desc limit 1),
                (select u.id from users u where u.role = 'manager' and u.active order by u.id limit 1)),
       'Carried over from the Supervised stage when standing approvals were introduced (BL-171). Sign again to confirm.',
       false, app_now()::date + 90
from plays p
where p.autonomy = 'supervised' and p.status = 'live'
  and coalesce((select c.decided_by from play_stage_changes c where c.play_id = p.id and c.to_stage = 'supervised' and c.decided_by is not null
                order by c.at desc limit 1),
               (select u.id from users u where u.role = 'manager' and u.active order by u.id limit 1)) is not null
  and not exists (select 1 from standing_approvals s where s.play_id = p.id);

update messages m set standing_approval_id = s.id
from enrollments e join account_plays ap on ap.id = e.account_play_id join standing_approvals s on s.play_id = ap.play_id
where e.id = m.enrollment_id and m.approval_mode = 'auto_supervised' and m.status in ('approved', 'scheduled')
  and m.standing_approval_id is null and s.signed_by_person = false;
