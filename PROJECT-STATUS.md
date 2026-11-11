# Outbound Desk: project status

**Updated:** 2026-11-11. **Spec:** `docs/SPEC.md` (sections 1 to 21, then 22 with every review decision, which wins where they differ). **Decisions:** `docs/DECISIONS.md`, 1 to 14. **Working name**, Bryan's to change.

## Where it stands

v1 is built end to end on simulated vendors and runs locally. It is not on GitHub and not hosted yet: creating the public repo is Bryan's call (name still open).

Checked on 2026-11-11 by running them:

- `pytest` on real Postgres 18: 77 passed in about 5 seconds, including a 21-day simulation of the whole desk (140 accounts) followed by checks of every promise against what happened, and 9 regression tests for the first code review's blocking findings.
- `ruff check src tests`: clean. `tsc --noEmit` and `vite build`: clean.
- `make demo`: 460 invented accounts, 60 simulated days in about 25 seconds; opens on 2026-11-11 with work waiting for each SDR.
- Every page walked in the browser pane at 1440 wide: Today, Accounts and the account sheet, Approvals and the email sheet. Not yet walked by a fresh reviewer against `docs/DESIGN-CHECKLIST.md`, and not yet checked at phone width.

## At production size (measured 2026-11-11)

5,000 accounts, 30 simulated days: 71 s, no dead jobs. Then 2,008,711 signals: every page under 50 ms except Signals (88 to 165 ms), rescoring 10 ms an account and 0.8 s per batch of 500, monitors 50 ms or less. Signals and Results were 2.7 s and 2.4 s before migration 0004's `signals_type_recent` index and the split feed query. The `slow_first_touch` monitor found 38 accounts past their play's time limit: four SDRs cannot approve fast enough for 5,000 accounts.

## Reviews

- Spec: goldfish review against its sources and the build checklist, a real-world review against how strong teams run signal-based outbound in 2026, and a re-review after the blockers were fixed. 49 findings, all resolved in spec section 22.
- Code: one fresh reviewer, verdict "do not ship" with 11 blocking findings (double-send on a crash mid-send, jobs stranded in running, plays that could stay open forever, a customer turned back into a prospect by a lost expansion deal, a spoofable login header, a default webhook secret, failed drafts approvable unchanged, wrong influenced attribution, and others). All 11 fixed with regression tests, plus most non-blocking items (commit `9b055c4`). A second code review has not run.

## Proven and not proven

**Proven on simulated vendors:** scoring and its reproduction, play matching and the comparison group, research and the buying committee, drafting with the copy checks, approvals and autonomy stages, the account calendar and send windows, mailbox and domain health, the database trigger behind every send, stop-first replies, reply cleaning and rules in five languages, meetings, attribution, the statistics (Wilson and Newcombe checked against published values), signed webhooks, one-click unsubscribe, erasure, the job queue and its reaper, the monitors.

**Not proven:**

- No live model call. Brief, drafts, reply labels and call-note extraction run on the deterministic stand-in. Recording real answers needs an Anthropic key (`ANTHROPIC_LIVE=1`).
- No live vendor adapter (people search, finder, verifier, phone, research, mail provider, telemetry, CRM, Slack). Contracts only.
- No MCP server yet (in the spec, section 20).
- No evals with labelled sets yet (spec 22.15).
- Real login only through Cloudflare Access token verification, which has not been run against a real Access app.
- Region rules are a starting point. Counsel to confirm.
- Contention from several servers at once (one process was measured).

## Next

1. Bryan: the repo name and the go-ahead to create the public GitHub repo, then the Render service.
2. A fresh hands-on design review of every screen against `docs/DESIGN-CHECKLIST.md`, including phone width.
3. Evals: a labelled reply set and a draft set, recorded with a real key.
4. The MCP server, live adapters vendor by vendor (Apollo, a verifier, Instantly or Smartlead, HeyReach, HubSpot, Slack, Google Postmaster).
5. A second fresh code review.
