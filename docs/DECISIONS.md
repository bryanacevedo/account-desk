# Decisions

Each entry: what was decided, why, and what it costs. Newest last.

1. **The unit of work is an account in a play, never a contact in a list.** Proposals, the calendar, caps and stops all work at the account. Cost: a team that wants to blast a list cannot use this.

2. **Python, FastAPI and plain SQL, no ORM.** The portfolio needs Python for AI-engineering roles, and plain SQL keeps every guarantee visible in one migration file. Cost: no model-level validation; Pydantic covers the API edge.

3. **Postgres everywhere, real Postgres in tests.** A stand-in database hid a JSON bug for all of a previous build's first version. Tests create and drop their own database. Cost: running tests needs Postgres installed or the CI service.

4. **No separate invariant layer (Bryan left the call to Claude, 2026-11-11).** What Postgres can refuse, it refuses: CHECK constraints, partial unique indexes and a trigger on the message status. What it cannot (time, other systems, absence) are monitors that alert and never fix. Cost: the trigger duplicates part of the Python gate; the Python gate exists to explain a block, the trigger to make it impossible.

5. **Stop first, classify second.** A reply pauses the person and their colleagues in the same transaction it is stored in. Classification can be slow or wrong without a send slipping through. Cost: an out-of-office briefly pauses the whole account.

6. **The model returns structure, code decides.** Drafts come back as sentences labelled claim, ask or courtesy, each claim with fact ids. Labels come from a fixed list. A referral's email counts only if it is in the reply's text. Cost: a claim the model mislabels as courtesy passes the code check; the approval screen highlights claims so the SDR can see the difference.

7. **Tracking data triggers plays but is never cited.** Website visits, intent, product sign-ups, social engagement and event attendance never reach the drafter, and the copy check fails a draft that cites one. Cost: a weaker opening line on accounts whose only signal is a visit.

8. **Complaint data is unknown until a provider reports it.** Gmail reports domain-level spam rates only above a volume threshold. Unknown never counts as zero: a domain with unknown complaint data cannot gain capacity, and no play can be promoted while it sends from one. Cost: new domains ramp slower.

9. **A comparison group per play, intention to treat.** A deterministic 20% of matched accounts are never contacted and held for 90 days. Treated counts every account offered to an SDR, including skipped and expired ones. The page shows the sample still needed instead of a lift it cannot support. Cost: 20% of good accounts wait.

10. **Autonomy is earned and demoted automatically.** Promotion needs 50 person approvals with 90% unedited, no complaint, under 2% bounces and known complaint data, and a manager. Cost: plays start slow on purpose.

11. **LinkedIn and calls are SDR tasks by default.** LinkedIn's terms prohibit automation and senders are real people's accounts. Cost: more manual steps.

12. **Each paid call is wrapped by the caller, not the adapter.** The ledger row is written in the same transaction as the work, in the vendor's unit; credits and dollars are never added together. Cost: an adapter cannot be called without the spend wrapper, by design.

13. **SDR, not rep (Bryan, 2026-11-11).** One word for the person who works the accounts, in the code, the database and the screens.

14. **Invented company marks and photo avatars (Bryan, 2026-11-11).** Every company gets a generated mark from its domain. People show their profile photo when the enrichment vendor provides one (stock portraits in the demo), and initials otherwise. The photo is a URL, never stored bytes, and is erased with the person.

15. **Inbox placement is measured, not assumed (2026-11-11, after Bryan asked how placement is covered).** A weekly seed test per mailbox at Gmail and Outlook records inbox, spam and missing. Under 80% at either holds the mailbox at 10 a day, under 50% pauses it, and a test older than 10 days counts as unknown, which also holds it. A mailbox replying at under half its peers' rate on the same plays raises an alert and asks for a seed test, since tracking is off and nothing else would show it. The thresholds are our defaults in settings, not industry figures. Cost: a seed-test vendor, and mailboxes held while a test is missing.

16. **LinkedIn and calls are channels, not reminders (2026-11-11, after the layer review).** Still done by hand (decision 11), but the desk drafts LinkedIn notes through the same copy checks as email, a connect note has a character cap (setting, 200 by default; free accounts allow fewer), and sending one goes through the database's send guard, so a held-back account, a stopped play or an opt-out is refused as for email. The SDR approves a note by sending it, so notes never enter the email approvals queue. Every outcome is a touch: connect sent, accepted, message sent, LinkedIn reply, and four call outcomes. Per spec 22.19 an accepted connection pauses nothing, and a LinkedIn message from the person is a reply. One call we extended: a call where they spoke means the SDR is in the conversation, so the desk's own steps for that person stop (22.19 names inbound calls; an outbound call that connects is the same conversation). Guarantee 20, no email after engaging on another channel in the same play, is now in the send trigger. Cost: SDRs record outcomes by hand until a LinkedIn tool's webhook is connected.

17. **A play closes the moment its last person stops**, instead of waiting for the six-hourly sweep, except on the reply path, where the reply's outcome decides what the play becomes. Found because the slow-first-touch alert caught a play left in approving with nobody in it.

18. **Deals arrive only by reading the CRM (2026-11-11, after the layer review).** A cursor-based read of changed deals is the one way an opportunity enters the desk; amounts, stages, closes and loss reasons update on every read. Only deals lost on timing come back as a revisit signal. The demo's CRM is simulated the same way: deals are opened by sales after meetings, by sales on its own, and from inbound demo requests, at held-back accounts too.

19. **Credit needs cause (2026-11-11, after Bryan asked how trustworthy attribution is).** Sourced: a meeting from a treated play, not an inbound request, booked after the play's first outreach and within the 90 days before the deal, and not a no-show or cancelled. Influenced: a treated play that actually reached the account in those 90 days. A play that never contacted anyone gets nothing. Attribution is recomputed when the deal or its meeting changes. The comparison with the held-back group counts any meeting or deal at the account the same way in both groups, and is shown for deals as well as meetings. Cost per meeting is this month's spend over this month's meetings.

20. **People who come from replies are acted on, not handed over.** A referral becomes a person, a citable fact ("X suggested speaking with Y") and an enrollment when it can; when it cannot, the SDR's task says why. Someone who left becomes a job-change signal at the company they named, and their role is refilled from people on record or by search.

21. **No account is created automatically.** The `auto_create_accounts` setting was never read; it is removed. Accounts come from the CRM or an import, and a person adds one from an unmatched signal. Cost: a click per new company, in exchange for no account list filled by noise.

22. **A real desk starts careful.** `init` refuses a database with users, creates plays as drafts in the draft stage with the team's own legitimate-interest reference, and sending domains start unauthenticated until the DNS check reads them. The DNS check is the first live adapter (DNS-over-HTTPS, no new dependency); blocklists stay "not checked" until a vendor key exists, never "clean".

23. **Guarantee 8 is in the database.** The send trigger refuses an email past the mailbox's cap for the day or the domain's, and a mailbox whose cap was not set today; the sending code sets it under the row lock it already took. A cap refusal reschedules; it never stops the person.

24. **The MCP server is read-only by construction.** Five tools, each in a read-only transaction, none returning money; built on the official MCP Python SDK, version 2.

25. **The footer is two short lines, and says "unsubscribe" (Bryan, 2026-11-11).** Company and postal address, then "To stop hearing from us, reply "unsubscribe" or use" a short link (`/u/<id>-<12 characters>`); links in emails already sent keep working. The first footer offered "reply 'no thanks'" as the way out, and I briefly made a "no thanks" reply an opt-out to match it. Bryan: "If someone says no thanks that's literally not interested." The copy was wrong, not the reading: "no thanks" is not interested (the play ends, the account rests), and only an unsubscribe request blocks all future email. The mailto unsubscribe is offered only when a real mailbox receives it (`UNSUBSCRIBE_MAILTO`). Risk: legal; counsel to confirm.

26. **Owners come from the CRM.** A reassignment moves the account, its open play, open tasks and booked meetings to the new SDR; sequences already under way finish from the original sender, so a thread never changes voice; an owner who is not an SDR on the desk moves nothing and the manager is told.

27. **A play launches with a monthly cap (SPEC 22.16).** The manager sets it from the cost card at launch, per vendor in credits and AI in cents. Every charge is tagged with the play it was for; at the cap the play takes no new accounts until next month and paid work waits a day instead of failing.

28. **A live desk never acts on simulated data.** In live mode every vendor without a key is replaced by one that refuses (paid lookups and sends wait, and the team is told) or answers unknown (no spam rate, no seed test, no delivered alert). Found by the second layer review: the simulated verifier would have marked every real address invalid.

29. **Fit is judged on what is known.** A field the desk has no data for is left out of the score instead of counting as a miss; below 60% of the profile known, fit is not judged. Imports carry region (from the country), revenue band and technologies, and GTM edits and publishes the profile, which rescores every account.

30. **More guarantees live in the database.** The send trigger now also refuses an email to someone who replied since their sequence started (guarantee 6). Customers are never downgraded by a lost expansion or a blank re-import. A live play's trigger, sequence, people and held-back share change only after a manager pauses it.

31. **Measurement counts causes once.** The held-back comparison counts each account once, in the group it was first put in; the watched first batch counts the first 20 sends of each step version, however late a bounce arrives; an email an SDR writes in a research-stage play is outreach.

32. **Administration belongs to managers.** Managers add people, change roles (never removing the last manager) and remove someone by naming the SDR who takes their accounts, plays, tasks and meetings; their mailboxes retire and anyone mid-sequence continues from the successor's mailbox. Sending domains start unauthenticated until DNS checks them; a domain carries at most three mailboxes; pausing or retiring needs a reason.

33. **Drafts are evaluated on the real path, graded by code, and read by a person.** The eval found that drafts did not know the sender's company and were never told the limits they are checked against; both now travel with every request, and a sentence naming the prospect's company is a claim that needs a source, whatever the model labels it.
