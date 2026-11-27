-- BL-170: a person approves several drafts of one play and step in one action. Each draft is still its own approval (its own
-- hash, its own audit row); this table only says which approvals were made together. To take it back:
-- alter table messages drop column approval_batch_id, drop column taken_back_at, drop column taken_back_by; drop table approval_batches.
create table if not exists approval_batches (
  id bigint generated always as identity primary key,
  template_key text not null,
  approved_by bigint not null references users,
  at timestamptz not null default app_now(),
  requested integer not null,
  approved integer not null,
  skipped jsonb not null default '[]'
);
alter table messages add column if not exists approval_batch_id bigint references approval_batches;
alter table messages add column if not exists taken_back_at timestamptz;
alter table messages add column if not exists taken_back_by bigint references users;
create index if not exists messages_approval_batch on messages (approval_batch_id) where approval_batch_id is not null;
