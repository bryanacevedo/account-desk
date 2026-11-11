# Account Desk: project status

**Updated:** 2026-11-11. **Spec:** `docs/SPEC.md` (sections 1 to 21, then 22 with every review decision, which wins where they differ). **Decisions:** `docs/DECISIONS.md`, 1 to 14. **Name:** Account Desk since 2026-11-11 (was Outbound Desk; Bryan: the tool is purely account-based). The repo and the Render address still say outbound-desk until he confirms renaming them.

## Where it stands

v1 is built end to end on simulated vendors. **Public** at https://github.com/bryanacevedo/outbound-desk since 2026-11-11 (Bryan: keep the name, publish). CI green on the first push (lint, the suite on Postgres 18, the web build). **Live demo** at https://outbound-desk.onrender.com since 2026-11-11 (Render free plan, service `outbound-desk`, Docker with Postgres inside; the 60-day simulation is built into the image, so a start or a wake takes seconds; checked on the live link: every page 200 in under 0.7 s). The first deploy failed because the simulation ran at start and took longer than Render's port wait; fixed by building it into the image.

Checked on 2026-11-11 by running them:

- `pytest` on real Postgres 18: 152 passed on 2026-11-11 after both layer reviews' work (79 at first publish) (77 then, plus 2 eval replays) in about 5 seconds, including a 21-day simulation of the whole desk (140 accounts) followed by checks of every promise against what happened, and 9 regression tests for the first code review's blocking findings.
- `ruff check src tests`: clean. `tsc --noEmit` and `vite build`: clean.
- `make demo`: 460 invented accounts, 60 simulated days in about 25 seconds; opens on 2026-11-11 with work waiting for each SDR.
- Every page walked in the browser pane at 1440 wide: Today, Accounts and the account sheet, Approvals and the email sheet. Not yet walked by a fresh reviewer against `docs/DESIGN-CHECKLIST.md`, and not yet checked at phone width.

## At production size (measured 2026-11-11)

5,000 accounts, 30 simulated days: 71 s, no dead jobs. Then 2,008,711 signals: every page under 50 ms except Signals (88 to 165 ms), rescoring 10 ms an account and 0.8 s per batch of 500, monitors 50 ms or less. Signals and Results were 2.7 s and 2.4 s before migration 0004's `signals_type_recent` index and the split feed query. The `slow_first_touch` monitor found 38 accounts past their play's time limit: four SDRs cannot approve fast enough for 5,000 accounts.

## Reviews

- Spec: goldfish review against its sources and the build checklist, a real-world review against how strong teams run signal-based outbound in 2026, and a re-review after the blockers were fixed. 49 findings, all resolved in spec section 22.
- Second code review (fresh, 2026-11-11, everything since the first publish): "ship after fixes", no blocker, 10 majors (erased people could be re-imported or stay named in signals, a stopped person's call task stayed open and calls skipped the contact rules, a connected call could cost a play its sourced credit, the CRM owner cursor could skip bulk changes, a reply could point the desk at any address, the play-cap alert and live AI charges were lost on rollback, the cap check relied on the caller's locks, a sequence could change under people in it, the CRM could hand accounts back to someone who left). All fixed with regression tests (`tests/test_review_fixes.py`), plus most minors; the tests also found that erasing someone whose signal had only a quote would have failed.
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

1. Live vendor adapters beyond DNS (people search, finder, verifier, mail provider, seed tests, CRM, Slack), with `docs/INTEGRATIONS.md`; a delivery-event webhook for complaints and soft bounces.
2. Tests for the time-based play exits, auto-approve and demotion, CRM push retries and SLA escalation.

## Done since the first review (2026-11-11)

- In flight search (company, domain or person) and filters (play, SDR, next step: due today, a call or LinkedIn, waiting on the team), kept in the URL; checked at 800 and 375 wide.
- Renamed Account Desk, tagline "Signal & Account based outbound", new mark (one account, the people in it, one still to reach) in the sidebar and favicon.
- HeyReach webhooks: `POST /api/webhooks/linkedin/{LINKEDIN_TOOL_TOKEN}` takes connection accepted and the first reply; tested (matching by profile however it is written, no double counting, unknown people acknowledged and noted). Not yet tested against a real HeyReach event: the accepted event's field names come from third-party guides.
- In flight after a fresh design review (13 findings): a step is filled only if it was sent (skipped steps dashed), each stopped or paused person shows why, the Next column names the person and opens the reply, draft or meeting that waits, the SDR has a column, one count per view, 44px tap targets on phones, emails named "Email 3" as on Approvals, sorted by next step.

- The daily cap is the database's own rule: `mailbox_cap()` (migration 0017) computes ramp, ceiling and the spam and placement holds, and the send trigger uses it; nothing the sending code writes is trusted.
- CRM deals on accounts the desk does not know yet are held (`crm_held_deals`, migration 0018) and read again after an import or a resolved signal; tested.
- In flight page: every open play with each person's sequence as a step strip (done, next, not happening) and what happens next; stage filter, Mine and Team for SDRs. On phones it takes Accounts' slot in the bottom bar (Accounts moves to More). Checked at 1440 and 375 (no sideways scroll); tested. 170 tests.

- Play editor: GTM writes a play with a live preview of matching accounts and a worst-case cost card, saved as a draft; a manager who did not write it launches it. Checked in the browser.
- Plays with no email step activate directly; tested end to end.
- Inbox placement (decision 15): weekly seed tests per mailbox at Gmail and Outlook hold or pause a mailbox, a missing test counts as unknown, and a mailbox that goes quiet next to its peers raises an alert. Shown on Inboxes as "Where mail lands". 4 tests. The 0001 table that was never written to is replaced.
- LinkedIn and calls (decision 16): drafted notes through the copy checks, sent through the send guard, every outcome a touch, LinkedIn replies as replies, guarantee 20 in the trigger, a monitor for it, results by channel on Results. 16 tests. Checked in the browser: a note marked sent shows on the person's history and LinkedIn row.
- People open a person sheet from an account: how to reach them, their plays, and one history across email, LinkedIn, calls and signals.
- Icons within the Instrument identity (status icons in ink, green for healthy, amber and red only where someone must act); relative times spelled out ("2 days ago"), Bryan's call.
- After the first layer review (Bryan: "greenlight on deepening all the layers that are thin"): deals read from the CRM with attribution that needs a cause and is recomputed; owners from the CRM; meetings with a sheet, a date, outcomes, notes and a booking webhook; referrals enrolled and job changes as signals; a real desk from `init` and CSV imports; live DNS checks; mailbox and domain caps and replies in the send trigger; do-not-contact, holds, unmatched-signal resolution, resumes and unknown sends in the UI; a read-only MCP server; per-play monthly caps set at launch.
- After the second layer review: live mode refuses missing vendors instead of simulating them; customers are never downgraded; fit is judged on known fields and the ICP is editable; the watched batch and the comparison count correctly; live plays keep their audience until paused; erasure closes its gaps; the remaining UI dead ends have actions. Decisions 18 to 31.
- The footer is two lines and says "unsubscribe"; "no thanks" means not interested (decision 25, Bryan's correction).
- Team and sending administration (decision 32). Evals for drafts and briefs from live Claude (decision 33, README table).
- A second hands-on design review (2026-11-11): 5 phone blockers (pages scrolling sideways) and about 26 majors (contradicting figures, one thing with several names, explaining sentences, jargon, a dead end in the play editor). Blockers and majors fixed; checked at 375 and 1440.
- The flaky monitor test was the slow-first-touch alert catching late approvals by simulated SDRs, which is its job; the test now fails only when a play is stuck inside the desk, and that found a real one (decision 17). Simulator picks now use its seeded generator instead of SQL `random()`.
