# Layer review, 2026-11-11

A fresh reviewer that had not seen the build conversation read docs/SPEC.md and the code, and judged each layer Deep, Partial or Thin. Bryan asked for it to find layers that are not properly developed. LinkedIn and placement were the examples he had found; the reviewer was not told them. Its words, unedited apart from dashes. What has been done about it since is tracked in PROJECT-STATUS.md.

## Depth by layer (working tree as of 2026-11-11, uncommitted changes included)

| Layer | Depth | Evidence | What is missing |
|---|---|---|---|
| Signal ingest and resolution | Partial | `signals.py:ingest`, `resolve_account` (domain, subdomain, name), `_consider_move` + `person_moves`; CHECKs on `signals.evidence`; `views.signals_page`; Signals page has a "Not matched" tab | Only sources are sim (`adapters/sources.fetch` reads `sim_events`) and the signed webhook. `live.fetch_source` returns `[]`. No CSV import. The `auto_create_accounts` setting is seeded (`catalog.py`) but never read. Unknown types are counted and then dropped, with no row. Unmatched signals can't be acted on in the UI. No unit test covers resolution or move corroboration. |
| Account universe and data layer | Thin | Accounts, users, mailboxes, ICP and plays are only written by `seed/load.load_catalog`, which only `sim/runner.setup` calls | No import or CRM path to create accounts, users, mailboxes or domains. No CLI to bootstrap a live database. `accounts.parent_id` is read by the gate and trigger but nothing writes it (tests do). `is_champion` is set only by sim adapters (spec says it comes from won-opp contacts). No 90-day re-verify for people in open plays, and no firmographic refresh (22.9). |
| Scoring | Deep | `scoring.compute/rescore`, `score_history` at a move of 5 or more, `score_not_reproducible` monitor, `test_units` decay/convergence/tier/reproduce, account sheet breakdown, "Rising this week" view | Nothing material. |
| Plays: matching, holdout, state machine | Deep (thin tests) | `plays.match/propose/holdout_draw`, `ALLOWED` transitions, `COOLDOWN` written as holds, `expire_proposals`, `close_stale`; the DB partial unique index and a CHECK that the author can't launch; the play editor (`play_editor.py`, `PlayEditor.tsx`), tested | `trigger.exclude_lifecycles` is never read. 22.3 says a new sequence version gets a fresh watched batch, but `template_key` = `play:step` with no version. None of the time-based exits (`expired`, `no_meeting`, `no_opportunity`, `became_customer`, `nothing_approved`) has a test. |
| Research and brief | Partial | `outreach._research_facts` (cached by domain for 30 days), `write_brief` drops uncited findings; brief shown in the account sheet | Research is `SimResearch` only. The brief runs only on the `sim_llm` stand-in. No brief eval set (22.15). |
| Committee, people finding, verification | Partial | `build_committee` (persona match, people search, finder→verifier waterfall, channel-aware), `committee_gaps` shown in the UI, `reverify` job on send | All vendors are sim. A referral never becomes a person or an enrollment: `enrollments.via_referral` is never written. `_next_for_persona` only creates a "Find another …" task, not a proposed person. |
| Drafting and copy gate (email) | Deep | `copy_gate.check` covers spec 8 items 1-9 and 22.11, redraft once, `messages.attempts`, `_edit_checks` on person edits, ~10 unit tests, approval sheet shows failures and cited facts | Drafts run on the stand-in only. No labelled draft or copy-gate eval set (15, 22.15). |
| Approval and autonomy | Deep (gaps) | `approved_hash` + `message_send_guard` trigger, `maybe_auto_approve` (supervised 1-in-5 sample, autonomous tier B), `views.promotion_check` + manager-only promotion API, `plays.autonomy_watch` demotion | Demotion uses a 1-day bounce rate, not the play's last 200 sends (22.5). Auto-approve and demotion are untested. 22.16 says the manager's launch approval caps play spend per month: not implemented, the cost card is display-only. |
| Email sending | Deep | `sending.send_one` (row locks, gate, window, play-step watch, mailbox and domain caps under lock), trigger as last check, two-phase `send_provider`, `sweep_sending`/`reconcile_send`, RFC 8058 headers + `Feedback-ID` | Only `SimEmail` exists (no SMTP, Instantly or Smartlead). Spec 16 #8 (mailbox cap) is labelled [enforced], but there is no DB constraint or trigger, only Python. SPF, DKIM, DMARC and `blocklisted` are static seed values; no DNS or blocklist check job. `dmarc_policy` is never read. |
| Deliverability telemetry and health | Partial | `telemetry`, `mailbox_health` (14d/50-send bounce), `record_delivery_event` watched batch, `placement_tests` + `reply_rate_drops` (new, `tests/test_placement.py`), Inboxes page | Telemetry is sim (Postmaster-like only; no Yahoo FBL or SNDS). No UI to resume a paused play step (`/api/watch/.../resume` has no caller). The "capacity forecast" is a count of scheduled messages, not capacity over 10 business days. Mailbox bounce pause and watched-batch pause are untested. |
| LinkedIn channel | Thin | `outreach.due_steps` makes a `tasks` row titled "Connect with X"; `TaskRow` has a Profile link and a Done button; `replies.ingest(channel='linkedin')` only via webhook | No drafted connect note or message, no copy gate. `messages.channel` is never `linkedin`. No HeyReach adapter, and `users.heyreach_consent` is never read. `/api/tasks/{id}/done` writes no touch and no outcome (connection accepted, replied). Nothing stops email on LinkedIn engagement (spec 16 #20 is labelled [enforced]; there is no code). Not measured. |
| Call channel | Thin | Call task title includes the phone; sim phone waterfall in `research_job` | Gate not run when a call task is created. `person_reasons` is never called with `'call'`, so `phone` suppressions (do-not-call numbers) can never block. No outcome logging, no touch row, `rep_in_conversation` (22.19) absent, no measurement. |
| Replies | Deep (email) | `replies.ingest/stop_first/clean/rules_label/classify_job/act`, referral email checked verbatim, injection → review, SLA + `sla_check` escalation, 48-item live-recorded eval, multilingual unit tests, Reply sheet with relabel | No inbound mail adapter (only the signed webhook and the sim). Referral → task only (see committee). `left_company` extracts `new_company` but never raises a signal. 22.2 says the SDR resolves a positive reply and chooses whether colleagues resume or stop; there is no such choice, only the 3-day auto-resume. |
| Meetings and pipeline | Thin / Partial | `pipeline.book_meeting` (via the Reply sheet's "Meeting booked" button), `set_meeting_status` (rebook task), `opportunity_created` attribution + `converted`, `learn_from` quote check | No booking webhook (Calendly-shaped, spec 12). The button can't set a date (defaults to now+3 days). `/api/meetings/{id}/status` (held, no-show, cancelled, notes, learn) has no UI caller, and meetings in the account sheet aren't clickable. Opportunities are created only by `sim/runner.meetings_and_deals`. `opportunity_closed` has no caller outside tests, so won/lost never happens in a running desk. |
| Attribution and measurement | Partial | `views.results/plays_page/signal_performance`, `stats.wilson/newcombe/lift_report` (tested against published values), pooled lift, SLA median, cost per meeting | "Contacted" and "signal to first touch" count only `touches` out, which only email sends write, so LinkedIn/call-only plays and research-stage plays show 0 contacted. No split by channel. No weight suggestion (spec 17). Holdout meetings per signal type are computed but not shown. No cost per opportunity. |
| CRM sync | Thin | `crm_outbox` writes (activity, task, opt_out, meeting), `crm_push` with backoff and an alert when dead, `crm_outbox_stuck` monitor | `Crm` protocol is push-only, `SimCrm` only. `crm_sync` reads nothing (owners, lifecycle, opps, contacts): it only turns old closed-lost opps into signals. No contact-create writes. Retry and dead-letter paths are untested. |
| Compliance and privacy | Deep (gaps) | Footer and opt-out line enforced on edit; one-click endpoint acts on POST only (tested); region rules and `contact_basis` in the trigger (tested); `privacy.erase` (tested); `email_hash` suppression | Every play's legitimate-interest basis is the hard-coded `'LIA-2026-07'` in `create_play`/seed, auto-recorded with `recorded_by` null. No UI or API to add suppressions or holds. Mailto unsubscribe is not processed. LinkedIn-only plays still drop consent-country people, because `_enrollable` checks channel `email`. |
| Spend | Partial / Deep | `spend.paid_call` ledger + `adapter_calls`, caps via `OverBudget` + alert, `spend_over_cap` and `paid_call_unledgered` monitors, Health budgets | No per-play monthly cap from launch approval (22.16). |
| Monitors, alerts, Slack | Partial | 13 monitors + `monitors_ran` self-check, `/api/health`, alerts stored as rows, `deliver_alert` | Slack is `SimChat` only, and `SLACK_BOT_TOKEN` is never used. Spec 16 #21 asks "last cycle is recent"; nothing checks that `monitors_ran` is fresh. #20 has no monitor. The flow test exempts `source_silent` and `alerts_undelivered`. |
| Jobs and operations | Deep | `jobs.py` SKIP LOCKED, dedupe, reaper (tested), scheduler with dedupe keys | Nothing material. |
| Auth and roles | Partial / Deep | `current_user` with Cloudflare Access JWT verification, `need()` role checks, SDR ownership checks, money hidden from SDRs (tested), HMAC webhooks with a 5-minute timestamp | Replay protection is timestamp plus per-payload idempotency, with no nonce store. No user or role administration. Access is unverified against a real app (status doc says so). |
| AI and evals | Partial | `llm.run` live/recorded/sim, schema outputs, classify eval replayed in CI with a prompt-hash check | Brief, draft, suggest_reply and extract have no recordings or eval sets. `EVALS_STRICT` is parsed but never read. |
| Web app screens | Partial | All 11 pages from spec 18 exist; write actions: decide proposal, approve/edit/reject, handle/relabel reply, task done, play create/edit/launch/promote, kill switch, signal weights | No UI for: meeting outcome or notes, unknown-send resolution, watched-batch resume, erasure, suppressions/holds, ICP edit, mailbox/domain setup, unmatched-signal resolution, referral promotion, logging a call or LinkedIn outcome. The account sheet shows "Emails" only (no calendar or tasks per person). The Results funnel is labelled "Emailed". |
| MCP server, INTEGRATIONS.md | Thin (absent) | Neither exists (spec 20, 22.17) | Everything. |
| Live vendor adapters (all) | Thin | `adapters/live.adapters()` returns the sim set plus a note | Every vendor. |

**Uniformity:** the email path (scoring → play → draft → copy gate → approval → send trigger → reply) is deep, enforced in the database and tested. Everything that leaves that path drops to Thin: LinkedIn, calls, meetings after booking, opportunities, CRM read, referral follow-through, and the bootstrap of a real (non-sim) database. Those pieces have tables and enum values but no writers, UI or measurement. Several things the spec labels "[enforced]" (#8 mailbox cap, #20 cross-channel) are not enforced by the database.

## Most important gaps, ranked by harm to a real team

1. **Pipeline never closes outside the simulator (spec 12, 13, 22.19).** Opportunities are created only by `sim/runner`. `opportunity_closed` has no runtime caller, and `crm_sync` reads nothing from the CRM. In a live deployment there would be no sourced or influenced pipeline. No account would move to `converted` or have its lifecycle changed to `customer`/`open_opp` by the CRM, and every `meeting`-state play would time out as `no_opportunity`. The Results page's headline numbers would be zero, and the lifecycle exclusions (customer, open opp) would rest on stale seed data.

2. **LinkedIn and calls are tasks with a title and a Done button (spec 11, 12 "Cross-channel", 16 #20, 22.10, 22.19).** No drafted text, no copy check, no gate at task creation (phone suppression is unreachable), no touch or outcome when done, no connection-accepted or LinkedIn-reply logging from the UI, and no HeyReach adapter. A team running mixed sequences can't stop email after LinkedIn engagement, can't record a do-not-call number, and sees these plays as 0 "contacted". The status doc already lists this as next; it is the widest gap across the layers.

3. **Meetings can't be worked after booking (spec 12, 18 Account page).** The held/no-show/cancel/notes endpoint has no UI. "Meeting booked" can't take a date (defaults to +3 days), and there is no booking webhook. So "learning from calls", engagement scoring (meetings held), rebook tasks and the `meeting → engaged` exit only happen in the sim.

4. **There is no way to stand up a real desk (spec 22.9 account universe, 13 CRM read, 18 Settings).** Users, mailboxes, sending domains, ICP, personas, plays and accounts come only from `load_catalog` inside the sim setup. There's no import, no settings writes beyond weights and the kill switch, and `parent_id`/`is_champion` are never populated from data. A team would need to write SQL by hand to start.

5. **Measurement is blind to every channel but email (spec 17, 22.8).** "Contacted", signal-to-first-touch, the `slow_first_touch` monitor and the cooldown all key off `touches` direction `out`, and only `sending.record_result` writes those. Research-stage plays, where the SDR writes the outreach, and LinkedIn/call plays look like zero outreach, and `slow_first_touch` would flag them. The weight suggestion and the per-type holdout comparison promised in spec 17 aren't shown.

6. **Referrals and job changes stop at a task (spec 12 Actions, 22.9).** A referral reply makes a "Referred to X" task. No person is created, nothing is proposed, `via_referral` is never written, and the UI tells the user "the desk will look it up", which no code does. `left_company` with a named new company raises no signal, so the champion loop the spec leans on only works from sim signals.

7. **Deliverability inputs are static (spec 11 Mailboxes, 22.5).** SPF, DKIM, DMARC, alignment and blocklist status are seed values with no DNS or blocklist job. Telemetry and placement are sim-only. A paused play step and an unknown send can only be cleared through the API (no UI). A real domain that loses DKIM would keep sending.

8. **Some "[enforced]" guarantees are code paths, not database rules (spec 16 #8, #20, #21).** The mailbox daily cap is a Python count under row locks (sound, but not a constraint). #20 has no enforcement and no monitor. #21 doesn't check that the monitor cycle is recent. The spec's list of what can't happen overstates what the database refuses.

## Could not verify

- Whether the UI renders correctly or every button works end to end. No browser was run; judged from source only.
- Whether `_live` model calls work for brief, draft or extract (only classify has recordings).
- The Cloudflare Access JWT path against a real Access app (the status doc says it is unrun).
- Whether the play editor cost card's worst-case figures match real vendor pricing (they come from `spend.RATES`).
- Whether the full suite passes on the current uncommitted tree. Tests were not run (read-only review); PROJECT-STATUS reports a 79-pass run that predates the current changes.
- Whether the Render demo matches this tree.


---

# Second layer review, 2026-11-11 (after the layers were deepened)

The same brief, a new fresh reviewer, at commit 2382d2c. Its words, unedited apart from dashes.

## Depth by layer (working tree as of 2026-11-11, uncommitted changes included)
43	
44	| Layer | Depth | Evidence | What is missing |
45	|---|---|---|---|
46	| Signal ingest and resolution | Partial | `signals.py:ingest`, `resolve_account` (domain, subdomain, name), `_consider_move` + `person_moves`; CHECKs on `signals.evidence`; `views.signals_page`; Signals page has a "Not matched" tab | Only sources are sim (`adapters/sources.fetch` reads `sim_events`) and the signed webhook. `live.fetch_source` returns `[]`. No CSV import. The `auto_create_accounts` setting is seeded (`catalog.py`) but never read. Unknown types are counted and then dropped, with no row. Unmatched signals can't be acted on in the UI. No unit test covers resolution or move corroboration. |
47	| Account universe and data layer | Thin | Accounts, users, mailboxes, ICP and plays are only written by `seed/load.load_catalog`, which only `sim/runner.setup` calls | No import or CRM path to create accounts, users, mailboxes or domains. No CLI to bootstrap a live database. `accounts.parent_id` is read by the gate and trigger but nothing writes it (tests do). `is_champion` is set only by sim adapters (spec says it comes from won-opp contacts). No 90-day re-verify for people in open plays, and no firmographic refresh (22.9). |
48	| Scoring | Deep | `scoring.compute/rescore`, `score_history` at a move of 5 or more, `score_not_reproducible` monitor, `test_units` decay/convergence/tier/reproduce, account sheet breakdown, "Rising this week" view | Nothing material. |
49	| Plays: matching, holdout, state machine | Deep (thin tests) | `plays.match/propose/holdout_draw`, `ALLOWED` transitions, `COOLDOWN` written as holds, `expire_proposals`, `close_stale`; the DB partial unique index and a CHECK that the author can't launch; the play editor (`play_editor.py`, `PlayEditor.tsx`), tested | `trigger.exclude_lifecycles` is never read. 22.3 says a new sequence version gets a fresh watched batch, but `template_key` = `play:step` with no version. None of the time-based exits (`expired`, `no_meeting`, `no_opportunity`, `became_customer`, `nothing_approved`) has a test. |
50	| Research and brief | Partial | `outreach._research_facts` (cached by domain for 30 days), `write_brief` drops uncited findings; brief shown in the account sheet | Research is `SimResearch` only. The brief runs only on the `sim_llm` stand-in. No brief eval set (22.15). |
51	| Committee, people finding, verification | Partial | `build_committee` (persona match, people search, finder→verifier waterfall, channel-aware), `committee_gaps` shown in the UI, `reverify` job on send | All vendors are sim. A referral never becomes a person or an enrollment: `enrollments.via_referral` is never written. `_next_for_persona` only creates a "Find another …" task, not a proposed person. |
52	| Drafting and copy gate (email) | Deep | `copy_gate.check` covers spec 8 items 1-9 and 22.11, redraft once, `messages.attempts`, `_edit_checks` on person edits, ~10 unit tests, approval sheet shows failures and cited facts | Drafts run on the stand-in only. No labelled draft or copy-gate eval set (15, 22.15). |
53	| Approval and autonomy | Deep (gaps) | `approved_hash` + `message_send_guard` trigger, `maybe_auto_approve` (supervised 1-in-5 sample, autonomous tier B), `views.promotion_check` + manager-only promotion API, `plays.autonomy_watch` demotion | Demotion uses a 1-day bounce rate, not the play's last 200 sends (22.5). Auto-approve and demotion are untested. 22.16 says the manager's launch approval caps play spend per month: not implemented, the cost card is display-only. |
54	| Email sending | Deep | `sending.send_one` (row locks, gate, window, play-step watch, mailbox and domain caps under lock), trigger as last check, two-phase `send_provider`, `sweep_sending`/`reconcile_send`, RFC 8058 headers + `Feedback-ID` | Only `SimEmail` exists (no SMTP, Instantly or Smartlead). Spec 16 #8 (mailbox cap) is labelled [enforced], but there is no DB constraint or trigger, only Python. SPF, DKIM, DMARC and `blocklisted` are static seed values; no DNS or blocklist check job. `dmarc_policy` is never read. |
55	| Deliverability telemetry and health | Partial | `telemetry`, `mailbox_health` (14d/50-send bounce), `record_delivery_event` watched batch, `placement_tests` + `reply_rate_drops` (new, `tests/test_placement.py`), Inboxes page | Telemetry is sim (Postmaster-like only; no Yahoo FBL or SNDS). No UI to resume a paused play step (`/api/watch/.../resume` has no caller). The "capacity forecast" is a count of scheduled messages, not capacity over 10 business days. Mailbox bounce pause and watched-batch pause are untested. |
56	| LinkedIn channel | Thin | `outreach.due_steps` makes a `tasks` row titled "Connect with X"; `TaskRow` has a Profile link and a Done button; `replies.ingest(channel='linkedin')` only via webhook | No drafted connect note or message, no copy gate. `messages.channel` is never `linkedin`. No HeyReach adapter, and `users.heyreach_consent` is never read. `/api/tasks/{id}/done` writes no touch and no outcome (connection accepted, replied). Nothing stops email on LinkedIn engagement (spec 16 #20 is labelled [enforced]; there is no code). Not measured. |
57	| Call channel | Thin | Call task title includes the phone; sim phone waterfall in `research_job` | Gate not run when a call task is created. `person_reasons` is never called with `'call'`, so `phone` suppressions (do-not-call numbers) can never block. No outcome logging, no touch row, `rep_in_conversation` (22.19) absent, no measurement. |
58	| Replies | Deep (email) | `replies.ingest/stop_first/clean/rules_label/classify_job/act`, referral email checked verbatim, injection → review, SLA + `sla_check` escalation, 48-item live-recorded eval, multilingual unit tests, Reply sheet with relabel | No inbound mail adapter (only the signed webhook and the sim). Referral → task only (see committee). `left_company` extracts `new_company` but never raises a signal. 22.2 says the SDR resolves a positive reply and chooses whether colleagues resume or stop; there is no such choice, only the 3-day auto-resume. |
59	| Meetings and pipeline | Thin / Partial | `pipeline.book_meeting` (via the Reply sheet's "Meeting booked" button), `set_meeting_status` (rebook task), `opportunity_created` attribution + `converted`, `learn_from` quote check | No booking webhook (Calendly-shaped, spec 12). The button can't set a date (defaults to now+3 days). `/api/meetings/{id}/status` (held, no-show, cancelled, notes, learn) has no UI caller, and meetings in the account sheet aren't clickable. Opportunities are created only by `sim/runner.meetings_and_deals`. `opportunity_closed` has no caller outside tests, so won/lost never happens in a running desk. |
60	| Attribution and measurement | Partial | `views.results/plays_page/signal_performance`, `stats.wilson/newcombe/lift_report` (tested against published values), pooled lift, SLA median, cost per meeting | "Contacted" and "signal to first touch" count only `touches` out, which only email sends write, so LinkedIn/call-only plays and research-stage plays show 0 contacted. No split by channel. No weight suggestion (spec 17). Holdout meetings per signal type are computed but not shown. No cost per opportunity. |
61	| CRM sync | Thin | `crm_outbox` writes (activity, task, opt_out, meeting), `crm_push` with backoff and an alert when dead, `crm_outbox_stuck` monitor | `Crm` protocol is push-only, `SimCrm` only. `crm_sync` reads nothing (owners, lifecycle, opps, contacts): it only turns old closed-lost opps into signals. No contact-create writes. Retry and dead-letter paths are untested. |
62	| Compliance and privacy | Deep (gaps) | Footer and opt-out line enforced on edit; one-click endpoint acts on POST only (tested); region rules and `contact_basis` in the trigger (tested); `privacy.erase` (tested); `email_hash` suppression | Every play's legitimate-interest basis is the hard-coded `'LIA-2026-07'` in `create_play`/seed, auto-recorded with `recorded_by` null. No UI or API to add suppressions or holds. Mailto unsubscribe is not processed. LinkedIn-only plays still drop consent-country people, because `_enrollable` checks channel `email`. |
63	| Spend | Partial / Deep | `spend.paid_call` ledger + `adapter_calls`, caps via `OverBudget` + alert, `spend_over_cap` and `paid_call_unledgered` monitors, Health budgets | No per-play monthly cap from launch approval (22.16). |
64	| Monitors, alerts, Slack | Partial | 13 monitors + `monitors_ran` self-check, `/api/health`, alerts stored as rows, `deliver_alert` | Slack is `SimChat` only, and `SLACK_BOT_TOKEN` is never used. Spec 16 #21 asks "last cycle is recent"; nothing checks that `monitors_ran` is fresh. #20 has no monitor. The flow test exempts `source_silent` and `alerts_undelivered`. |
65	| Jobs and operations | Deep | `jobs.py` SKIP LOCKED, dedupe, reaper (tested), scheduler with dedupe keys | Nothing material. |
66	| Auth and roles | Partial / Deep | `current_user` with Cloudflare Access JWT verification, `need()` role checks, SDR ownership checks, money hidden from SDRs (tested), HMAC webhooks with a 5-minute timestamp | Replay protection is timestamp plus per-payload idempotency, with no nonce store. No user or role administration. Access is unverified against a real app (status doc says so). |
67	| AI and evals | Partial | `llm.run` live/recorded/sim, schema outputs, classify eval replayed in CI with a prompt-hash check | Brief, draft, suggest_reply and extract have no recordings or eval sets. `EVALS_STRICT` is parsed but never read. |
68	| Web app screens | Partial | All 11 pages from spec 18 exist; write actions: decide proposal, approve/edit/reject, handle/relabel reply, task done, play create/edit/launch/promote, kill switch, signal weights | No UI for: meeting outcome or notes, unknown-send resolution, watched-batch resume, erasure, suppressions/holds, ICP edit, mailbox/domain setup, unmatched-signal resolution, referral promotion, logging a call or LinkedIn outcome. The account sheet shows "Emails" only (no calendar or tasks per person). The Results funnel is labelled "Emailed". |
69	| MCP server, INTEGRATIONS.md | Thin (absent) | Neither exists (spec 20, 22.17) | Everything. |
70	| Live vendor adapters (all) | Thin | `adapters/live.adapters()` returns the sim set plus a note | Every vendor. |
71	
72	**Uniformity:** the email path (scoring → play → draft → copy gate → approval → send trigger → reply) is deep, enforced in the database and tested. Everything that leaves that path drops to Thin: LinkedIn, calls, meetings after booking, opportunities, CRM read, referral follow-through, and the bootstrap of a real (non-sim) database. Those pieces have tables and enum values but no writers, UI or measurement. Several things the spec labels "[enforced]" (#8 mailbox cap, #20 cross-channel) are not enforced by the database.
73	
74	## Most important gaps, ranked by harm to a real team
75	
76	1. **Pipeline never closes outside the simulator (spec 12, 13, 22.19).** Opportunities are created only by `sim/runner`. `opportunity_closed` has no runtime caller, and `crm_sync` reads nothing from the CRM. In a live deployment there would be no sourced or influenced pipeline. No account would move to `converted` or have its lifecycle changed to `customer`/`open_opp` by the CRM, and every `meeting`-state play would time out as `no_opportunity`. The Results page's headline numbers would be zero, and the lifecycle exclusions (customer, open opp) would rest on stale seed data.
77	
78	2. **LinkedIn and calls are tasks with a title and a Done button (spec 11, 12 "Cross-channel", 16 #20, 22.10, 22.19).** No drafted text, no copy check, no gate at task creation (phone suppression is unreachable), no touch or outcome when done, no connection-accepted or LinkedIn-reply logging from the UI, and no HeyReach adapter. A team running mixed sequences can't stop email after LinkedIn engagement, can't record a do-not-call number, and sees these plays as 0 "contacted". The status doc already lists this as next; it is the widest gap across the layers.
79	
80	3. **Meetings can't be worked after booking (spec 12, 18 Account page).** The held/no-show/cancel/notes endpoint has no UI. "Meeting booked" can't take a date (defaults to +3 days), and there is no booking webhook. So "learning from calls", engagement scoring (meetings held), rebook tasks and the `meeting → engaged` exit only happen in the sim.
81	
82	4. **There is no way to stand up a real desk (spec 22.9 account universe, 13 CRM read, 18 Settings).** Users, mailboxes, sending domains, ICP, personas, plays and accounts come only from `load_catalog` inside the sim setup. There's no import, no settings writes beyond weights and the kill switch, and `parent_id`/`is_champion` are never populated from data. A team would need to write SQL by hand to start.
83	
84	5. **Measurement is blind to every channel but email (spec 17, 22.8).** "Contacted", signal-to-first-touch, the `slow_first_touch` monitor and the cooldown all key off `touches` direction `out`, and only `sending.record_result` writes those. Research-stage plays, where the SDR writes the outreach, and LinkedIn/call plays look like zero outreach, and `slow_first_touch` would flag them. The weight suggestion and the per-type holdout comparison promised in spec 17 aren't shown.
85	
86	6. **Referrals and job changes stop at a task (spec 12 Actions, 22.9).** A referral reply makes a "Referred to X" task. No person is created, nothing is proposed, `via_referral` is never written, and the UI tells the user "the desk will look it up", which no code does. `left_company` with a named new company raises no signal, so the champion loop the spec leans on only works from sim signals.
87	
88	7. **Deliverability inputs are static (spec 11 Mailboxes, 22.5).** SPF, DKIM, DMARC, alignment and blocklist status are seed values with no DNS or blocklist job. Telemetry and placement are sim-only. A paused play step and an unknown send can only be cleared through the API (no UI). A real domain that loses DKIM would keep sending.
89	
90	8. **Some "[enforced]" guarantees are code paths, not database rules (spec 16 #8, #20, #21).** The mailbox daily cap is a Python count under row locks (sound, but not a constraint). #20 has no enforcement and no monitor. #21 doesn't check that the monitor cycle is recent. The spec's list of what can't happen overstates what the database refuses.
91	
92	## Could not verify
93	
94	- Whether the UI renders correctly or every button works end to end. No browser was run; judged from source only.
95	- Whether `_live` model calls work for brief, draft or extract (only classify has recordings).
96	- The Cloudflare Access JWT path against a real Access app (the status doc says it is unrun).
97	- Whether the play editor cost card's worst-case figures match real vendor pricing (they come from `spend.RATES`).
98	- Whether the full suite passes on the current uncommitted tree. Tests were not run (read-only review); PROJECT-STATUS reports a 79-pass run that predates the current changes.
99	- Whether the Render demo matches this tree.
100	# Outbound Desk: project status
101	
102	**Updated:** 2026-11-11. **Spec:** `docs/SPEC.md` (sections 1 to 21, then 22 with every review decision, which wins where they differ). **Decisions:** `docs/DECISIONS.md`, 1 to 14. **Working name**, Bryan's to change.
103	
104	## Where it stands
105	
106	v1 is built end to end on simulated vendors. **Public** at https://github.com/bryanacevedo/outbound-desk since 2026-11-11 (Bryan: keep the name, publish). CI green on the first push (lint, the suite on Postgres 18, the web build). **Live demo** at https://outbound-desk.onrender.com since 2026-11-11 (Render free plan, service `outbound-desk`, Docker with Postgres inside; the 60-day simulation is built into the image, so a start or a wake takes seconds; checked on the live link: every page 200 in under 0.7 s). The first deploy failed because the simulation ran at start and took longer than Render's port wait; fixed by building it into the image.
107	
108	Checked on 2026-11-11 by running them:
109	
110	- `pytest` on real Postgres 18: 107 passed on 2026-11-11 after the layer work (79 at first publish) (77 then, plus 2 eval replays) in about 5 seconds, including a 21-day simulation of the whole desk (140 accounts) followed by checks of every promise against what happened, and 9 regression tests for the first code review's blocking findings.
111	- `ruff check src tests`: clean. `tsc --noEmit` and `vite build`: clean.
112	- `make demo`: 460 invented accounts, 60 simulated days in about 25 seconds; opens on 2026-11-11 with work waiting for each SDR.
113	- Every page walked in the browser pane at 1440 wide: Today, Accounts and the account sheet, Approvals and the email sheet. Not yet walked by a fresh reviewer against `docs/DESIGN-CHECKLIST.md`, and not yet checked at phone width.
114	
115	## At production size (measured 2026-11-11)
116	
117	5,000 accounts, 30 simulated days: 71 s, no dead jobs. Then 2,008,711 signals: every page under 50 ms except Signals (88 to 165 ms), rescoring 10 ms an account and 0.8 s per batch of 500, monitors 50 ms or less. Signals and Results were 2.7 s and 2.4 s before migration 0004's `signals_type_recent` index and the split feed query. The `slow_first_touch` monitor found 38 accounts past their play's time limit: four SDRs cannot approve fast enough for 5,000 accounts.
118	
119	## Reviews
120	
121	- Spec: goldfish review against its sources and the build checklist, a real-world review against how strong teams run signal-based outbound in 2026, and a re-review after the blockers were fixed. 49 findings, all resolved in spec section 22.
122	- Code: one fresh reviewer, verdict "do not ship" with 11 blocking findings (double-send on a crash mid-send, jobs stranded in running, plays that could stay open forever, a customer turned back into a prospect by a lost expansion deal, a spoofable login header, a default webhook secret, failed drafts approvable unchanged, wrong influenced attribution, and others). All 11 fixed with regression tests, plus most non-blocking items (commit `9b055c4`). A second code review has not run.
123	
124	- Design: one fresh hands-on reviewer drove every page and panel at 1440 and 375 wide (2026-11-11): "not ready to show", 3 blockers (phone rows, broken draft grammar, panels scrolling sideways), 14 major (explanatory sentences, jargon, numbers shown twice, two names for one thing, decorative dots, phone navigation, Approve and Reject behaving differently, losing the tab on Back, team work labelled as yours) and nits. All blockers and majors fixed and checked at both widths; checking at 375 also found a tab strip that collapsed to 1px and a page that grew to 402px wide, both fixed. Bryan's own review: "best design work so far", with comments to come.
125	- Found by the flow test during the fixes: a resume after an out-of-office brought a colleague's first email forward to the same day; a pause now keeps each person's planned time.
126	
127	## Proven and not proven
128	
129	**Proven on simulated vendors:** scoring and its reproduction, play matching and the comparison group, research and the buying committee, drafting with the copy checks, approvals and autonomy stages, the account calendar and send windows, mailbox and domain health, the database trigger behind every send, stop-first replies, reply cleaning and rules in five languages, meetings, attribution, the statistics (Wilson and Newcombe checked against published values), signed webhooks, one-click unsubscribe, erasure, the job queue and its reaper, the monitors.
130	
131	**Not proven:**
132	
133	- Reply labelling is measured on live Claude answers (2026-11-11, `evals/REPLIES.md`): 45 of 48 exact, 47 of 48 acceptable, rules alone 12, injection flagged, no invented referral emails, $0.25. The set is 48 author-written replies: a regression guard, not a benchmark. Brief, drafts and call-note extraction still run on the stand-in only. The key lives in `.env` (gitignored, 600).
134	- No live vendor adapter (people search, finder, verifier, phone, research, mail provider, telemetry, CRM, Slack). Contracts only.
135	- No MCP server yet (in the spec, section 20).
136	- No eval sets yet for the brief, drafts or call notes (spec 22.15).
137	- Real login only through Cloudflare Access token verification, which has not been run against a real Access app.
138	- Region rules are a starting point. Counsel to confirm.
139	- Contention from several servers at once (one process was measured).
140	
141	## Next
142	
143	The layer review (`docs/LAYER-REVIEW.md`, 2026-11-11) found the email path deep and most of what sits off it thin. Done since: placement, LinkedIn and calls, the person sheet. Remaining, in the review's order of harm:
144	
145	1. Pipeline outside the simulator: opportunities only come from the simulator and nothing closes them in a running desk; the CRM is push-only.
146	2. Meetings after booking: no date on booking, no held or no-show or notes in the UI, no booking webhook.
147	3. Standing up a real desk: users, mailboxes, domains, ICP, plays and accounts only come from the demo seed.
148	4. Referrals and job changes stop at a task.
149	5. Deliverability inputs are static: SPF, DKIM, DMARC and blocklists are seed values with no check job.
150	6. Evals for drafts and briefs with live calls; the MCP server; live vendor adapters; a second fresh code review.
151	
152	## Done since the first review (2026-11-11)
153	
154	- Play editor: GTM writes a play with a live preview of matching accounts and a worst-case cost card, saved as a draft; a manager who did not write it launches it. Checked in the browser.
155	- Plays with no email step activate directly; tested end to end.
156	- Inbox placement (decision 15): weekly seed tests per mailbox at Gmail and Outlook hold or pause a mailbox, a missing test counts as unknown, and a mailbox that goes quiet next to its peers raises an alert. Shown on Inboxes as "Where mail lands". 4 tests. The 0001 table that was never written to is replaced.
157	- LinkedIn and calls (decision 16): drafted notes through the copy checks, sent through the send guard, every outcome a touch, LinkedIn replies as replies, guarantee 20 in the trigger, a monitor for it, results by channel on Results. 16 tests. Checked in the browser: a note marked sent shows on the person's history and LinkedIn row.
158	- People open a person sheet from an account: how to reach them, their plays, and one history across email, LinkedIn, calls and signals.
159	- Icons within the Instrument identity (status icons in ink, green for healthy, amber and red only where someone must act); relative times spelled out ("2 days ago"), Bryan's call.
160	- The flaky monitor test was the slow-first-touch alert catching late approvals by simulated SDRs, which is its job; the test now fails only when a play is stuck inside the desk, and that found a real one (decision 17). Simulator picks now use its seeded generator instead of SQL `random()`.
161	# Outbound Desk
162	
163	[![CI](https://github.com/bryanacevedo/outbound-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/bryanacevedo/outbound-desk/actions/workflows/ci.yml)
164	
165	Outbound Desk runs signal-based, account-based outbound for a B2B sales team. It watches for the moments a company that fits your customer profile shows it may need you (a new finance leader, a pricing change, hiring for the team you serve, a past champion joining), decides which accounts are worth working this week and why, finds the people who buy there, drafts outreach grounded in what actually happened at that company, has an SDR approve it, sends it from healthy inboxes at a human pace, and handles every reply through to a meeting and pipeline. It measures which signals turn into meetings against a comparison group nobody contacted.
166	
167	It is built for a small team that would rather write to 40 companies at the right moment than to 4,000 at random.
168	
169	**[Try the live demo](https://outbound-desk.onrender.com).** Pick who you are acting as in the sidebar (an SDR, the sales manager, or GTM engineering). The company, its accounts, people and vendors are all invented, and every vendor is simulated. If it has been idle, the first load takes about a minute. Read "What is real and what is simulated" before trusting any number in it.
170	
171	## The rules it is built on
172	
173	Autonomous "AI SDRs" mostly failed in 2025 and 2026: shallow or invented personalization, burned sending domains, bad data underneath. The teams getting results use signals plus fit to choose accounts, let AI research and draft, and keep a person on the send decision. Outbound Desk takes that as its design:
174	
175	| People | AI | Code |
176	|---|---|---|
177	| Decide the ideal customer, the plays, which accounts to work | Reads the facts about a company and writes a brief, citing each fact | Scores accounts, matches plays, draws the comparison group |
178	| Approve, edit or write every first email | Drafts each email as sentences, each claim tied to a fact id | Checks every citation, every number and every name against the facts |
179	| Answer every positive reply, book meetings, make the calls | Labels a reply from a fixed list and pulls out dates and referrals | Stops the sequence the moment a reply lands, before anyone reads it |
180	| Change weights and plays when results say so | Pulls objections and competitors out of call notes | Counts which signals and plays produce meetings, against the comparison group |
181	
182	Three more rules came from running outbound in production:
183	
184	- **Act on tracking data, never cite it.** Website visits, research intent and product sign-ups can trigger a play, but the drafter never sees them and the copy check fails any email that cites one. Buyers read that as surveillance.
185	- **Make the bad state impossible, and watch for what cannot be.** A send to a suppressed address, a holdout account or a message edited after approval is refused by a Postgres trigger, so no bug in the app can do it. Promises about time (sent inside the recipient's hours, hot replies answered on time, every source ran) are monitors that alert.
186	- **Autonomy is earned per play.** A play moves from "SDR writes" to "desk drafts, SDR approves" to "SDR approves first emails" only after 50 approvals with 90% unedited, no complaint, low bounces, and known complaint data for every sending domain. A manager approves each step.
187	
188	## What it does
189	
190	- **Signals.** Seventeen signal types, each with a written reason it matters, a weight and a half-life. Sources are adapters (job postings, funding, job changes, website visits, intent, reviews, technology changes, social engagement, product sign-ups, the CRM, a signed webhook). Every source run is recorded, so a silent source shows up.
191	- **Scoring.** Fit from a versioned ideal customer profile, intent from decayed signals with a bonus when different kinds of signal agree, engagement from replies and meetings. Every stored score keeps its inputs and must reproduce from them.
192	- **Plays.** Six shipped plays, each a hypothesis with a trigger, the people to reach, a sequence and an angle. A deterministic share of matched accounts goes to a comparison group that is never contacted.
193	- **The buying committee.** Up to three people per account by role (finance leader, controller, revenue operations, data), found through a people search, emails found and verified, phones found for call steps, all charged to a ledger in each vendor's own unit. Gaps are named ("Email in Germany needs consent first").
194	- **Drafting and the copy checks.** Code checks every draft: citations exist, numbers and proper names appear in a cited fact, it opens with the person's first name, length fits the step, no banned phrases, no long dashes, no links in a first email, not a near copy of a colleague's email, no private signal. A failed draft is rewritten once, then goes to the SDR.
195	- **Sending.** An account calendar staggers colleagues two business days apart. Sends land inside the recipient's own working hours, skip public holidays, ramp each mailbox, cap each domain, and pause a mailbox at a 2% bounce rate or any complaint. Every email carries the sender's postal address, a plain opt-out and RFC 8058 one-click unsubscribe headers; EU and UK recipients also get a privacy notice link.
196	- **Replies.** Stop first. Then clean the reply (quoted history, signatures, legal footers, so an "unsubscribe" in a footer opts nobody out), label it with rules first and the model second, and act: hot replies go to the owner with a deadline and a suggested answer, out-of-office pauses until the return date, referrals become tasks, not-now becomes a hold until the date given. Opt-outs work in five languages.
197	- **Meetings and pipeline.** Meetings stop the account's sequences. Opportunities are attributed as sourced or influenced. Call notes, once a person marks them worth learning from, become quotes grouped by play and signal.
198	- **Results.** A funnel from signal to meeting, meeting rate per signal type, and the difference from the comparison group with a Newcombe interval. Below the sample size needed to tell a difference, the page says how many accounts are still needed instead of showing a number.
199	- **Health.** Monitors, background jobs, the CRM outbox, alerts and spend against each vendor's monthly cap, plus one button that stops all sending.
200	
201	## How it fits together
202	
203	```mermaid
204	flowchart LR
205	  S[Signal sources] --> I[Ingest: resolve by domain, keep evidence]
206	  I --> SC[Score: fit, intent, engagement]
207	  SC --> M{Play matches and account gate passes}
208	  M -->|comparison group| H[Held out, measured, never contacted]
209	  M --> P[Proposed to the SDR]
210	  P -->|accepted| R[Research and brief, buying committee, verified emails]
211	  R --> D[Drafts, then the copy checks]
212	  D --> A[SDR approves]
213	  A --> C[Account calendar, send window, healthy mailbox]
214	  C --> G{Contact gate and the database trigger}
215	  G --> X[Sent]
216	  X --> RP[Reply: stop first, clean, label, act]
217	  RP --> MT[Meeting, opportunity]
218	  MT --> RS[Results by signal and play]
219	  RS -.->|SDRs and GTM adjust weights and plays| SC
220	```
221	
222	Python 3.13, FastAPI and Postgres 18 with plain SQL in numbered migrations. A job queue in Postgres claimed with `FOR UPDATE SKIP LOCKED`. React and Vite for the web app, served by the API. Model calls go through one function with structured outputs, record and replay, and a deterministic stand-in for the demo.
223	
224	The full behaviour is in [docs/SPEC.md](docs/SPEC.md), written and reviewed by two fresh reviewers before any code (one against its sources, one against how strong teams run outbound today; 49 findings, all resolved in section 22). Decisions are in [docs/DECISIONS.md](docs/DECISIONS.md).
225	
226	## Run it
227	
228	You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 26 and Postgres 18 installed (the scripts start a private Postgres in `.data/`).
229	
230	```bash
231	make setup
232	```
233	
234	```bash
235	make demo
236	```
237	
238	That builds an invented company with 460 accounts, simulates 60 days of signals, SDRs, buyers and vendors (about 30 seconds), and serves the desk at http://localhost:8800. Pick who you are acting as in the sidebar. "Move a day ahead" runs the world forward a day.
239	
240	```bash
241	make test
242	```
243	
244	The tests run on real Postgres, including a 21-day simulation of the whole desk followed by every promise checked against what actually happened: nobody in the comparison group was contacted, nothing was sent after a reply, every sent email matches what was approved and carries its legal footer, no email cites tracking data.
245	
246	### At production size
247	
248	Measured on 2026-11-11 on a laptop (Apple silicon, Postgres 18): 5,000 accounts simulated for 30 days in 71 seconds with no failed job, then 2 million signals loaded on top. Every page answered in under 50 ms except Signals (under 0.2 s); rescoring took 10 ms an account and 0.8 s per nightly batch of 500; every monitor ran in 50 ms or less. Two pages took 2.4 to 2.7 seconds before an index covering signal type and time, and a feed query that walks the status index instead of sorting every signal.
249	
250	At that size the monitors also found the real limit: four SDRs cannot approve first emails fast enough for 5,000 accounts, so 38 accepted accounts passed their play's time limit before a first email. The fix is people or autonomy, not code.
251	
252	Or with Docker, the same image the hosted demo runs:
253	
254	```bash
255	make docker
256	```
257	
258	## Reply labelling, measured
259	
260	48 labelled replies, written to include the cases that break classifiers: an "unsubscribe" inside a quoted footer or a legal signature, an assistant answering for their boss, a referral with and without an email address, a reply that tries to instruct the system, and replies in Spanish, German, French and Portuguese. Run through the real pipeline (cleaning, rules, then Claude Opus 5.5 at low effort) on 2026-11-11:
261	
262	| Measure | Result |
263	|---|---|
264	| Exact label | 45 of 48 (94%) |
265	| Label a person would accept | 47 of 48 (98%) |
266	| Rules alone | 12 of 48 (25%) |
267	| Settled by rules with no model call | 11 of 48 |
268	| Written by someone else, spotted | 2 of 2 |
269	| Attempt to instruct the system, flagged | Yes |
270	| Referral emails the model invented | 0 |
271	
272	Two of the three misses are calls a reviewer could go either way on ("¿Podemos hablar la semana que viene?" read as a meeting request rather than interest). The labels were left as written. 37 model calls cost $0.25. The answers are recorded in `evals/recordings/`, CI replays them without a key, and a prompt change fails CI until the eval is re-recorded. Full report: [evals/REPLIES.md](evals/REPLIES.md). The set is small and written by the author, so treat it as a regression guard, not a benchmark.
273	
274	## What is real and what is simulated
275	
276	**Real and tested:** the scoring, plays, the contact gate and the database trigger behind it, the copy checks, the account calendar, send windows and holidays, mailbox and domain health rules, stop-first reply handling, reply cleaning and the rules that label replies, attribution, the statistics, signed webhooks, one-click unsubscribe, erasure, the job queue and the monitors.
277	
278	**Simulated:** every vendor (people search, email finder and verifier, phone finder, website research, the mail provider, deliverability telemetry, the CRM, Slack) and every buyer. The simulated world gives each company a hidden need; signals and replies are drawn from it, with some signal types linked to need strongly and some barely, so the results pages have something true to find.
279	
280	**Not yet proven:**
281	
282	- Reply labelling is measured on real Claude answers; the brief, drafting and call-note tasks still run on the deterministic stand-in in the demo and tests.
283	- No live vendor adapter is written yet. The contracts are in `src/outbound/adapters/__init__.py`.
284	- There is no login. "Acting as" is chosen from a menu in demo mode; `AUTH_MODE=header` reads identity from a trusted proxy such as Cloudflare Access. Live sending refuses to start in demo mode.
285	- Region rules (which countries need a recorded legitimate interest or consent before a cold email) are a starting point. Counsel to confirm.
286	- Profile photos in the demo are stock portraits from randomuser.me. In live use the photo URL comes from the enrichment vendor and is erased with the person.
287	
288	## License
289	
290	PolyForm Noncommercial 1.0.0.
291
