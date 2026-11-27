-- BL-111: the SDR's own note on the meeting they booked, written for the account executive. Account Desk carries it to the
-- deal in the CRM as the "SDR note" of the handoff (with the play and the signal), never generated and never filled in for them.
-- Separate from call_notes, which are written after a meeting is held. To take it back: alter table meetings drop column sdr_note, drop column sdr_note_by.
alter table meetings add column if not exists sdr_note text;
alter table meetings add column if not exists sdr_note_by bigint references users;
