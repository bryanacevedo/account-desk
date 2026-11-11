# Eval cases v2: coverage

## replies_v2.jsonl (100)

| Category | Count |
|---|---|
| interested | 8 |
| meeting_request | 9 |
| question | 9 |
| not_now | 9 |
| not_interested | 9 |
| referral | 9 |
| left_company | 7 |
| out_of_office | 10 |
| unsubscribe | 8 |
| wrong_person | 6 |
| bounce | 6 |
| auto_reply | 5 |
| other | 5 |
| multilingual (es 8, de 6, fr 4, it 4, nl 3, pt 3; 1 mixed es/en) | 28 |
| prompt injection (instructs_system true) | 6 |
| written by someone else, not bounce or auto_reply (same_person false) | 8 |
| referral with email / without email | 7 / 4 |
| out of office with date / without date | 7 / 3 |
| one-word replies | 6 |
| sarcasm / hostile / passive-aggressive | 4 / 4 / 4 |
| quoted thread or forward with a tiny answer on top | 4 |
| GDPR requests / legal threat | 2 / 1 |
| new company stated | 2 |

## drafts_v2.jsonl (30)

| Category | Count |
|---|---|
| open / follow_up / bump / break_up | 10 / 5 / 4 / 4 |
| LinkedIn connect (all with a character limit) / message | 4 / 3 |
| only one public fact | 5 |
| private facts plus one public fact | 4 |
| only private facts | 1 |
| many facts (8+) with noise | 2 |
| exact numbers or dates | 5 |
| conflicting facts | 2 |
| instruction inside a fact | 2 |
| referral fact | 2 |
| non-English person or company names | 8 |
| wrong-buyer title | 1 |
| follow-up with nothing new | 1 |

## briefs_v2.jsonl (14)

| Category | Count |
|---|---|
| two facts only | 1 |
| 10+ facts with noise | 1 |
| numbers and dates | 6 |
| contradictory facts | 2 |
| instruction inside a fact | 1 |
| unrelated to finance | 2 |
| non-English market (pt, de, es/en) | 3 |
| speculation bait (resignation, layoffs, acquisition rumour, exec plus tool change) | 4 |

## suggest_v2.jsonl (30)

| Category | Count |
|---|---|
| question / meeting_request / interested / referral / not_now | 9 / 7 / 6 / 4 / 4 |
| pricing questions | 4 |
| integration questions | 3 |
| security or compliance questions | 3 |
| meeting acceptance with a day or time / without | 5 / 2 |
| time zones | 3 |
| send more info | 3 |
| two questions in one reply | 5 |
| not now with a date | 3 |
| hostile but interested | 2 |
| multilingual (es, pt, fr, de, nl) | 7 |
| prompt injection | 2 |

## extract_v2.jsonl (20)

| Category | Count |
|---|---|
| nothing worth learning (allow_empty) | 5 |
| competitor named, misspelled or uncertain | 8 |
| competitor mentioned only as not used or not for billing | 3 |
| price objection | 4 |
| timing objection | 3 |
| security or compliance objection | 3 |
| switching cost | 4 |
| verbatim quote (one long) | 10 |
| Spanish notes / French call translated | 2 / 1 |

## Approach to realism

Each reply was written as it would land in an inbox, with the noise a parser must survive: quoted threads, forwarded headers, legal footers, mobile signatures, HTML fragments and bounce diagnostics in the formats of different mail systems. Hard cases sit next to easy ones on purpose, so a classifier is tested on near-neighbours (unsubscribe versus not_interested, left_company with a referral, a delivery delay that is not a bounce) and on injected instructions that try to change the label. Generation cases bait the specific failures that hurt in sales: citing private signals, rounding exact figures, turning a rumour or resignation into a story, and inventing prices, integrations or dates.
