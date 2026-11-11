-- Indexes for the paths a production-size desk walks on every reply, gate check and results load.
create index if not exists messages_thread_key on messages (thread_key) where thread_key is not null;
create index if not exists messages_provider_id on messages (provider_id) where provider_id is not null;
create index if not exists messages_enrollment on messages (enrollment_id);
create index if not exists touches_account_play on touches (account_play_id) where account_play_id is not null;
create index if not exists holds_person on holds (person_id, until) where person_id is not null;
create index if not exists signals_person on signals (person_id) where person_id is not null;
create index if not exists signals_type on signals (type_key, status);
create index if not exists account_plays_trigger on account_plays (trigger_signal_id);
create index if not exists account_plays_account on account_plays (account_id, proposed_at desc);
create index if not exists replies_person on replies (person_id, received_at desc);
create index if not exists meetings_account_booked on meetings (account_id, booked_at);
create index if not exists suppressions_value on suppressions (value, kind);
create index if not exists jobs_running on jobs (locked_at) where status = 'running';
alter table plays alter column holdout_pct set default 20;
