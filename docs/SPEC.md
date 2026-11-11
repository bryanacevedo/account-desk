# Outbound Desk: spec

**Written:** 2026-11-11. **Working name**, Bryan's call to rename. **Status:** v1 spec, before code.

Outbound Desk runs signal-based, account-based outbound from one place. It watches for moments when a company that fits your ideal customer profile (ICP) shows it may need you, decides which accounts are worth working this week and why, maps the people who buy there, drafts outreach grounded in what actually happened at that company, has a person approve it, sends it through healthy inboxes at a pace a human would, and handles every reply, meeting and outcome through to pipeline. It measures which signals turn into meetings and which do not, and feeds that back into the score.

It is the opposite of volume outbound. The unit of work is an **account in a play**, never a contact in a list.

## 1. What the research says, and the design rules it gives

Sources checked 2026-11-11 (vendor blogs, so figures are treated as unverified; the direction is consistent across them): [Unify on team structure](https://www.unifygtm.com/explore/signal-based-outbound-team-structure), [Autobound 2026 playbook](https://www.autobound.ai/blog/outbound-sales-playbook-2026), [Lusha on why AI SDRs failed](https://www.lusha.com/blog/why-the-ai-sdr-dream-failed/), [Belkins on AI SDR limits](https://belkins.io/blog/ai-sdr), [Abmatic on committee orchestration](https://blog.abmatic.ai/how-to-orchestrate-buying-committee-touches-by-stage), [Red Sift on bulk sender rules](https://redsift.com/guides/bulk-email-sender-requirements).

| Finding | Rule in this system |
|---|---|
| Fully autonomous AI SDRs disappointed: shallow or invented personalization, burned domains, bad data underneath (Lusha, Belkins). | AI researches and drafts. Code checks. A person approves. Autonomy is earned per play in stages with exit criteria the desk measures (section 9). |
| Personalization only works when it rests on something true and recent. | Every claim in a draft cites a fact id from the account's evidence. Code rejects a draft with an uncited claim or a number that is not in the evidence. |
| A signal is only useful when it matches the offer (Autobound). | Every signal type carries its written "because" and a weight. The desk measures each type's signal-to-meeting rate against a holdout and shows which ones earn their weight. |
| Signal plus ICP fit is the trigger, not either alone. | A play fires on a matching signal at an account above the fit floor. |
| Plays are owned by one person (the "outbound quarterback", most often in growth or marketing, a GTM engineer at larger teams), reps own replies and human steps (Unify). | Roles: GTM (owns plays, settings), Manager (approves launches, sees money), Rep (accepts accounts, approves copy, works replies and tasks). |
| Buying committees are large; orchestration coordinates people and channels on one account calendar. | One account calendar per account in play. Each person's steps are staggered, capped and stopped together. |
| Contact data decays roughly 2% a month, mostly from job changes (real-world review). | Verification has an age. An address older than the limit is re-verified before its first send. |
| Gmail and Yahoo require SPF, DKIM, DMARC and one-click unsubscribe (RFC 8058) from bulk senders and hold complaint rates under 0.3% (target 0.1%); Microsoft enforces authentication but publishes no spam-rate threshold (Red Sift). | Domain checks block a mailbox from sending; every email carries a List-Unsubscribe and List-Unsubscribe-Post header; complaint and bounce thresholds pause a mailbox automatically. |
| High-volume sends can push a domain over Gmail's complaint ceiling within an afternoon (Belkins). | Low daily caps per mailbox and per domain; the first 20 sends of every play step are a watched batch; a bounce or complaint signal pauses before the batch completes (section 22). |
| Data layer first. | Accounts resolve by every known domain; people dedupe by email and LinkedIn URL; every fact carries its source and age. |

## 1a. Who does what: people, AI, code

Every step belongs to whichever of the three is good at it. A step that does not fit this table is a design error.

| Work | People | AI | Code |
|---|---|---|---|
| Decide what the ICP, plays and signal hypotheses are | Owns it | | Stores, versions, enforces |
| Notice a signal and tie it to a company | | Reads unstructured pages and posts into a typed signal (live sources only) | Dedupes, resolves by domain, decays, scores |
| Decide an account is worth working now | Accepts or skips the proposal | | Scores, matches the play, runs the account gate, draws the holdout |
| Understand the account | Reads the brief | Writes the brief from facts, citing each one | Checks every citation exists |
| Find who buys | Fills a gap by hand when it matters | Proposes who a referral is (never an email) | Matches personas, calls the finder and verifier, ranks |
| Write the message | Approves, edits, or writes | Drafts from cited facts | The copy gate: citations, numbers, length, banned words, merge fields |
| Decide whether a person may be contacted now | | | The contact gate, at every moment |
| When and from which inbox | | | Account calendar, send window, holidays, mailbox health and caps |
| Read a reply | Classifies when the model is unsure; answers every hot reply | Labels from a fixed list, extracts dates, referrals, new companies | Stops first, cleans, applies the rules, routes, starts the SLA clock |
| Talk to a buyer | Owns it: calls, LinkedIn, replies, meetings | Suggests a reply the rep may use | Creates the tasks, logs the touches |
| Learn from calls | Decides which notes are worth learning from | Extracts objections, competitors, reasons from the notes | Aggregates by play and signal (a GROUP BY a person can audit) |
| Know whether it works | Changes weights and plays | | Funnel, holdout lift, signal performance, monitors |

## 1b. Lessons from running outbound in production

From a previous system Bryan ran (ideas only, nothing copied):

- A reply has side facts beside its label: whether the writer is the person we wrote to (an assistant or a forward is not them), and a named referral. The model may name who; it never writes an email address. A vendor finds and verifies the address, and a person promotes the referral.
- Engagement on one channel stops the other channel for that person in the same transaction, and every channel writes one touch log, so "have we touched them" has one answer.
- A draft that fails the copy gate is re-drafted once, then goes to a person. Each attempt is kept beside the final verdict, so a rescued draft does not look like it never failed.
- Integrity checks observe and never fix. They also check themselves: a check that skipped on every run protects nothing. Every source with a cadence must have run. Every stored score must reproduce from its inputs. Every paid call leaves a ledger row. A vendor's "verified" is stored as the vendor's claim with its date, never as ours.
- AI may propose a new monitor; only a person adds it.
- Research about a company is cached by domain with an age, so the same company is not paid for twice.

## 2. Who uses it

- **Rep** (account executive or SDR). Owns a book of accounts. Sees Today: accounts proposed to them, drafts to approve, replies to answer, tasks due. Never sees company money.
- **Manager.** Sees the team, approves play launches, sees results and money.
- **GTM** (GTM engineer, RevOps). Owns signals, scoring, plays, mailboxes, settings, monitors. Sees everything.

There is no real login in the demo; "acting as" is chosen from a menu. Live sending is refused unless authentication is configured (section 13).

## 3. The flow

```
signal sources -> ingest -> resolve to account -> score (fit x intent x engagement)
   -> play trigger -> account proposed to its owner (or holdout arm)
   -> owner accepts -> research (brief with cited facts) -> buying committee (personas -> people)
   -> contacts verified -> drafts per person per step (AI, cited) -> copy gate (code)
   -> approval (person) -> account calendar scheduled -> contact gate at every step -> send
   -> reply: stop first, then classify -> route to owner, SLA clock -> meeting -> opportunity
   -> results by signal type and play, against holdout -> weights and play stages adjust
```

## 4. Data model (Postgres)

All tables are in `migrations/`. Every state column has a CHECK constraint naming its allowed values. Every stop, drop or rejection has a non-null reason enforced by CHECK. Money is stored in integer cents.

- **users** (id, name, role rep|manager|gtm, email, slack_id, timezone).
- **accounts** (id, name, primary_domain, industry, employees, revenue_band, hq_country, region, tech[], description, lifecycle prospect|customer|open_opp|churned|competitor|partner, owner_id, crm_id, fit_score, fit_tier A|B|C|X, fit_breakdown jsonb, fit_icp_version).
- **account_domains** (domain primary key, account_id). Resolution reads this, so aliases and acquired domains map to one account.
- **people** (id, account_id, full_name, first_name, last_name, title, seniority, function, persona_key, email, email_status unknown|valid|risky|invalid, email_verified_at, linkedin_url, country, timezone, status active|left|unreachable, source, crm_id). Unique on lower(email) and on linkedin_url.
- **facts** (id, account_id, person_id null, kind, text, source, source_url, observed_at). The evidence a brief and a draft may cite.
- **icp_versions** (id, rules jsonb, weights jsonb, published_by, published_at). Scoring pins the version.
- **personas** (key, label, title_patterns, seniority, committee_role economic_buyer|champion|user|technical|blocker, priority).
- **signal_types** (key, label, because, level account|person, weight, half_life_days, enabled, source).
- **signals** (id, type_key, source, external_id, account_id null, person_id null, raw_domain, raw_company, observed_at, ingested_at, strength 0..1, evidence jsonb, status matched|unmatched|ignored, ignore_reason). Unique (source, external_id).
- **account_scores** (account_id, computed_at, fit, intent, engagement, priority, breakdown jsonb, reason_signal_id) plus **score_history** for "what changed".
- **plays** (id, key, name, hypothesis, trigger jsonb, personas[], max_people, sequence jsonb, angle, autonomy research|draft|supervised|autonomous, status draft|live|paused|retired, holdout_pct, owner_id, launched_by, launched_at, sla_hours).
- **account_plays** (id, account_id, play_id, trigger_signal_id, arm treated|holdout, state (see 22.19), why_now jsonb, owner_id, proposed_at, accepted_at, closed_at, close_reason). Partial unique index: one open account play per account.
- **enrollments** (id, account_play_id, person_id, persona_key, state pending|active|paused|stopped|done, step_index, next_at, pause_until, stop_reason, mailbox_id).
- **messages** (id, enrollment_id, step_index, channel email|linkedin|call|task, subject, body, citations jsonb, body_hash, status draft|failed_gate|awaiting_approval|approved|rejected|scheduled|sending|sent|send_unknown|failed|cancelled, gate jsonb, approved_hash, approved_by, approved_at, scheduled_for, sent_at, mailbox_id, provider_id, thread_key).
- **mailboxes** (id, address, domain, provider, display_name, user_id, warmup_state, ramp_start, daily_cap, status active|paused|retired, pause_reason) and **sending_domains** (domain, spf, dkim, dmarc, dmarc_policy, registered_at, blocklisted, checked_at, status).
- **deliveries** (message_id, event sent|delivered|bounced_hard|bounced_soft|complaint, at, detail) for mailbox and template health.
- **replies** (id, message_id null, person_id null, account_id null, received_at, from_addr, subject, raw, cleaned, language, label, confidence, extracted jsonb, classified_by rules|model|person, needs_review, handled_by, handled_at, outcome).
- **suppressions** (id, kind email|domain|person|account, value, reason, source, created_at, expires_at null).
- **holds** (id, account_id, person_id null, reason, until, set_by).
- **meetings** (id, account_play_id, account_id, person_id, booked_at, starts_at, status booked|held|no_show|cancelled, source).
- **opportunities** (id, account_id, crm_id, name, amount_cents, stage, created_at, closed_at, won, source_play_id, attribution sourced|influenced|none).
- **touches** (id, account_id, person_id, account_play_id null, channel email|linkedin|call|meeting|other, direction out|in, kind, at, source, dedup_key unique). The one record of contact across channels.
- **call_notes** (id, meeting_id, text, worth_learning bool, marked_by) and **learnings** (id, call_note_id, kind objection|competitor|reason_to_buy|reason_not|quote, text, quote, play_id, signal_type).
- **tasks** (id, account_play_id, person_id, kind call|linkedin_connect|linkedin_message|research|reply, due_at, owner_id, status open|done|skipped, note).
- **jobs** (id, kind, payload, run_at, status queued|running|done|failed|dead, attempts, max_attempts, locked_at, locked_by, last_error, dedupe_key unique). Claimed with `FOR UPDATE SKIP LOCKED`.
- **crm_outbox** (id, kind, payload, idempotency_key unique, status pending|done|failed|dead, attempts, last_error).
- **ledger** (id, at, vendor, unit credits|tokens|usd_cents, qty, cost_cents, purpose, account_id, job_id) and **budgets** (vendor, period month, cap_cents).
- **llm_calls** (id, at, task, model, input_hash, input_tokens, output_tokens, cost_cents, output jsonb, source live|recorded|sim).
- **alerts** (id, at, kind, severity, channel, target_user, object, body, delivered_at, acked_at).
- **audit_log** (id, at, actor_id, action, object_kind, object_id, detail jsonb).
- **settings** (key, value jsonb). Includes the kill switch, caps, send window, limits.
- **sim_clock** (one row): the demo's clock. All time in the app reads `now()` from one function that returns the sim clock in demo mode.

## 5. Signals

**Sources** are adapters with one contract: `fetch(since) -> list[RawSignal]`. Shipped: simulated sources for every type, plus written adapters for a webhook intake (generic JSON, HMAC-signed), CSV import, Trigify-style social engagement, job-postings, funding and website-visit providers, all behind env keys. Each source run is recorded (`source_runs`: started, finished, fetched, matched, error) so a silent source is visible.

**Types shipped** (each with a "because" and a starting weight and half-life):

| Key | Level | Because | Weight | Half-life |
|---|---|---|---|---|
| champion_moved | person | A past buyer or user joined a new company and already trusts us. | 30 | 60 d |
| new_exec | account | A new leader in our buyer's function reviews tools in their first 90 days. | 22 | 45 d |
| hiring_function | account | Hiring for the team we serve means the pain we solve is growing. | 14 | 30 d |
| funding | account | New money funds new tools and new targets. | 12 | 60 d |
| pricing_visit | account | Someone at the company looked at our pricing. | 18 | 7 d |
| site_visit | account | Repeat visits to product pages. | 8 | 10 d |
| intent_topic | account | Research on our category across the web. | 10 | 14 d |
| competitor_review | account | Reviewing or complaining about a competitor. | 16 | 21 d |
| tech_added | account | Adopted a tool we integrate with. | 9 | 60 d |
| tech_removed | account | Dropped a competitor or a tool we replace. | 15 | 45 d |
| social_engaged | person | Engaged with our or a peer's content on the topic. | 7 | 14 d |
| expansion | account | Opened an office or entered a market we serve. | 8 | 60 d |
| news_negative | account | Layoffs or a freeze: lowers priority. | -15 | 45 d |

**Ingest** dedupes on (source, external_id), resolves the company by domain through `account_domains` (normalised: lowercase, strip `www.`, public email domains rejected), then by exact normalised name, else stores the signal as `unmatched` with the reason. An unmatched signal for a company that fits the ICP can create an account (setting `auto_create_accounts`). Person signals resolve by email, then LinkedIn URL. A `champion_moved` signal also marks the person `left` at the old account and creates the person at the new one.

Signals older than 3 half-lives are kept but contribute nothing.

## 6. Scoring

Three parts, each 0 to 100, with the breakdown stored.

- **Fit** from the published ICP version: weighted factors (industry, employee band, region, revenue band, required and helpful tech, excluded tech), each with its contribution. Hard excludes (lifecycle customer, open_opp, competitor; excluded industries) set tier X. Tiers: A at 70+, B at 50+, C otherwise.
- **Intent**: `raw = sum(weight_t * strength * 0.5^(age/half_life_t))` over the account's signals, plus a convergence bonus of 15% per distinct positive type beyond the first (capped at 3); `intent = 100 * (1 - exp(-raw / 40))`. Negative signals subtract after saturation, floored at 0.
- **Engagement** from our own outreach outcomes in the last 90 days (positive replies, meetings; never opens).
- **Priority** = `fit^0.4 * intent^0.6` when fit tier is A or B, else 0. The "reason" is the signal that contributed most.

Rescoring runs on every new matched signal for that account and nightly for decay. Each run writes `score_history` only when priority moves by 5 or more, which drives "what changed this week".

## 7. Plays

A play is: a hypothesis, a trigger, who to reach, the sequence, the angle, its autonomy stage, its holdout share, and its owner.

- **Trigger** (jsonb): `any_of` signal types, `min_strength`, `fit_tiers`, `min_priority`, `within_days`, `exclude_lifecycles`.
- **Who**: an ordered persona list and `max_people` (default 3). The champion persona goes first when there is one.
- **Sequence**: steps with channel, day offset, and whether a person does it (call, LinkedIn) or the desk sends it (email). Email steps after the first reply in-thread.
- **Shipped plays**: Champion moved, New leader first 90 days, Hiring the team we serve, Pricing page visit, Competitor review, Funding round.

**Matching** runs after each rescore. For an account with no open account play: pick the highest-priority live play whose trigger matches. Before proposing, the **account gate** runs (section 10). Then the holdout draw: a deterministic hash of (play, account) puts `holdout_pct` of accounts in the holdout arm, recorded, never contacted, and measured.

**Proposal** goes to the account owner (or round-robin among reps when there is none) with the why-now: the triggering signal's evidence and the top three score contributions. The owner accepts or skips with a reason. A proposal expires after `proposal_ttl_days` (default 5).

## 8. Research, committee and drafting

**Research** (AI, priced): one account brief per account play. Input: the account's facts and recent signals, each with an id. Output (structured): 3 to 5 bullet findings, each citing fact ids, and a suggested angle. Code checks every cited id exists for the account; a finding with no valid citation is dropped.

**Committee**: for each persona in order, choose the best person already known at the account (title match against persona patterns, seniority, not left, not suppressed); if none, ask the people-search adapter (Apollo-shaped, simulated by default, credits to the ledger). Find and verify emails through the email waterfall (finder then verifier, simulated by default, credits to the ledger). Stop at `max_people`. A persona with nobody is recorded as a gap, which the account page shows.

**Drafting** (AI): for each person and each step the desk sends, a draft from the brief, the person, the persona's angle and the step's job (open, follow up, break-up). Output (structured): subject, sentences each with the fact ids it relies on. The body is assembled from sentences. Step 1 is drafted at acceptance; later steps are drafted when the previous step is sent, so they can use anything learned since.

**Copy gate** (code, `copy_gate.py`). A draft passes only if all hold:
1. No unresolved merge field (`{{`, `[First`, `<name>`).
2. Length: step 1 body 40 to 120 words; follow-ups 20 to 90; subject 1 to 6 words, not all caps.
3. Opens with the person's first name as recorded (prefixes like "Dr." are stripped from the record, not invented).
4. Every sentence that states a fact about the account cites at least one fact id that exists for that account; at least one sentence cites a fact (it is about them).
5. Every number in the body appears in a cited fact.
6. No phrase from the banned list (stock openers, hype, fake familiarity), no em dashes, no exclamation marks beyond one.
7. At most one link, none in step 1; no attachments; no images.
8. Spam-trigger word score under the limit.
9. Not a near-duplicate (shingle similarity) of another draft sent to the same account.
A failing draft is re-drafted once with the failures listed; failing twice, it goes to the rep marked "failed gate" to write or skip.

## 9. Approval and autonomy stages

Each play has an autonomy stage:

| Stage | What the desk does alone | What a person does |
|---|---|---|
| research | Proposes accounts, writes briefs, maps committees. | Writes and sends outreach. |
| draft | Drafts every message. | Approves each message. |
| supervised | Drafts; approves follow-ups that passed the gate. | Approves every step 1, and a 1-in-5 sample of the rest. |
| autonomous | Sends anything that passed the gate, for fit tier B only. | Approves every tier A message. |

Promotion is proposed by the desk and approved by a manager, only when the play's last 50 approved drafts had an approve-without-edit rate of at least 90%, no complaint, bounce rate under 2%, and positive reply rate at or above the play's floor. Demotion is automatic on a complaint, a bounce rate over 3% in a day, or an edit rate over 30% in the last 20.

An approval stores `approved_hash = sha256(subject + body)`. Sending refuses any message whose current hash differs.

## 10. The contact gate

`gate.check(person, channel, at)` returns `allow` or a list of reasons. It runs at proposal (account part), at approval, at scheduling, and immediately before each send inside the transaction that holds the enrollment's row lock. Any reason blocks.

1. Kill switch on.
2. Suppressed: email, domain, person or account, unexpired.
3. Account lifecycle customer, open_opp, competitor; account fit tier X.
4. An account or person hold that has not expired.
5. Person status left or unreachable; email invalid; email verified more than `verify_max_age_days` (default 45) ago (schedules re-verification instead of failing hard).
6. Another active enrollment for this person in a different account play.
7. Touched by any play in the last `person_cooldown_days` (default 90), unless this is the same enrollment.
8. The account has `account_max_active` (default 3) people active already (counted at enrollment).
9. A reply from anyone at the account in the last `account_reply_pause_hours` (default 72) that is not yet handled.
10. Region rule: the person's country (not the company HQ) falls in a region set to `consent_required` and no basis is recorded. Region rules are labelled "counsel to confirm".
11. For email: no healthy mailbox with capacity; mailbox's domain failing SPF, DKIM or DMARC.

## 11. Sending and deliverability

**Account calendar.** When an account play goes active, every enrollment's steps are laid out on one calendar: the first person starts on the next send slot, each further person `stagger_days` (default 2) later, so no two people at one company get a first email the same day.

**Send window.** Steps land on business days in the recipient's timezone between `send_window` (default 08:30 to 11:30 and 13:30 to 16:00), skipping the country's public holidays (a small table for the countries in the demo). A random jitter of up to 25 minutes inside the window.

**Mailboxes.** A mailbox is used only when its domain passes SPF, DKIM and a DMARC policy, the domain is at least 30 days old, warmup has run 14 days, and it is not paused. Daily cap follows the ramp (5 a day in week 1, then +5 a week up to `mailbox_max_daily`, default 30). A person keeps one mailbox for their whole sequence; an account keeps its owner's mailboxes. The owner's own domain is never the primary company domain (outbound sends from a secondary domain).

**Health.** Rolling 7-day bounce rate over 3% or any spam complaint pauses the mailbox with the reason and alerts GTM. A template's first 20 sends are a watched batch: two hard bounces in that batch stop the template.

**Headers.** Every email carries `List-Unsubscribe` (mailto and https) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. The https endpoint suppresses the address immediately.

**Channels** are adapters with one contract: `send(message, mailbox) -> SendResult(sent|failed|unknown, provider_id)`. Shipped: simulated email (with a simulated recipient world that replies, bounces and complains), an SMTP/Gmail-API email adapter, Instantly and Smartlead (single-send API), and HeyReach for LinkedIn. LinkedIn steps default to a **task for the rep** (connect, message) because LinkedIn's terms prohibit automation; the HeyReach adapter needs a per-sender consent flag. Call steps are always tasks.

**Unknown outcomes.** A send that times out is `send_unknown`. It is never retried blindly; a reconcile job asks the provider by idempotency key, and a person resolves it if the provider cannot say.

## 12. Replies, meetings and pipeline

**Stop first.** Any inbound message matched to a person stops that enrollment and pauses every other active enrollment at the account, in the same transaction, before anything else happens. Classification second.

**Side facts.** Beside its label a reply carries `same_person` (false when an assistant, successor or forward wrote it; such a reply goes to the rep, never auto-actions the contact) and an optional referral (name, title, relationship; an email only when the reply itself contains it).

**Cross-channel.** A reply, connection acceptance or LinkedIn message from a person stops their email steps, and the reverse. Every touch on every channel, including the rep's calls and manual emails, is one row in `touches` (account, person, channel, direction, kind, at, source, dedup key).

**Matching.** By thread key, then by sender email, then by sender domain to the account; an unmatched reply is kept and shown to GTM, never dropped.

**Cleaning.** Strip quoted history (lines starting `>`, "On ... wrote:", Outlook headers), signatures and legal footers, so an "unsubscribe" in a quoted footer cannot opt someone out.

**Classification.** Rules first: bounce notifications (DSN), auto-replies (headers and phrasing), explicit opt-out phrases in English, Spanish, Portuguese, French and German. Then the model, which can only return a label from a fixed list plus extracted fields: `interested`, `meeting_request`, `question`, `not_now` (return date), `not_interested`, `referral` (name, email, title), `left_company` (new company if stated), `out_of_office` (return date), `unsubscribe`, `wrong_person`, `bounce`, `auto_reply`, `other`. Confidence below 0.7, or text that tries to instruct the system, goes to a person.

**Actions.**
- interested, meeting_request, question: hot. Alert the owner in the team channel with an @-mention; the SLA clock starts (default 4 business hours); a missed SLA escalates to the manager. A suggested reply is drafted for the rep, who sends it from their own inbox.
- not_now: hold the person and account until the date (default 90 days), then the account may be proposed again.
- not_interested: stop the account play (`lost`, reason), hold the account 180 days.
- referral: create the referred person (if an email is given) and propose adding them to the account play with a referral angle; the rep approves.
- left_company: mark the person left; if the new company is named, raise a `champion_moved` signal.
- out_of_office: pause the enrollment until the return date plus one business day, then resume at the same step. The account's other enrollments resume too.
- unsubscribe: suppress the email permanently; stop all their enrollments.
- wrong_person: stop that person; propose the next person for that persona.
- bounce: mark the email invalid, record the delivery event, propose the next person for that persona.

**Meetings** come from a booking adapter (simulated; Calendly/Chili Piper-shaped webhook) or are logged by the rep. A meeting moves the account play to `meeting` and stops all its enrollments. Held or no-show is recorded after the start time.

**Opportunities** sync from the CRM. An opportunity created within 90 days after a meeting from an account play is `sourced` by that play; one created at an account that had an active play in the 90 days before is `influenced`. One opportunity has one attribution.

**Learning from calls.** A rep pastes or uploads notes for a held meeting. A person marks them worth learning from. The model extracts atomic facts (objection, competitor named, reason to buy, reason not to, quote), each with the line it came from; code checks the quote is in the notes. Results aggregates them by play and signal type. Nothing the model extracts changes a play by itself.

## 13. CRM, Slack and security

**CRM** adapters (HubSpot-shaped and Salesforce-shaped; simulated by default). Read: accounts, owners, lifecycle, open opportunities, contacts. Write through `crm_outbox` with idempotency keys: contact create, activity (email sent, reply), task (hot reply), meeting. Retries with backoff; after 5 attempts an item is dead and alerts GTM.

**Slack**: hot replies, SLA escalations, launch requests and health alerts go to channels (`#outbound-replies`, `#outbound-ops`), never DMs, with the person @-mentioned. Every alert is also a row in `alerts`, and the health endpoint reports undelivered alerts, so a dead Slack is visible.

**Security.** Webhooks are HMAC-signed with a timestamp (5 minutes) and replay protection. Writes need a write key in shared deployments. Live sending (`LIVE_SEND=1`) refuses to start without `AUTH_MODE` set to a real mode. Personal data: erasure deletes the person, their messages and replies, and leaves a hashed suppression row so they are never re-added. Secrets only from env.

## 14. Spend

Every paid call (people search, email finder, verifier, model) writes the ledger with its cost at configured rates. Each vendor has a monthly cap; a call that would cross it waits and alerts GTM. Model calls record tokens and cost.

## 15. AI: where it runs and how it is checked

- Account brief, drafts, reply classification, suggested replies. Everything else is code.
- Structured outputs only. Model output can select a label or cite ids; code checks every id and every number.
- Model: `claude-opus-5-5` through the Anthropic SDK, effort `low` for classification and `medium` for drafting, configurable per task.
- **Record and replay**: every live call is recorded by input hash. CI replays recordings; a changed prompt marks recordings stale and `EVALS_STRICT=1` fails CI until re-recorded. The demo uses a deterministic simulated model.
- **Evals**: reply classifier (dev and holdout sets, multilingual, quoted-footer traps, injection attempts) with a confusion matrix; copy gate (labelled good and bad drafts); brief grounding (every finding cites a real fact). Rules-only baseline reported beside rules plus model.

## 16. Guarantees: prevented at write time, monitored where they cannot be

Decision (2026-11-11, Bryan left the call to Claude): no separate invariant layer. A promise the database can enforce is enforced when the row is written, so the bad state cannot exist: CHECK constraints, partial unique indexes, foreign keys, and triggers that refuse a send to a holdout or suppressed person, a send whose body changed after approval, a second open play per account, a second active enrollment per person, a stop with no reason. The rest (promises about time, other systems, or the absence of something) are **monitors**: queries that run on a schedule, write an alert to the ops channel when they find rows, and show on the Health page. Monitors never fix anything. The same list runs as a test after a simulated 60-day run in CI.

Each item below is labelled **[enforced]** (cannot happen) or **[monitor]** (detected and alerted).

1. **[enforced]** No email sent while its address or account was suppressed.
2. **[enforced]** Every sent message's hash equals its approved hash.
3. **[enforced]** No person has two active enrollments.
4. **[enforced]** No account has more than `account_max_active` active enrollments.
5. **[enforced]** Every stopped enrollment and every stopped account play has a reason.
6. **[enforced]** No message sent to a person after a reply from them.
7. **[monitor]** No email sent outside the recipient's send window or on a weekend.
8. **[enforced]** No mailbox sent more than its cap on any day.
9. **[enforced]** No message reached a holdout account.
10. **[monitor]** Every hot reply has an alert, and every alert past SLA has an escalation.
11. **[monitor]** No crm_outbox item pending for more than 24 hours.
12. **[enforced]** No send while the kill switch was on.
13. **[enforced]** Every account play beyond `proposed` has a trigger signal that exists.
14. **[monitor]** Monthly spend per vendor within its cap.
15. **[monitor]** Every paid adapter call has a ledger row (counted against the adapter call log).
16. **[monitor]** Every stored account score reproduces from its stored inputs.
17. **[monitor]** Every enabled signal source has run within twice its cadence.
18. **[enforced]** Every signal type that is enabled has a weight, a half-life and a "because".
19. **[enforced]** Every signal carries evidence with a source link or quote.
20. **[enforced]** No person was emailed after engaging on another channel in the same account play.
21. **[monitor]** The monitors themselves: every monitor ran in the last cycle (none skipped or errored), and the last cycle is recent.

## 17. Measurement

- Funnel by play and by signal type: proposed, accepted, contacted, replied, positive, meeting, opportunity, pipeline.
- **Lift against holdout**: meeting rate treated vs holdout per play, with a 90% interval (Wilson), labelled "too few to call" under 30 accounts per arm.
- Signal type performance: meetings per 100 accounts triggered, against the weight it carries. A suggestion to move a weight is shown; a person applies it.
- Rep SLA: median time to first response on hot replies; misses.
- Deliverability: bounce, complaint and reply rates per mailbox and domain.
- Cost: spend per meeting and per opportunity (managers and GTM only).

## 18. Web app

React and Vite, served by the API. Pages by job:

- **Today** (rep): proposed accounts to accept, drafts to approve, hot replies with their SLA, tasks due.
- **Accounts**: ranked by priority, why now, change this week, owner, stage.
- **Account** (side sheet and full page): who they are, score with its breakdown, signal timeline, committee by persona with gaps, the play and its calendar, messages and replies, meetings and pipeline.
- **Signals**: the feed, unmatched signals, source health, type performance.
- **Plays**: each play's hypothesis, trigger, sequence, stage, launch checks, results against holdout.
- **Approvals**: each draft beside the facts it cites, with the gate result; approve, edit or reject.
- **Replies**: every reply with its label, the action taken, and the ones a person must classify.
- **Deliverability**: domains and mailboxes, health, capacity forecast for the next 10 business days.
- **Results** (manager, GTM): funnel, lift, signal performance, cost per meeting.
- **Health** (GTM): monitors, jobs, outbox, sources, alerts, spend.
- **Settings** (GTM): ICP, signal types and weights, caps and windows, regions, suppression, kill switch.

Design follows the house design checklist (copied from Events Desk) with its own palette.

## 19. Operations

- One process in the demo: API, scheduler and worker. The worker claims jobs with `SKIP LOCKED`; the scheduler enqueues periodic jobs (ingest, decay rescoring, scheduled sends, SLA checks, reconcile, monitors) with dedupe keys so a double tick enqueues once.
- Structured JSON logs with a request and job id. `/api/health` reports database, job backlog, dead jobs, stale sources, undelivered alerts, and monitor findings.
- The demo clock: `make demo` seeds a world and runs 45 simulated days so every screen has history; the app's clock control advances days.

## 20. Stack and hosting

- Python 3.13 everywhere (laptop, CI, host). FastAPI, psycopg 3, Pydantic 2, pytest. Raw SQL in migration files; no ORM.
- Postgres 18 everywhere. Local `make demo` starts a private Postgres in `.data/` with the installed binaries; CI uses the postgres:18 service; the hosted demo is a Docker image with Postgres inside it, fresh on every restart.
- Web app: React 18, Vite, TypeScript. Built into `web/dist` and served by FastAPI.
- MCP server (Python MCP SDK) over read-only views: "why is this account hot", "what is waiting on me", "how did this play do". It reads no money.

## 21. Not in v1

Real calendar and inbox OAuth; multi-tenant; gifting and direct mail; ad audiences; real-time website de-anonymisation; phone dialer.

## 22. Review decisions (2026-11-11)

Two fresh reviews ran before any code: one read this spec against its sources and the build checklist, one compared it with how strong teams run signal-based outbound today. Where this section and an earlier section differ, this section wins.

### 22.1 The account play state machine

Open states (the partial unique index): `proposed, accepted, researching, approving, active, engaged, meeting`.

| From | Event | To |
|---|---|---|
| (none) | play matches, holdout draw says treated | proposed |
| (none) | play matches, holdout draw says holdout | held_out (terminal at once; the account gets a hold for the measurement window, 90 days, so no other play touches it and the comparison stays clean) |
| proposed | owner accepts | accepted, and the research job is queued |
| proposed | owner skips (reason) / TTL passes | skipped / expired |
| accepted | research job starts | researching |
| researching | brief and committee done, autonomy is `research` | active (no desk sends; call, LinkedIn and email tasks for the rep) |
| researching | brief and committee done, autonomy above `research` | approving (step 1 drafts exist) |
| researching | nobody reachable for any persona | stopped (reason `no_reachable_people`) |
| approving | first step 1 message approved | active (that enrollment goes active, the others follow the calendar) |
| active | a reply labelled interested, meeting_request or question | engaged |
| active, engaged | meeting booked | meeting (all enrollments stop, reason `meeting_booked`) |
| active | every enrollment done or stopped with no positive reply | stopped (reason `sequence_finished`) |
| any open | not_interested reply | lost (reason `not_interested`) |
| any open | person stops it (reason) / kill of the play | stopped |
| meeting | opportunity created and later won / lost | won / lost |
| meeting | 120 days with no opportunity | stopped (reason `no_opportunity`) |

### 22.2 Stop first, then decide

An inbound message sets that person's enrollment to `paused` (reason `reply_received`) and every other active enrollment at the account to `paused` (reason `account_reply`), in the same transaction. Classification then decides:

- out_of_office and auto_reply: the person resumes at the same step after the return date plus one business day (default 5 business days when no date is given); the account's other enrollments resume at once.
- interested, meeting_request, question: the person is stopped (`replied_positive`); the others stay paused until the rep resolves the reply, then resume or stop by the rep's choice.
- not_now, not_interested, unsubscribe, wrong_person, bounce, left_company, referral: the person is stopped with the label as reason; the others resume unless the label also ends the account play (not_interested).
- needs review: everything stays paused until a person classifies it.

The promise "no desk send after a reply" means: no message sent by the desk to a person after an inbound touch from them, unless every inbound touch since was classified out_of_office or auto_reply. A rep's own emails and calls are touches, not desk sends.

### 22.3 Templates and the watched batch

There are no stored templates; every draft is written per person. The unit that is watched is a **play step**: `template_key = <play key>:<step index>`. The first 20 sends of a play step (and of each new version of the play's sequence) are its watched batch: 2 hard bounces or any complaint signal in the batch pauses that play step until GTM looks. Hard bounces are also attributed to the email source (finder vendor) that supplied the address, so a bad data source shows up as a source problem.

### 22.4 Legal footer and contact basis (Risk: legal, high. Counsel to confirm.)

- Every desk email ends with a footer block the copy gate requires and does not count against length or link limits: the sender's company name and postal address, a plain-text opt-out line ("Reply 'no thanks' or use this link and I won't write again"), the opt-out link, and for EU, EEA and UK recipients a link to the privacy notice that says where the data came from (GDPR Article 14).
- The one-click endpoint acts only on POST (RFC 8058); a GET shows a confirm button, so mail scanners cannot unsubscribe people. An opt-out is honoured at once and always within 2 days.
- `contact_basis` records the basis per person (`legitimate_interest` with the assessment reference for EU and UK, `consent` where a region needs it). Region rules key on the person's country. No basis where one is needed blocks the send.

### 22.5 Complaints and placement are aggregate signals

Gmail never says which message was reported. So:
- A **deliverability telemetry** adapter reads Google Postmaster Tools (domain spam rate, compliance status) per sending domain, Yahoo's complaint feedback loop and Microsoft SNDS/JMRP where enrolled, and seed-list placement tests per mailbox. Simulated in the demo. Each email carries a `Feedback-ID` header naming the play.
- Per-message complaint events exist only where a feedback loop provides them.
- Missing data is **unknown**, never zero. A domain whose spam rate is unknown for more than 7 days, or at or above 0.1%, cannot gain capacity; at 0.3% it pauses. Promotion to a higher autonomy stage is blocked while any domain the play uses is unknown.
- Bounce rate for a mailbox: hard bounces over sends in a rolling 14 days, measured from 50 sends. Warn at 1.5%, pause at 2%. For a play: over its last 200 sends; demotion at 3%.
- Tracking is off: no open pixel, no link rewriting. Plain-text email. Each sending domain has at most 3 mailboxes and its own daily cap. DMARC must align with SPF or DKIM.

### 22.6 Data the flow needs

Added to section 4: `accounts.parent_id` (a subsidiary of a customer or open opportunity is excluded), `people.phone, phone_status, phone_verified_at`, `people.is_champion` (seeded from contacts on won opportunities), `personas.angle`, `plays.positive_floor`, `plays.latency_hours`, `plays.urgent`, `messages.attempts` (each gate attempt kept), `messages.edited` (approved after a person changed the text), `sequence` steps with `job` (open, follow_up, bump, break_up), `source_runs`, `adapter_calls`, `holidays`, `region_rules`, `contact_basis`, `research_cache` (domain, kind, content, fetched_at), `sla_due_at` and `escalated_at` on replies, `heyreach_consent` on users, `suppressions.kind` gains `phone`.

### 22.7 Scoring, exactly

- **Fit** = 100 × (sum of weights of matched positive factors) ÷ (sum of all positive weights), minus excluded-factor penalties, clamped 0 to 100. ICP rules shape: `{"factors": [{"key", "field", "op": "in|between|has_any|has_none", "value", "weight"}], "excludes": [{"field", "op", "value", "reason"}], "tiers": {"A": 70, "B": 50}}`. The fit floor for any play is tier B.
- **Intent**. For each signal: `c = weight × strength × 0.5^(age_days / half_life)`; person-level signals count toward their account. `pos = Σ c` over positive types; `types = number of distinct positive types with c ≥ 1`; `mult = 1 + 0.15 × min(types − 1, 3)` (when types ≥ 1); `neg = Σ |c|` over negative types. `intent = clamp(100 × (1 − e^(−pos × mult / 40)) − neg, 0, 100)`.
- **Engagement** = min(100, 35 × positive replies in 90 days + 50 × meetings held in 90 days).
- **Priority** = round(fit^0.4 × (0.85 × intent + 0.15 × engagement)^0.6) for tier A or B, else 0.
- `account_scores.inputs` stores every input, so a stored score must reproduce exactly.

### 22.8 Speed from signal to first touch

Each play has `latency_hours` (default 48 business hours; 24 for pricing visit and new leader). Urgent plays have a 1-business-day proposal TTL and sit at the top of Today. Signal-to-first-touch is a funnel metric per play and a monitor.

### 22.9 Sources of accounts and facts

- **Account universe**: CSV or CRM import of the target account list, refreshed on a schedule; `auto_create_accounts` only for tier A fit from a signal.
- **Research**: before the brief, an AI research step may add `facts` with a `source_url` (live mode: web search tool; demo: the simulated world's pages). Cached by domain for 30 days. The brief cites facts from signals and research alike.
- **Re-enrichment**: people re-verified when older than 45 days at the moment of a send, and every 90 days for people in open account plays. Accounts' firmographics refresh every 90 days.
- **First-party signals**: `product_signup`, `closed_lost_revisit`, `event_attended`, `form_abandoned`, `job_change` (any known person who moved; `champion_moved` only when `is_champion`). Website visits stay at the account level; a de-anonymised visitor never becomes a contact.
- **Job changes need corroboration**: a move marks the person `left` only when a second source agrees or their old address hard-bounces. The person row moves to the new account (one row per human), with the move in `person_moves`.

### 22.10 Phone

People have a phone and its status. A phone waterfall (simulated) fills it for people in open account plays when a play has a call step, charged to the ledger. A `phone` suppression kind holds do-not-call numbers. Call tasks show the number.

### 22.11 What code can and cannot check in a draft

Code cannot tell which sentence states a fact. The model returns each sentence with a `kind` (`claim`, `ask`, `courtesy`) and its citations. Code enforces: every `claim` cites a fact id that exists for this account; every number and every capitalised name that is not the person, the account or our own company appears in a cited fact; at least one sentence is a cited claim. A claim mislabelled as `courtesy` is the gap this leaves, and the person who approves is the check for it. The approval screen shows each sentence beside the facts it cites.

### 22.12 Holdout and lift

- Lift is the difference in meeting rate, treated minus holdout, with a Newcombe hybrid-score 90% interval. Treated counts every account assigned to the treated arm, including skipped and expired (intention to treat).
- The page shows the minimum detectable effect at the observed base rate and the accounts still needed (80% power, 90% two-sided). Below that it says "Not enough accounts yet" with the number needed, not a lift.
- Holdout is also pooled across plays for one desk-level figure. Default `holdout_pct` is 20.

### 22.13 Approval timing

A step is scheduled only once approved. It goes to the next valid slot at or after its planned time. If approval comes more than 5 business days after the planned time, the step lapses and the enrollment ends (`done`, reason `approval_lapsed`). Step 1 is drafted at acceptance only when autonomy is above `research`.

### 22.14 Terms, once

- **Touched** (cooldown, gate rule 7): a desk send to that person in the last 90 days. Rep calls and the rep's own emails do not count.
- **Account gate**: gate rules 1, 3 and 4, plus no open account play and no holdout hold. It runs before a proposal. The full contact gate runs per person.
- **Active account play**, for attribution: any open state.
- **Attribution**: an opportunity is `sourced` when created within 90 days after a meeting from an account play; else `influenced` when the account had an open account play in the 90 days before; sourced wins.
- **SLA business hours** are the owner's, in the owner's timezone, 09:00 to 18:00.
- A play's `max_people` cannot exceed `account_max_active`; tier A accounts may run up to 5 at once when the play allows it.

### 22.15 AI jobs and their evals

AI runs in: research facts (live only), the brief, drafts, reply classification with side facts, suggested replies, call-note extraction. Each has an eval set and a code check: brief and drafts (citations exist), classification (labels, referral emails must appear verbatim in the reply), extraction (every quote appears in the notes). Model per task is configurable; default `claude-opus-5-5`, effort `low` for classification and extraction, `medium` for briefs and drafts; the evals decide whether a smaller model holds quality. Page-to-signal reading is not in v1.

### 22.16 Money, credits and cost

Credits stay in their vendor's unit and AI spend in dollars; they are never added together. Budgets are per vendor in its own unit. Launching a play shows its cost card (worst case per account: search credits, finder credits, verifier credits, AI calls in dollars) and the manager's launch approval caps it per month.

### 22.17 Hosting, Slack, uploads, login

- Host: Render free web service from the repo's Dockerfile, Postgres inside the container (fresh on each restart, sleeps after 15 idle minutes). Memory target under 400 MB, measured.
- Slack: ops alerts go to `#outbound-ops`. When an account play becomes engaged, the desk creates a channel for that account (`#acct-<domain>`), invites the owner first, and posts the reply there; hot-reply alerts @-mention the owner.
- The public demo (`PUBLIC_DEMO=1`) takes no uploads and sends nothing outside.
- `AUTH_MODE` has `demo` (acting-as menu) and `header` (identity from a trusted proxy header such as Cloudflare Access). `LIVE_SEND=1` refuses to start in `demo`.
- Erasure deletes the person, their enrollments, messages, replies, touches, facts about them, learnings quoting them, tasks and meetings; scrubs their address from crm_outbox payloads, llm_calls and audit_log details; and leaves an `email_hash` suppression.
- Integration limits are written down per adapter in `docs/INTEGRATIONS.md`.

### 22.18 Screen words

The house design checklist is copied into `docs/DESIGN-CHECKLIST.md`. Words on screens: "Comparison group (not contacted)" for the holdout, "Meetings compared with not contacted" for lift, "Needs a rewrite" for a draft that failed the checks, "Why now" for the trigger.

### 22.19 Every open state can close (re-review)

The account play states are exactly those in `migrations/0001_core.sql`: `proposed, accepted, researching, approving, active, engaged, meeting` (open) and `converted, lost, stopped, skipped, expired, held_out` (closed). There is no `drafting` and no `won`: an account play ends `converted` when an opportunity is created; the opportunity carries won or lost.

Added exits:

| From | Event | To, and the cooldown before this account can be proposed again |
|---|---|---|
| accepted, researching | research job dead, or no progress in 2 business days | stopped `research_failed`, 7 days; GTM alerted |
| approving | every enrollment ended without an approved step 1 (rejected, skipped, lapsed) | stopped `nothing_approved`, 30 days |
| engaged | 21 days since the last positive reply with no meeting | stopped `no_meeting`, 60 days |
| meeting | meeting cancelled or no-show | engaged, with a rebook task for the owner |
| meeting | opportunity created (linked by account) | converted, no cooldown (lifecycle `open_opp` blocks anyway) |
| meeting | 120 days with no opportunity | stopped `no_opportunity`, 90 days |
| any open | CRM sync turns the account `customer` or `open_opp` | stopped `became_customer` / `opportunity_elsewhere`, until lifecycle changes |
| active | sequence finished | stopped `sequence_finished`, 90 days |
| any open | not_now reply | stopped `not_now`; account hold until the date given (default 90 days) |
| proposed | skipped | 30 days; expired: 14 days |
| any open | not_interested | lost, 180 days |

Cooldowns are written as rows in `holds` with the close reason, so the account gate needs no extra rule.

**Approvals** made by the desk under `supervised` or `autonomous` count as approvals for every transition.

**Paused enrollments.** Pauses use `enrollments.pause_reason` (not `stop_reason`). When the rep has not resolved a positive reply within 3 business days, the account's other paused enrollments resume. On resume, the remaining steps keep their spacing, counted from the resume time. The 5-day approval lapse in 22.13 applies only to steps not yet approved.

**Replies that need no person.** out_of_office and auto_reply are marked handled by the classifier, so gate rule 9 does not wait 72 hours on them. Rule 9 counts only replies that need a person.

**LinkedIn and calls.** A connection acceptance is a touch, not a reply: it pauses nothing. A LinkedIn message from the person is a reply. An inbound call or email the rep logs stops that person's desk steps (`rep_in_conversation`) and counts as handled.

**A gate block at send time.** A permanent reason (suppressed, unsubscribed, invalid email, person left, lifecycle, region blocked) stops the enrollment with `gate:<rule>`. A temporary reason (hold, outside the window, no mailbox capacity, verification due) leaves it active and moves `next_at` to the next time the rule could pass; verification due queues a re-verification job.

**Inbound before outreach.** A reply from someone at the account while the play is `proposed` or `researching` is recorded and shown to the owner; the play state does not change.

**Measurement window.** Meeting rate for lift counts meetings within 60 days of the proposal, inside the 90-day holdout hold.

**Account cap.** The enrollment trigger reads `account_max_active` (3), or `account_max_active_wide` (5) when the account is tier A and the play's `max_people` is above 3.
