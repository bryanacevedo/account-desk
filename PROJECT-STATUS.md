# Outbound Desk: project status

**Updated:** 2026-11-11. **Spec:** `docs/SPEC.md` (sections 1 to 21, then 22 with every review decision, which wins where they differ). **Decisions:** `docs/DECISIONS.md`, 1 to 14. **Working name**, Bryan's to change.

## Where it stands

v1 is built end to end on simulated vendors. **Public** at https://github.com/bryanacevedo/outbound-desk since 2026-11-11 (Bryan: keep the name, publish). CI green on the first push (lint, the suite on Postgres 18, the web build). **Live demo** at https://outbound-desk.onrender.com since 2026-11-11 (Render free plan, service `outbound-desk`, Docker with Postgres inside; the 60-day simulation is built into the image, so a start or a wake takes seconds; checked on the live link: every page 200 in under 0.7 s). The first deploy failed because the simulation ran at start and took longer than Render's port wait; fixed by building it into the image.

Checked on 2026-11-11 by running them:

- `pytest` on real Postgres 18: 79 passed (77 then, plus 2 eval replays) in about 5 seconds, including a 21-day simulation of the whole desk (140 accounts) followed by checks of every promise against what happened, and 9 regression tests for the first code review's blocking findings.
- `ruff check src tests`: clean. `tsc --noEmit` and `vite build`: clean.
- `make demo`: 460 invented accounts, 60 simulated days in about 25 seconds; opens on 2026-11-11 with work waiting for each SDR.
- Every page walked in the browser pane at 1440 wide: Today, Accounts and the account sheet, Approvals and the email sheet. Not yet walked by a fresh reviewer against `docs/DESIGN-CHECKLIST.md`, and not yet checked at phone width.

## At production size (measured 2026-11-11)

5,000 accounts, 30 simulated days: 71 s, no dead jobs. Then 2,008,711 signals: every page under 50 ms except Signals (88 to 165 ms), rescoring 10 ms an account and 0.8 s per batch of 500, monitors 50 ms or less. Signals and Results were 2.7 s and 2.4 s before migration 0004's `signals_type_recent` index and the split feed query. The `slow_first_touch` monitor found 38 accounts past their play's time limit: four SDRs cannot approve fast enough for 5,000 accounts.

## Reviews

- Spec: goldfish review against its sources and the build checklist, a real-world review against how strong teams run signal-based outbound in 2026, and a re-review after the blockers were fixed. 49 findings, all resolved in spec section 22.
- Code: one fresh reviewer, verdict "do not ship" with 11 blocking findings (double-send on a crash mid-send, jobs stranded in running, plays that could stay open forever, a customer turned back into a prospect by a lost expansion deal, a spoofable login header, a default webhook secret, failed drafts approvable unchanged, wrong influenced attribution, and others). All 11 fixed with regression tests, plus most non-blocking items (commit `9b055c4`). A second code review has not run.

- Design: one fresh hands-on reviewer drove every page and panel at 1440 and 375 wide (2026-11-11): "not ready to show", 3 blockers (phone rows, broken draft grammar, panels scrolling sideways), 14 major (explanatory sentences, jargon, numbers shown twice, two names for one thing, decorative dots, phone navigation, Approve and Reject behaving differently, losing the tab on Back, team work labelled as yours) and nits. All blockers and majors fixed and checked at both widths; checking at 375 also found a tab strip that collapsed to 1px and a page that grew to 402px wide, both fixed. Bryan's own review: "best design work so far", with comments to come.
- Found by the flow test during the fixes: a resume after an out-of-office brought a colleague's first email forward to the same day; a pause now keeps each person's planned time.

## Proven and not proven

**Proven on simulated vendors:** scoring and its reproduction, play matching and the comparison group, research and the buying committee, drafting with the copy checks, approvals and autonomy stages, the account calendar and send windows, mailbox and domain health, the database trigger behind every send, stop-first replies, reply cleaning and rules in five languages, meetings, attribution, the statistics (Wilson and Newcombe checked against published values), signed webhooks, one-click unsubscribe, erasure, the job queue and its reaper, the monitors.

**Not proven:**

- Reply labelling is measured on live Claude answers (2026-11-11, `evals/REPLIES.md`): 45 of 48 exact, 47 of 48 acceptable, rules alone 12, injection flagged, no invented referral emails, $0.25. The set is 48 author-written replies: a regression guard, not a benchmark. Brief, drafts and call-note extraction still run on the stand-in only. The key lives in `.env` (gitignored, 600).
- No live vendor adapter (people search, finder, verifier, phone, research, mail provider, telemetry, CRM, Slack). Contracts only.
- No MCP server yet (in the spec, section 20).
- No eval sets yet for the brief, drafts or call notes (spec 22.15).
- Real login only through Cloudflare Access token verification, which has not been run against a real Access app.
- Region rules are a starting point. Counsel to confirm.
- Contention from several servers at once (one process was measured).

## Next

1. A fresh hands-on design review of every screen against `docs/DESIGN-CHECKLIST.md`, including phone width.
2. A play editor for GTM (draft, edit, preview matching accounts) and launch with a cost card for the manager: plays are only seeded in code today (Bryan asked who creates them, 2026-11-11).
3. Evals for drafts and briefs with live calls (the reply set is done).
4. The MCP server, live adapters vendor by vendor (Apollo, a verifier, Instantly or Smartlead, HeyReach, HubSpot, Slack, Google Postmaster).
5. A second fresh code review.
