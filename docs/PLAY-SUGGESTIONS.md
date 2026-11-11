# Plays suggested from call learnings

**Status:** spec revision 2, 2026-11-11, from Bryan's idea: "the learnings, as soon as there's a clear pattern from the learnings, should prompt play suggestions." Revision 1 was reviewed by a fresh reader against the code.
- **Blockers it found, now fixed here:**
  - industry cannot trigger a play;
  - a 2x rule fires on chance at these sizes;
  - managers cannot create plays;
  - research-stage plays can never be promoted.
- **Majors it found, now fixed here:**
  - no stored note author;
  - no date for the window;
  - the editor cannot be prefilled;
  - placeholder recordings;
  - name collisions;
  - privacy paths.

Build on a branch; it is reviewed before Bryan sees it.

## The idea

Call notes that a person marks worth learning from already become learnings: objections, competitors, reasons to buy and reasons not to, each carrying the exact words behind it (`pipeline.learn_from`, table `learnings`).

This feature watches them for a pattern. A pattern is the same reason to buy (or the same competitor) heard at enough different accounts, by more than one SDR, and clearly more common among accounts that came in on one kind of signal. When that holds, the desk proposes a new play triggered by that signal and built on that reason.

GTM engineering turns a suggestion into a draft play; a manager can set one aside. Nothing becomes live on its own.

## 1. Themes

- Learnings of kind `reason_to_buy` and `competitor` are filed under a theme (`learning_themes`): one short label for one idea. Kinds `objection` and `reason_not` are also filed, so a suggestion can show what you will hear. Kind `quote` is not filed.
- **Filing is a new LLM task, `theme`.** It sees one learning's text and the existing themes of the same kind (id and label). It returns an existing theme id, or a new label.
- Code checks the answer:
  - a returned id must exist and be of the same kind;
  - a new label must be at most 80 characters;
  - a new label must not contain the name of any person or user in the desk (checked against `people` and `users` names), nor any email address;
  - labels are unique per kind, case-insensitive.

  On a failure, the task is re-asked once; after a second failure the learning stays unfiled and an alert is logged.
- **Filing runs as a background job,** enqueued by `learn_from`, never inside the request transaction. Add a `TYPICAL_TOKENS` entry and a sim stand-in.
- **Backfill.** A CLI command, `python -m outbound themes backfill`, files every unfiled learning. `make demo` runs it after seeding.

## 2. A clear pattern (code decides)

### Data
- Each learning reaches its account through `call_notes`, then `meetings.account_id`.
- **Its date** is `call_notes.created_at`.
- **Its SDR** is the note's author. Add `call_notes.written_by`, set in `record_call_notes`. Backfill it from `marked_by` where it is null. Only users with role `sdr` count.
- **Its segment** is the signal type that started the account's play: `learnings.signal_type`, from the meeting's account play. Learnings without one count in the overall rate but belong to no segment.
- **Industry is not a segment,** because a play's trigger cannot target it (`play_editor.Trigger`).

### The rule
A theme T of kind reason_to_buy or competitor is a pattern in segment S (a signal type) when all of these hold, counting distinct accounts with a learning under T in the last 90 days:

1. T is heard at **at least 5 accounts in S**.
2. Those accounts' notes were written by **at least 2 different SDRs**.
3. **The test.** T is more common in S than among the other accounts with learnings in the window. The comparison is a one-sided Fisher exact test on the 2x2 table: accounts in S or not, against T heard or not.
   - It must pass at **alpha 0.05 divided by the number of (theme, segment) pairs tested that day** (Bonferroni).
   - Implement it in `stats.py` with no new dependency (the hypergeometric tail).
   - Show the two rates and the number of pairs tested, the same way DECISIONS 44 and the held-back comparison show their numbers.
4. **No play of any status** has `suggested_from = T`.
5. **No suggestion for T is open,** and none is `dismissed`. A `not_now` suggestion re-opens only when the theme's distinct accounts in S reach at least 1.5 times the count recorded when it was set aside, and the rule passes again.

**An open suggestion lapses** (status `lapsed`) when the daily check no longer finds the pattern.

**The thresholds** (5, 2, 90 days, 0.05, 1.5x) live as constants in one module and are shown read-only on Settings.

**The daily job:** a `PERIODIC` entry in `scheduler.py` plus a `@jobs.handler` in a module the worker imports (see `__main__.py`). The check also runs after each backfill.

## 3. The suggestion

A new LLM task, `draft_play`, receives:
- the theme label;
- the segment's signal type, with its label and its "because";
- the objection and reason_not themes heard at the same accounts (labels only);
- the catalog of signal types and personas (keys and labels).

It never receives quotes or account names.

It returns:
- a name;
- a hypothesis;
- `trigger.any_of` (one or more signal types, which must include S);
- personas;
- an angle.

Code checks:
- the trigger and personas are in the catalog, and S is among the triggers;
- the angle and hypothesis name no person, user, account or company in the desk;
- the angle passes the existing copy checks that apply to a play angle (no long dashes; the banned phrase list).

On a failure it is re-asked once with the failures named; after that, no suggestion is made and an alert is logged.

The angle may describe the theme in plainly general terms. It never applies the theme to the recipient as fact, because the drafter will still only use facts about the account. It never names or quotes a customer.

## 4. Where it shows and who can act

- **API.** `/api/play-suggestions` (list) and `/api/play-suggestions/{id}` (one). Both are enforced in the API, for manager and GTM only, with the same `need()` pattern as other gated routes.
- **The Plays page** gets a "Suggested from calls" section, rendered for those roles.
- **The side sheet** gets a new Frame kind with its own identity (see `KIND` in `sheets.tsx`). It shows:
  - the pattern in plain words and numbers: "Heard at 6 of the 11 accounts that came in on a new finance leader, against 3 of 19 elsewhere, from 3 SDRs." It also gives how many pairs were tested and that the difference passed the test;
  - the quotes it rests on, read live from `learnings` (never copied into the suggestion), each with its account, its SDR and the date, and each opening its meeting sheet;
  - the objections heard at the same accounts;
  - the drafted play.
- **"Make it a draft play"** is for GTM only, because `create_play` is GTM-only. It opens the existing play editor prefilled.
  - `PlayEditor` gains a `fromSuggestion` input, and `/plays/new?suggestion=<id>` loads the drafted fields: name, hypothesis, `trigger.any_of`, personas and angle.
  - Every other field takes the editor's defaults for a new play: sequence, max_people, latency, `holdout_pct` 20, fit tiers, `min_priority` and `within_days`.
  - `PlayIn` gains an optional `suggested_from`.
  - The play is created exactly as today: `status = 'draft'`, autonomy `draft` (DECISIONS 22), launched later under the existing rules (a different person, a monthly cap).
  - The suggestion becomes `drafted`, with the play's id.
- **"Not now"** is for manager or GTM and needs a reason.
- **"No"** is for manager or GTM and dismisses the theme for good.

Every decision goes to the audit log, without quotes.

## 5. Data (migration 0024)

- `learning_themes`: id, kind (check: the four filed kinds), label, created_at; unique (kind, lower(label)).
- `learnings.theme_id`, referencing `learning_themes`, null allowed.
- `call_notes.written_by`, referencing `users`.
- `play_suggestions`:
  - id, theme_id, segment_signal_type (references `signal_types`);
  - `evidence` jsonb, holding counts, rates, p and pairs tested, but **no quotes or names**;
  - `draft` jsonb (the drafted play fields);
  - status: open, drafted, not_now, dismissed or lapsed;
  - reason, decided_by, decided_at, play_id and accounts_at_decision;
  - created_at.
  - **Checks:**
    - one open suggestion per theme (a partial unique index);
    - decided states need decided_by and decided_at;
    - not_now needs a reason;
    - drafted needs play_id.
- `plays.suggested_from`, referencing `learning_themes`.

**Privacy.**
- `privacy.erase` already deletes learnings that mention a person. It must also delete themes left with no learnings, and the suggestions on those themes (any status, except drafted, whose play stays and has its `suggested_from` set to null).
- Theme labels may never hold personal names (checked in section 1).

## 6. AI and evals, the way this repo does them

- The two new tasks are `theme` and `draft_play`. Each gets:
  - an entry in `llm.TASKS` with its prompt hash;
  - a stand-in in `sim_llm.py`;
  - `TYPICAL_TOKENS`.
- **Evals.** File names and threshold keys must not collide with the existing `run_suggest.py` and `suggest_*`:
  - `evals/run_themes.py`: about 30 learnings worded differently, with the expected grouping. Report pairwise agreement and invented-name failures.
  - `evals/run_draft_play.py`: about 15 patterns.
    - Code checks catalog-only triggers and personas, and no names.
    - The judge (`evals/judge.py`) checks that the hypothesis and angle follow from the theme and do not apply it to the recipient as fact.
  - Threshold keys start with `themes_` and `draft_play_`. The safety keys (catalog-only, no names) are at 1.0.
  - **The cases are written by an agent that has not read the code** (DECISIONS 45). They are provided in `evals/cases/themes_v1.jsonl` and `evals/cases/draft_play_v1.jsonl`.
- **Recordings.** `tests/test_evals.py` requires real recordings for every task's current prompt. Run the two new evals live once (`ANTHROPIC_LIVE=1`; the key is in `.env`; expected cost is a few dollars) and commit the recordings and reports. If a live run is impossible, do not add placeholder recordings; say so in the report, and leave the task out of the recorded-task list with a comment saying why.

## 7. The demo, honestly

The simulator draws call-note reasons with no link to the account's signal (`sim/runner.py`), so today no pattern can pass the rule except by chance. Change the simulation so that a few reasons truly depend on the signal that brought the account in. For example:
- accounts that came in on a new finance leader say "Audit flagged revenue recognition on usage contracts" more often;
- accounts that came in on hiring in finance operations say "Close team spends a week reconciling usage by hand" more often.

Write this down in the simulation code and in README "What is real and what is simulated" as a planted relationship, so a reader knows the demo's pattern was put there. Make the notes come from more than one SDR. Make sure meetings carry their account play, so learnings have a segment.

After `make demo`, at least one suggestion must be open because it passes the rule above. Do not lower thresholds to get one. Phrase the sim's call-note lines with some variation, so the theming task has real work to do.

## 8. Tests

The build adds tests for:
- the Fisher test against known values;
- the rule:
  - passes at the thresholds and fails just under each one;
  - Bonferroni changes the verdict;
  - lapsing;
  - not_now re-opening at 1.5x;
  - dismissed never re-opening;
- the API role checks;
- prefill;
- privacy erase;
- the migration's checks;
- the demo producing a suggestion.

The full suite stays green.

## Not in v1

- Changing an existing play's angle from objections.
- Auto-launching anything.
- Industry or other non-signal segments.
- Learnings from sources other than marked call notes.
- Clustering by embeddings.
