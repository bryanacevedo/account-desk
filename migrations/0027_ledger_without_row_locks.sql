-- A vendor's charge is written on its own connection the moment the vendor answers, so it survives the job that made
-- the call rolling back (spend.paid_call, spend.charge_llm). A foreign key from that row to the account or play made the
-- write wait for a lock the job itself holds on that account or play, and the job waited for the write: the
-- 3,000-account demo build hung on it. The ledger keeps the ids as plain numbers, like an invoice line keeps a
-- customer number; an account or play that is later deleted leaves its spend on record.
alter table ledger drop constraint ledger_account_id_fkey;
alter table ledger drop constraint ledger_play_id_fkey;
