-- What a source needs from outside: first-party sources (your product, CRM, events) need nothing; every
-- third-party source is a paid vendor of a named kind.
alter table signal_sources add column provider text not null default '';
