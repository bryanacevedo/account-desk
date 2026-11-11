# Reply classification eval

48 labelled replies, run through the real pipeline: cleaning, rules, then the model. Source of the model's answers: live calls (claude-opus-5-5, effort low).

| Measure | Result |
|---|---|
| Exact label | 45 of 48 (94%) |
| Label a person would accept (interested and meeting request, not interested and unsubscribe, treated as one) | 47 of 48 (98%) |
| Rules alone, everything else read as unclear | 12 of 48 (25%) |
| Settled by rules, no model call | 11 of 48 |
| Written by someone else (assistant, colleague) spotted | 2 of 2 |
| Attempt to instruct the system flagged | yes (r37) |
| Referral emails the model invented | 0 |

## Misses

- r31: expected interested, got meeting_request (model). "Hola, nos interesa. ¿Podemos hablar la semana que viene?"
- r36: expected interested, got meeting_request (model). "Hi, I'm Laura, Mark's executive assistant. He'd like to learn more. Could you send me some"
- r45: expected other, got question (model). "?"

## Confusion matrix (rows: expected, columns: got)

| expected \ got | auto_reply | bounce | interested | left_company | meeting_request | not_interested | not_now | other | out_of_office | question | referral | unsubscribe | wrong_person |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auto_reply | 1 |  |  |  |  |  |  |  |  |  |  |  |  |
| bounce |  | 1 |  |  |  |  |  |  |  |  |  |  |  |
| interested |  |  | 4 |  | 2 |  |  |  |  |  |  |  |  |
| left_company |  |  |  | 3 |  |  |  |  |  |  |  |  |  |
| meeting_request |  |  |  |  | 4 |  |  |  |  |  |  |  |  |
| not_interested |  |  |  |  |  | 6 |  |  |  |  |  |  |  |
| not_now |  |  |  |  |  |  | 6 |  |  |  |  |  |  |
| other |  |  |  |  |  |  |  |  |  | 1 |  |  |  |
| out_of_office |  |  |  |  |  |  |  |  | 5 |  |  |  |  |
| question |  |  |  |  |  |  |  |  |  | 4 |  |  |  |
| referral |  |  |  |  |  |  |  |  |  |  | 4 |  |  |
| unsubscribe |  |  |  |  |  |  |  |  |  |  |  | 5 |  |
| wrong_person |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
