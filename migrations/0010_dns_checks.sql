-- Sending-domain authentication and blocklist status are read, not typed in: a daily check records what DNS says,
-- and a change stops sending from that domain until it is right again.
alter table sending_domains add column dkim_selector text;
alter table sending_domains add column dns_detail jsonb not null default '{}';
alter table sending_domains add column blocklists text[] not null default '{}';

-- Simulated DNS: a domain whose DKIM record goes missing for a few days, the way a DNS edit breaks it in real life.
create table sim_dns (
  domain text primary key references sending_domains on delete cascade,
  dkim_broken_from timestamptz,
  dkim_broken_until timestamptz
);
