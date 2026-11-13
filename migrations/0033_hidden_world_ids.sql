-- The world's person id on the simulated people vendor's hidden people, and whether the vendor can find them at all
-- (shared-world DESIGN.md 4.2: some people are in no contact database). Both stay null/true in the legacy demo.
alter table sim_hidden_people add column world_id text;
create unique index sim_hidden_people_world_id on sim_hidden_people (world_id) where world_id is not null;
alter table sim_hidden_people add column vendor_findable boolean not null default true;
