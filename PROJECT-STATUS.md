# Account Desk: project status

**Updated:** 2026-11-11. **Spec:** `docs/SPEC.md` (sections 1 to 21, then 22 with every review decision, which wins where they differ). **Decisions:** `docs/DECISIONS.md`, 1 to 46. **Name:** Account Desk since 2026-11-11, renamed from Outbound Desk (Bryan: the tool is purely account-based). Repo renamed to `account-desk` (GitHub redirects the old address); live at https://account-desk-x4ko.onrender.com (plain `account-desk` was taken on Render). The local folder is still `~/Developer/outbound-desk` and the Python package is still `outbound`.

## Where it stands

v1 is built end to end on simulated vendors. **Public** at https://github.com/bryanacevedo/account-desk since 2026-11-11 (Bryan: keep the name, publish). CI green on the first push (lint, the suite on Postgres 18, the web build). **Live demo** at https://account-desk-x4ko.onrender.com since 2026-11-11 (Render free plan, service `account-desk`, Docker with Postgres inside; the 60-day simulation is built into the image, so the app starts in seconds once Render has woken the container (up to a minute after idling); checked on the live link: every page 200 in under 0.7 s). The first deploy failed because the simulation ran at start and took longer than Render's port wait; fixed by building it into the image.

Checked on 2026-11-11 by running them:

- `pytest` on real Postgres 18: 201 tests (the count `pytest --collect-only` gives on 2026-11-11; the last full run recorded here passed 199), including a 21-day simulation of the whole desk (140 accounts) checked against every promise, and regression tests for both code reviews and both design reviews.
- `ruff check src tests`: clean. `tsc --noEmit` and `vite build`: clean.
- `make demo`: 700 invented accounts, 60 simulated days; opens on 2026-11-11 with work waiting for three of the four SDRs (Maya Okafor has none that morning).
- Every page walked in the browser pane at 1440 wide: Today, Accounts and the account sheet, Approvals and the email sheet. Since then two fresh design reviews and checks at 375 wide (see below).

## At production size (measured 2026-11-11)

5,000 accounts, 30 simulated days: 71 s, no dead jobs. Then 2,008,711 signals: every page under 50 ms except Signals (88 to 165 ms), rescoring 10 ms an account and 0.8 s per batch of 500, monitors 50 ms or less. Signals and Results were 2.7 s and 2.4 s before migration 0004's `signals_type_recent` index and the split feed query. The `slow_first_touch` monitor found 38 accounts past their play's time limit: four SDRs cannot approve fast enough for 5,000 accounts.

## Reviews

- Final goldfish review (2026-11-11, two fresh reviewers in parallel: one read the docs against the code, one read only the code and the demo): the README hid the fourth autonomy stage and called the eval and live-adapter state wrong, PROJECT-STATUS had stale counts, calls showed as skipped on In flight, and a message written already sent skipped the send guard. All fixed with tests where code changed.
- Spec: goldfish review against its sources and the build checklist, a real-world review against how strong teams run signal-based outbound in 2026, and a re-review after the blockers were fixed. 49 findings, all resolved in spec section 22.
- Second code review (fresh, 2026-11-11, everything since the first publish): "ship after fixes", no blocker, 10 majors (erased people could be re-imported or stay named in signals, a stopped person's call task stayed open and calls skipped the contact rules, a connected call could cost a play its sourced credit, the CRM owner cursor could skip bulk changes, a reply could point the desk at any address, the play-cap alert and live AI charges were lost on rollback, the cap check relied on the caller's locks, a sequence could change under people in it, the CRM could hand accounts back to someone who left). All fixed with regression tests (`tests/test_review_fixes.py`), plus most minors; the tests also found that erasing someone whose signal had only a quote would have failed.
- Code: one fresh reviewer, verdict "do not ship" with 11 blocking findings (double-send on a crash mid-send, jobs stranded in running, plays that could stay open forever, a customer turned back into a prospect by a lost expansion deal, a spoofable login header, a default webhook secret, failed drafts approvable unchanged, wrong influenced attribution, and others). All 11 fixed with regression tests, plus most non-blocking items (commit `9b055c4`).

- Design: one fresh hands-on reviewer drove every page and panel at 1440 and 375 wide (2026-11-11): "not ready to show", 3 blockers (phone rows, broken draft grammar, panels scrolling sideways), 14 major (explanatory sentences, jargon, numbers shown twice, two names for one thing, decorative dots, phone navigation, Approve and Reject behaving differently, losing the tab on Back, team work labelled as yours) and nits. All blockers and majors fixed and checked at both widths; checking at 375 also found a tab strip that collapsed to 1px and a page that grew to 402px wide, both fixed. Bryan's own review: "best design work so far", with comments to come.
- Found by the flow test during the fixes: a resume after an out-of-office brought a colleague's first email forward to the same day; a pause now keeps each person's planned time.

## Proven and not proven

**Proven on simulated vendors:** scoring and its reproduction, play matching and the comparison group, research and the buying committee, drafting with the copy checks, approvals and autonomy stages, the account calendar and send windows, mailbox and domain health, the database trigger behind every send, stop-first replies, reply cleaning and rules in five languages, meetings, attribution, the statistics (Wilson and Newcombe checked against published values), signed webhooks, one-click unsubscribe, erasure, the job queue and its reaper, the monitors.

**Not proven:**

- Every AI task has an eval (268 cases, 194 written by an agent that never saw the code), run live once on 2026-11-11: replies 99% accepted (147 of 148), drafts 94% pass after one rewrite (47 of 50) and 70% judge-faithful (35 of 50), briefs 100% faithful (20 of 20), suggested replies 63% pass every check (19 of 30) with 1 of 30 judged invented, call notes 87% recall. Not a real buyer among them.
- Only the DNS check is live (SPF, DKIM and DMARC over DNS-over-HTTPS). Every other vendor is simulated: people search, finders, verifier, catch-all resolver, company data, phone, research, mail provider, telemetry, CRM, Slack. For these only the contracts exist, and in live mode a vendor without a key refuses instead of simulating.
- The HeyReach webhook has not seen a real event.
- No mail provider adapter: a live desk cannot send email yet.
- Real login only through Cloudflare Access token verification, which has not been run against a real Access app.
- Region rules are a starting point. Counsel to confirm.
- Contention from several servers at once (one process was measured).

## Next

1. Live vendor adapters beyond DNS (people search, finder, verifier, mail provider, seed tests, CRM, Slack), with `docs/INTEGRATIONS.md`; a delivery-event webhook for complaints and soft bounces.
2. Tests for the time-based play exits, CRM push retries and SLA escalation.

## Done since the first review (2026-11-11)

Counts in this list (tests, cases) are as of when each item was done, not today's.

- Hard gates on invention, in code: suggested replies are checked for numbers, product facts and placeholders the prospect did not bring up (rewritten once, then withheld); every draft's sentences about the buyer are read against the facts by a second call (rewritten once, then held as Needs a rewrite). Re-measured live: drafts 94% pass, briefs 100% faithful, suggested replies with no invented number or placeholder. Accounts list pages through all accounts. The held-back comparison is said in plain words.

- The AI layer, made measurable: 268 eval cases over all six tasks (194 written independently), graded by code and a Claude Sonnet 5.5 judge with written checklists, with recordings so CI replays them free and floors in `evals/thresholds.json`. The first live run found real faults and the prompts were fixed against it: suggested replies invented product facts and left placeholders (half the cases, now 1 in 30); drafts stated guesses about the buyer as fact (40% judge-faithful on the first run, now 70%); briefs stated inferences as findings (10% on the first run, now 100%); return dates were missed for want of today's date; a departure notice was read as out of office. A weekly live workflow is in place but dormant without an API key secret; an in-app check alerts when SDRs start editing many more drafts.

- Final reviews on the final state (2026-11-11): a goldfish drift check (README and decisions accurate; five stale lines here, fixed) and a fresh design review (11 majors, all fixed: "Draft rejected" instead of a wrong "Email rejected"; follow-up drafts count as waiting on the team in In flight; panels say "overdue" against the desk's clock; the colleagues decision only while colleagues are waiting; "Play started" against "Held back" with share bars drawn to 100%; the finder order as figures; honest statuses with icons; a readable per-signal table; play people and meetings open; one owner on every page; "Colleague's meeting"). The six nits were then fixed too: figures on one line, a call panel with why now and what was sent, values shown once, one word per thing, nine distinct panel tints with ink labels, and a phone stage control that shows there is more.

- Signals layer, after a fresh deep review (five real findings, all fixed and tested): enrichment signals are dated by when the event happened (a seat taken 80 days ago reads as 80 days old); the same event from two sources counts once in intent, with a small bonus for agreement, and each type's contribution is capped; accounts are re-checked for a play nightly, so a moment that arrived during a hold is not stranded; a signal starts at most one play; per-signal results count each account once and say "too few to tell" or "not measured" instead of showing a bare rate. Not done: time to first touch is still measured from when a signal arrived, not when its event happened.

- Enrichment made deep after a fresh review of that layer: company data with monthly snapshots and signals from what changed (team growth, open roles, tools added or dropped, funding, someone new in a finance seat); catch-all addresses resolved by a second vendor and never sent unconfirmed (and no longer re-checked every 4 hours); provenance per field; departments in persona matching; role start, city, headline and match confidence kept, low-confidence matches refused; phones typed, do-not-call never dialled; one identity per LinkedIn profile; paid answers kept outside the job so a retry never pays twice; a daily refresh (companies monthly, people quarterly, addresses after 45 days); moves clear stale details; imports record moves. 7 enrichment tests.
- The database also refuses an email from a paused mailbox, an unauthenticated, blocklisted or new domain, a mailbox still warming up, or a domain at a 0.3% spam rate (0022). Autonomous auto-approval and automatic demotion are now tested.
- Final design review fixes: the cost page reads as figures; meeting outcomes only once it has started; Replies shows everyone's to managers; one wording for late ("Overdue by 2 days"); In flight lists what waits on the team first, says "Waiting on you", and has a key to the step strip; Live is the paper plane breathing, not a coloured dot; panel tints in distinct families and the header adds context instead of repeating the name; Health lists failing checks first.

- Side panels say what they are: each kind (account, person, email, reply, call, LinkedIn, task, meeting, play) has a mark in the header and a hairline in its own quiet tint, and the sections inside are separated by rules with consistent headings.
- Email finding is a waterfall: finders are asked in order (the demo simulates Findymail, then Prospeo, then LeadMagic), a miss or an address that fails verification moves to the next, and each finder is charged only for an address it returns. The cost page shows each step's answer rate and recommends a vendor per role. Tested.
- In flight shows full names.

- Vendors and costs page (managers and GTM): every vendor and signal source, paid, metered or free, connected, simulated or not connected, spend this month with flat fees prorated, projection, last month, cost per outbound meeting, credits, spend by play. The demo charges every lookup, every simulated AI call at its typical size, and seeded flat fees (mailbox seats, seed tests, HeyReach senders, paid feeds), all labelled as assumptions: about $1,820 last month, $130 per outbound meeting. Results links to it.
- Motion pass: running states (Live, Reaching out, In sequence, Sending mail) show an on-air pulse; figures count to their value; the segmented control's thumb slides; pages arrive with a short rise; nav counts pop when they change; step strips fill in left to right; the mark's fourth dot fills on hover; toasts rise. Everything is off under reduced motion.
- Every status word explains itself on hover (checked against what the code does).
- Inboxes failed locally because the database was three migrations behind; the server now applies pending migrations at start, one instance at a time.

- In flight search (company, domain or person) and filters (play, SDR, next step: due today, a call or LinkedIn, waiting on the team), kept in the URL; checked at 800 and 375 wide.
- Renamed Account Desk, tagline "Signal & Account based outbound", new mark (one account, the people in it, one still to reach) in the sidebar and favicon.
- HeyReach webhooks: `POST /api/webhooks/linkedin/{LINKEDIN_TOOL_TOKEN}` takes connection accepted and the first reply; tested (matching by profile however it is written, no double counting, unknown people acknowledged and noted). Not yet tested against a real HeyReach event: the accepted event's field names come from third-party guides.
- In flight after a fresh design review (13 findings): a step is filled only if it was sent (skipped steps dashed), each stopped or paused person shows why, the Next column names the person and opens the reply, draft or meeting that waits, the SDR has a column, one count per view, 44px tap targets on phones, emails named "Email 3" as on Approvals, sorted by next step.

- The daily cap is the database's own rule: `mailbox_cap()` (migration 0017) computes ramp, ceiling and the spam and placement holds, and the send trigger uses it; nothing the sending code writes is trusted.
- CRM deals on accounts the desk does not know yet are held (`crm_held_deals`, migration 0018) and read again after an import or a resolved signal; tested.
- In flight page: every open play with each person's sequence as a step strip (done, next, not happening) and what happens next; stage filter, Mine and Team for SDRs. On phones it takes Accounts' slot in the bottom bar (Accounts moves to More). Checked at 1440 and 375 (no sideways scroll); tested. Then 170 tests.

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
