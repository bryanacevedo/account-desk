# Plays suggested from call learnings

**Status:** spec, 2026-11-11, from Bryan's idea: "the learnings, as soon as there's a clear pattern from the learnings, should prompt play suggestions." To be built on a branch, reviewed, then shown to Bryan.

## The idea in one paragraph

SDRs already write call notes, and a person marks the ones worth learning from. The desk then pulls out objections, competitors, reasons to buy and reasons not to buy, each with the exact words from the notes behind it (`pipeline.learn_from`, table `learnings`). Today those learnings sit in a list on Results.

This feature watches them for a pattern: the same reason to buy, said at enough different accounts, by more than one SDR, and concentrated in one kind of account. When a pattern is clear, the desk proposes a new play built on it.

A manager or GTM engineer reads the evidence and turns the suggestion into a draft play in the existing play editor, or sets it aside. A suggestion never becomes a live play on its own.

## How it works

1. **Themes.** Learnings are worded differently on every call, so each new learning is filed under a theme, a short label for one idea such as "audit flagged revenue recognition on usage contracts".
   - The model files it, picking an existing theme of the same kind or naming a new one. Code checks the answer: a picked theme must exist and be of the same kind.
   - The model sees only the learning's text and the list of existing themes.
   - Filing happens when learnings are extracted, as one extra task in `llm.TASKS` ("theme").
   - Learnings already in the database are filed once by a backfill.

2. **A clear pattern. Code decides, never the model.** A theme is a pattern when all of these hold:
   - it appears at **at least 5 distinct accounts** in the last **90 days**;
   - in notes written by **at least 2 different SDRs**;
   - it is **concentrated in a segment** that can trigger a play. The segment is the signal type that started the account's play (`learnings.signal_type`) or the account's industry. The theme's rate in that segment must be at least **2 times** its rate across all accounts with learnings, with at least **4 accounts** in the segment;
   - no live or draft play already came from this theme, and no open suggestion exists for it.

   The thresholds live in one place and are shown on Settings (read-only is fine for v1). The kinds that make a play are reason to buy and competitor. Objections and reasons not to buy are not suggestions on their own; they appear inside a suggestion as "what you will hear".

3. **The suggestion.** The model drafts the play from the pattern only. It returns:
   - a name and a hypothesis;
   - a trigger, chosen from the signal types in `signal_types`;
   - the personas to reach, chosen from the personas that exist;
   - an angle.

   Code rejects any trigger or persona that is not in the catalog. The angle may use the theme in plainly general terms ("teams like yours often find..."). It must never name another customer or quote one, because a call note is private. This is the same line the claim checker draws. A failing draft is rewritten once, then the suggestion is dropped and logged.

4. **Where it shows.**
   - The Plays page gets a "Suggested from calls" section, visible to manager and GTM only.
   - Each suggestion opens a side sheet, with the usual Frame and its own kind identity. The sheet shows:
     - the pattern in numbers: the accounts, the SDRs and the segment rate against the overall rate;
     - every quote it rests on, verbatim, with the account, the SDR and the date, each opening its meeting sheet;
     - the objections heard at the same accounts;
     - the drafted play.

5. **What a person can do.**
   - **"Make it a draft play"** opens the existing play editor, prefilled. The play is created as `status = 'draft'` at the lowest autonomy stage (`research`, "SDR writes everything") with the standard holdout. Launching goes through the existing launch rules: a different person launches it, as `plays` already enforces.
   - **"Not now"** asks for a reason. The suggestion comes back only if the pattern grows by half.
   - **"No"** dismisses the theme for good.

   Every decision is written to the audit log.

6. **Measured.** A play created from a suggestion records the theme it came from (`plays.suggested_from`). Its held-back comparison works like any other play's. Nothing new is claimed about it.

## Data

New migration (0024 or the next free number):
- `learning_themes`: id, kind, label, created_at.
- `learnings.theme_id`.
- `play_suggestions`, holding:
  - id and theme_id;
  - the segment, as kind and value;
  - the evidence counts as jsonb;
  - the drafted play as jsonb;
  - status: open, drafted, not_now or dismissed;
  - reason, decided_by, decided_at and created_at;
  - the size the pattern had when the suggestion was decided.
- `plays.suggested_from`.

Constraints in the database, the way this repo does it:
- at most one open suggestion per theme;
- a decided suggestion has a decider and a time;
- not_now has a reason.

A background job (the existing `jobs` and `scheduler`) re-checks patterns daily and after each `learn_from`.

## AI and evals, the way this repo does them

- Two new LLM tasks: `theme` and `suggest_play`. Each needs:
  - a stand-in in `sim_llm.py`, so the demo runs without a key;
  - prompt hashes, so CI catches an unrecorded prompt change.
- Evals with recorded answers, in the shape of `evals/run_*.py`:
  - **theming:** about 30 learnings worded differently, with the expected grouping. Report pairwise agreement.
  - **suggestions:** about 15 patterns. Code checks that the trigger and personas are in the catalog. The judge (`evals/judge.py`) checks that every claim in the hypothesis and angle traces to the quotes, and that no customer is named or quoted.
  - Floors go in `evals/thresholds.json`; the safety ones (no customer named, catalog-only trigger) sit at 100%.
- Live runs need the Anthropic key in `.env`. Record them once live. If you cannot run live, ship the sim stand-ins and recorded-answer placeholders, and say so plainly in the report. Never fake a recording.

## Demo

The demo's seeded learnings already repeat. "Audit flagged revenue recognition on usage contracts" shows up at 7 accounts, and "Board wants clean usage revenue by next quarter" at 9. After the seed, at least one suggestion should be open, and it must pass the pattern rules for real: do not lower the thresholds to force one. If none qualifies, adjust the seed so a pattern exists honestly, and say how.

## Not in v1

- Changing an existing play's angle from objections.
- Auto-launching anything.
- Learnings from sources other than marked call notes.
- Clustering by embeddings.
