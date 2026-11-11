-- A person's profile photo, as the enrichment vendor reports it (a URL, never stored bytes). Erased with the person.
alter table people add column photo_url text check (photo_url is null or photo_url ~ '^https://');
