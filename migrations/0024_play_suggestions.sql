-- Plays suggested from call learnings (docs/PLAY-SUGGESTIONS.md).
--
-- A learning is filed under a theme: one short label for one idea, unique per kind whatever its case. Code finds a
-- pattern in the themes (src/outbound/suggestions.py) and the desk proposes a play built on it. A person decides.

create table learning_themes (
  id bigint generated always as identity primary key,
  kind text not null check (kind in ('objection', 'competitor', 'reason_to_buy', 'reason_not')),
  label text not null check (length(btrim(label)) between 1 and 80),
  created_at timestamptz not null default app_now()
);
create unique index learning_themes_label on learning_themes (kind, lower(label));

alter table learnings add column theme_id bigint references learning_themes on delete set null;
create index learnings_theme on learnings (theme_id);

-- Who wrote the notes, which is not always who marked them worth learning from.
alter table call_notes add column written_by bigint references users;
update call_notes set written_by = marked_by where written_by is null;
create index call_notes_created on call_notes (created_at);

-- The theme a play was suggested from. A play stays when its theme is erased; it just stops saying where it came from.
alter table plays add column suggested_from bigint references learning_themes on delete set null;

create table play_suggestions (
  id bigint generated always as identity primary key,
  -- Null only for a drafted suggestion whose theme was erased: its play stays, and so does the record of it.
  theme_id bigint references learning_themes on delete set null,
  segment_signal_type text not null references signal_types,
  evidence jsonb not null,  -- counts, rates, p and pairs tested; never quotes or names
  draft jsonb not null,     -- the drafted play: name, hypothesis, trigger.any_of, personas, angle
  status text not null default 'open' check (status in ('open', 'drafted', 'not_now', 'dismissed', 'lapsed')),
  reason text,
  decided_by bigint references users,
  decided_at timestamptz,
  play_id bigint references plays,
  accounts_at_decision integer check (accounts_at_decision >= 0),
  created_at timestamptz not null default app_now(),
  check (status <> 'open' or (theme_id is not null and decided_at is null)),
  -- A person decides drafted, not now and no; the desk lapses a suggestion whose pattern went away.
  check (status not in ('drafted', 'not_now', 'dismissed') or (decided_by is not null and decided_at is not null)),
  check (status <> 'lapsed' or decided_at is not null),
  check (status <> 'not_now' or length(btrim(coalesce(reason, ''))) > 0),
  check (status <> 'drafted' or play_id is not null)
);
-- One open suggestion per theme.
create unique index play_suggestions_one_open on play_suggestions (theme_id) where status = 'open';
create index play_suggestions_theme on play_suggestions (theme_id, status);
