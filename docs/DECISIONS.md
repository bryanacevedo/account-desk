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
