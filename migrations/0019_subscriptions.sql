-- Flat fees the desk cannot meter: the mail provider's seats, seed tests, the LinkedIn tool's senders, paid signal
-- feeds. Entered by a manager from the vendor's bill; the cost page adds them to what the desk meters itself.
create table subscriptions (
  key text primary key,                 -- a vendor key from the cost page, or a signal source key
  unit_cents bigint not null check (unit_cents >= 0),
  per text not null default 'month' check (per in ('month', 'mailbox', 'sender')),
  assumed boolean not null default true, -- true until someone enters the figure from a real bill
  note text
);
