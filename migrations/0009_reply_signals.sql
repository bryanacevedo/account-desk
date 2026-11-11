-- What people tell us in replies ("I'm now at X") is a first-party signal source. Present on every database, so a
-- desk installed before this migration has it too; the seed skips it when it is already here.
insert into signal_sources (key, label, adapter, cadence_minutes, paid, provider)
values ('replies', 'Replies', 'webhook', 1440, false, 'What people tell us in replies, such as a new job')
on conflict (key) do nothing;
