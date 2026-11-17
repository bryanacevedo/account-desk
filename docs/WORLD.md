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

## What the build plants, and why

The release says nothing that makes some scenarios happen, so the build adds data and lets the desk's own rules decide
(decisions 71 to 75). Nothing sets a final state: no stage, suggestion, gap or signal is written by hand, and no scenario
is special-cased in code.

| Scenario | Planted | Decided by the desk |
|---|---|---|
| `champion_moved` | A champion is whoever championed a deal we won (`truth/deal_roles.csv`; the release's own `is_champion` flag is empty). On about 14% of days one of the desk's champions starts at a prospect, reported by the job-change feed and, 80% of the time, by a second source one to five days later (`world_load.champion_moves`, `second_report`; fixed by hash of the day and the signal). The second report is also added to the world's own job changes. | Two sources agreeing move the person; the `champion_moved` play needs them confirmed at the new company. |
| Blocked: not emailed in this country | Nothing: the email rules for Italy, Switzerland, Sweden, Denmark, Belgium, Austria, Norway, Finland, Portugal and Mexico are in the catalog for every mode (decision 72), and Mexico's is opt-out (decision 76). No country in the world is blocked, so this scenario has no one to show and the coverage gate reports it as not applicable (decision 76). | The contact gate's `region_blocked` reason, written as a committee gap, for a contact in a blocked country (Singapore in the desk's own build). |
| Consent required, basis required | Nothing: the world's own countries. | The same gate, with the rules above. |
| No rule: needs a region rule first | Nothing: the people the release gives no country (about 0.4%). | The gate treats no country as no rule (decision 75). |
| Supervised, a promotion | SDRs edit fewer drafts of the finance operations hiring and pricing change plays (`runner.UNEDITED_WORLD`, 88.5% unedited against 72%). | The Monday promotion check (50 drafts, 90% unedited, bounces under 2%, positive replies, complaint data) and the manager's click. |
| Every suggestion state, "came back after a not now", "set aside and still set aside" | The call-note plants of decision 62, placed on the signals where the world's first calls are (`runner.MORE_PLANTED_WORLD`, decision 74). Among them: the ERP plant (`runner.ERP`, a usage-in-the-ERP reason on pricing-change calls heard until 1 October, so its suggestion is opened, set aside and never heard again), and the e-invoicing reason on hiring-function calls until 15 September, which `runner.SPREAD_WORLD` then spreads to 95% of first calls from that date (web visits excepted) so the pattern lapses. | The pattern rule in `suggestions.py` and the Tuesday routine of people deciding. |

Which of these depend on the CRM: see decision 75. Legacy mode has none of these plants and none of the ten countries.

## What it ignores

- `truth/people.csv` `phone_dnc`, `phone_type`, `human_id` (a job mover keeps one LinkedIn profile, which the desk already uses to match them), and `is_champion` (empty in this release; see above).
- `deals.csv` deals of the `scheduled` era, `deal_roles.csv` except its champions of won history deals, `call_notes.csv`, `attendance.csv`, `customers.csv` churn dates in the rehearsal, `public/events.csv`.
- The legacy generator's extras: signals about companies outside the account list, the random rate tables. The world's signals are the whole supply, plus the second report of a job change and the champion moves above.
- Reply behaviour (`behavior.json` `reply`, `positive_reply`, `unsubscribe`): it is decided in `sim/recipients.py`, which is not part of this change, so replies still use the desk's own numbers. The `no_show` and `opportunity_from_meeting` functions are read.
- Call-note wording in `runner.py` still names the old competitors (Chargewise, Meterline) in some lines.

## Columns the loader uses when present

`sim_hidden_people.world_id` (the `pe_` id) and `sim_hidden_people.vendor_findable` (boolean) are filled when the table has
them. Without them, a person no vendor can find is left out of the build (the news still names a new finance leader, so
those are kept), and a hidden person has no `pe_` id for a simulated people search to hand back.

## The CRM half, replayed from the rehearsal's journal

With `WORLD=world` and a `world/journal.jsonl` holding steps whose `actor` is `account_desk`, `demo` serves the whole
build's CRM calls from those steps (`adapters/recorded.py`) and, at the end, fails with `JournalMismatch` if any step was
not used. Any difference also fails: a call the journal does not have next, or a different method, path, query,
idempotency key or body. `at` is not compared. With no `account_desk` step the build uses the simulated CRM as before.
`CRM=recorded` (path from `JOURNAL_PATH`, default `world/journal.jsonl`) does the same outside `demo`; it is refused with
`MODE=live` and `PUBLIC_DEMO`.

Each `account_desk` step the rehearsal writes: `actor`, `at`, `method`, `path` (no `/api/v1`), `status`, `answer`, and,
when the request had them, `query` (GET params), `idempotency_key` (the `idempotency-key` header) and `body`.
`RecordingCrm(inner, path)` writes this format around a `CrmDeskCrm`.

The replay also pins the database's time zone to America/Santo_Domingo (`db.pin_timezone`, decision 104): the journal was
recorded there, and the build's day boundaries follow the session zone, so a UTC Postgres would make other calls.
