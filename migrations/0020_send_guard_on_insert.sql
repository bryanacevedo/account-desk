-- The send guard ran only when a message's status changed. A message written already marked sent would have skipped
-- every rule; the app never does that, and now the database refuses it the same way it refuses a bad update.
create trigger messages_send_guard_insert before insert on messages
  for each row when (new.status in ('sending', 'sent')) execute function message_send_guard();
