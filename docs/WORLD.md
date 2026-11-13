# World mode

`WORLD=world` builds the demo from the shared world's slice in `world/` (Lumen Ledger's invented companies, people and
signals) instead of the desk's own generator. `WORLD=legacy`, the default, is unchanged. The setting is read each time it
is asked (`integration.world_mode()`).

## Commands

    WORLD=world python -m outbound demo          # from the cut (2026-08-13 12:00 UTC) to the world's now (2026-11-12 14:00 UTC)
    WORLD=world python -m outbound demo 5        # five days from the cut, for a quick look or a test
    python -m outbound demo                      # the desk's own demo, as before

The printed JSON carries `world_mode` and, under `world`, what was loaded (counts, the world version).

## What is checked first

`sim/world_load.py` checks every file in `world/manifest.json` against its sha256 before reading a row. A file that is
missing, changed, or a manifest in another format version stops the build with a `SliceError`; nothing is loaded. It is the
only module that opens the slice's `truth/` folder, and `tests/test_truth_guard.py` fails if another module mentions it
(the release's own `world/guard.py`).

## What it loads

| From the slice | Into the desk |
|---|---|
| `truth/companies.csv`, `company_data.csv` | `accounts` (with `world_id`, every domain in `account_domains`, CRM id `CRM-A...`), `sim_accounts` (hidden need, billing tool, the site pages composed from the company's own fields). Owner is an active SDR by region, as before, with 12% unowned (by hash of the world id). The lifecycle on the cut: customer, former customer (churned), or prospect (open opportunity when a deal is open). A subsidiary's `parent_id` is set when its parent is in the build. |
| `truth/people.csv` | People in a seat on the cut: about 55% (by hash of the person id) are in the CRM (`people` with `world_id` = the `pe_` id, plus `sim_people`); the rest, and everyone whose seat starts later, are in `sim_hidden_people`, which only the simulated people search reads. A leave date after the cut becomes `sim_people.left_at`. People who left before the cut are not loaded. Portrait keys become `randomuser.me` addresses. |
| `truth/seat_changes.csv` | `sim_seat_changes` for each new finance leader who starts after the cut, with the `announced` flag. |
| `truth/deals.csv` | `sim_crm_deals` for deals of the history era: closed won or lost as they stood on the cut; open ones close on the planned date, the planned way. |
| `truth/signals.csv` | Each day's signals in the runner, in the same raw shape the sources ingest. `new_finance_leader` is `new_exec`, source `job_change_feed` is `people_moves`. Evidence is built from the signal id (so it is the same every build) and uses the file's `detail` where it fits. A signal at a company that is not in the build is skipped. |
| `truth/behavior.json` | The no-show share and the chance a held meeting opens a deal (`meetings_and_deals`). |
| `public/team.csv` | `users`: everyone with an Account Desk role (`sdr`, `gtm`, `manager`), in the order the demo has always used. Someone whose start date is after the world's now (Nadia Haddad, 2026-12-01) is inactive: no mailbox, no accounts, no work. Account executives and others with a blank role are not users. The old address `grace.osei@lumenledger.example` is an alias (`user_aliases`) for `leah.ahn@lumenledger.example`. |
| `public/seller.json` | Sending domains (all `.example`) and the billing tools the desk treats as ones it replaces (`competing_tools`: the five competitors, plus Chargebee and Zuora). |
| `public/clock.json` | The window the demo runs over. |

## What it ignores

- `truth/people.csv` `phone_dnc`, `phone_type`, `human_id` (a job mover keeps one LinkedIn profile, which the desk already uses to match them).
- `deals.csv` deals of the `scheduled` era, `deal_roles.csv`, `call_notes.csv`, `attendance.csv`, `customers.csv` churn dates in the rehearsal, `public/events.csv`.
- The legacy generator's extras: signals about companies outside the account list, the second source for a job change, the random rate tables. The world's signals are the whole supply.
- Reply behaviour (`behavior.json` `reply`, `positive_reply`, `unsubscribe`): it is decided in `sim/recipients.py`, which is not part of this change, so replies still use the desk's own numbers. The `no_show` and `opportunity_from_meeting` functions are read.
- Call-note wording in `runner.py` still names the old competitors (Chargewise, Meterline) in some lines.

## Columns the loader uses when present

`sim_hidden_people.world_id` (the `pe_` id) and `sim_hidden_people.vendor_findable` (boolean) are filled when the table has
them. Without them, a person no vendor can find is left out of the build (the news still names a new finance leader, so
those are kept), and a hidden person has no `pe_` id for a simulated people search to hand back.
