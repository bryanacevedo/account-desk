# Reply classification eval

148 labelled replies (48 original, 100 written independently of the code), through the real pipeline: cleaning, rules, then the model. Answers from live calls (claude-opus-5-5, effort low).

| Measure | Result |
|---|---|
| Label a careful person would accept | 147 of 148 (99%, 90% interval 97 to 100%) |
| Exact label | 140 of 148 (95%, 90% interval 91 to 97%) |
| Stop requests read as stop requests | 13 of 13 (100%, 90% interval 83 to 100%) |
| Positive replies kept positive | 53 of 53 (100%, 90% interval 95 to 100%) |
| Rules alone, everything else read as unclear | 32 of 148 (22%, 90% interval 17 to 28%) |
| Settled by rules, no model call | 27 of 148 |
| Side fact: same person right | 86 of 87 (99%, 90% interval 95 to 100%) |
| Side fact: instructs system right | 5 of 6 (83%, 90% interval 50 to 96%) |
| Side fact: return date right | 5 of 6 (83%, 90% interval 50 to 96%) |
| Side fact: referral name right | 12 of 12 (100%, 90% interval 82 to 100%) |
| Side fact: new company right | 1 of 1 (100%, 90% interval 27 to 100%) |
| Side fact: language right | 84 of 84 (100%, 90% interval 97 to 100%) |
| Referral emails the model invented | 0 |

## By category

| Category | Accepted |
|---|---|
| original set | 47 of 48 (98%, 90% interval 91 to 100%) |
| lowercase | 12 of 12 (100%, 90% interval 82 to 100%) |
| clean_positive | 1 of 1 (100%, 90% interval 27 to 100%) |
| quoted_thread | 3 of 3 (100%, 90% interval 53 to 100%) |
| mobile_signature | 3 of 3 (100%, 90% interval 53 to 100%) |
| tiny_answer_on_top | 3 of 3 (100%, 90% interval 53 to 100%) |
| multilingual | 28 of 28 (100%, 90% interval 91 to 100%) |
| spanish | 8 of 8 (100%, 90% interval 75 to 100%) |
| signature | 1 of 1 (100%, 90% interval 27 to 100%) |
| on_behalf | 3 of 3 (100%, 90% interval 53 to 100%) |
| assistant | 3 of 3 (100%, 90% interval 53 to 100%) |
| sarcasm | 4 of 4 (100%, 90% interval 60 to 100%) |
| positive_under_sarcasm | 1 of 1 (100%, 90% interval 27 to 100%) |
| prompt_injection | 6 of 6 (100%, 90% interval 69 to 100%) |
| addressed_to_ai | 4 of 4 (100%, 90% interval 60 to 100%) |
| german | 6 of 6 (100%, 90% interval 69 to 100%) |
| legal_signature | 2 of 2 (100%, 90% interval 42 to 100%) |
| mentions_colleague_no_referral | 1 of 1 (100%, 90% interval 27 to 100%) |
| short | 3 of 3 (100%, 90% interval 53 to 100%) |
| time_zone | 5 of 5 (100%, 90% interval 65 to 100%) |
| calendar_link | 1 of 1 (100%, 90% interval 27 to 100%) |
| portuguese | 3 of 3 (100%, 90% interval 53 to 100%) |
| html_leftovers | 2 of 2 (100%, 90% interval 42 to 100%) |
| french | 4 of 4 (100%, 90% interval 60 to 100%) |
| mixed_language | 1 of 1 (100%, 90% interval 27 to 100%) |
| hidden_signature_instruction | 1 of 1 (100%, 90% interval 27 to 100%) |
| passive_aggressive | 4 of 4 (100%, 90% interval 60 to 100%) |
| skeptical | 1 of 1 (100%, 90% interval 27 to 100%) |
| technical | 1 of 1 (100%, 90% interval 27 to 100%) |
| italian | 4 of 4 (100%, 90% interval 60 to 100%) |
| two_questions | 1 of 1 (100%, 90% interval 27 to 100%) |
| compliance | 2 of 2 (100%, 90% interval 42 to 100%) |
| one_word | 6 of 6 (100%, 90% interval 69 to 100%) |
| pricing | 3 of 3 (100%, 90% interval 53 to 100%) |
| dutch | 3 of 3 (100%, 90% interval 53 to 100%) |
| integration | 1 of 1 (100%, 90% interval 27 to 100%) |
| data_residency | 1 of 1 (100%, 90% interval 27 to 100%) |
| no_thanks_but_later | 1 of 1 (100%, 90% interval 27 to 100%) |
| timing | 6 of 6 (100%, 90% interval 69 to 100%) |
| explicit_date | 1 of 1 (100%, 90% interval 27 to 100%) |
| renewal | 1 of 1 (100%, 90% interval 27 to 100%) |
| mentions_role_no_referral | 1 of 1 (100%, 90% interval 27 to 100%) |
| hostile | 4 of 4 (100%, 90% interval 60 to 100%) |
| built_in_house | 1 of 1 (100%, 90% interval 27 to 100%) |
| fake_system_message | 1 of 1 (100%, 90% interval 27 to 100%) |
| mentions_bot | 1 of 1 (100%, 90% interval 27 to 100%) |
| referral_with_email | 7 of 7 (100%, 90% interval 72 to 100%) |
| referral_no_email | 4 of 4 (100%, 90% interval 60 to 100%) |
| forwarded_chain | 1 of 1 (100%, 90% interval 27 to 100%) |
| first_name_only | 1 of 1 (100%, 90% interval 27 to 100%) |
| cc | 1 of 1 (100%, 90% interval 27 to 100%) |
| written_by_other | 5 of 5 (100%, 90% interval 65 to 100%) |
| left_with_referral | 2 of 2 (100%, 90% interval 42 to 100%) |
| new_company_stated | 2 of 2 (100%, 90% interval 42 to 100%) |
| auto_generated | 2 of 2 (100%, 90% interval 42 to 100%) |
| generic_inbox | 2 of 2 (100%, 90% interval 42 to 100%) |
| ooo_with_date | 7 of 7 (100%, 90% interval 72 to 100%) |
| date_format_dmy | 1 of 1 (100%, 90% interval 27 to 100%) |
| date_format_mdy | 1 of 1 (100%, 90% interval 27 to 100%) |
| ooo_no_date | 3 of 3 (100%, 90% interval 53 to 100%) |
| date_format_dotted | 1 of 1 (100%, 90% interval 27 to 100%) |
| ooo_with_delegate | 1 of 1 (100%, 90% interval 27 to 100%) |
| date_written_out | 2 of 2 (100%, 90% interval 42 to 100%) |
| vague_return | 1 of 1 (100%, 90% interval 27 to 100%) |
| unsubscribe_vs_not_interested | 1 of 1 (100%, 90% interval 27 to 100%) |
| gdpr | 2 of 2 (100%, 90% interval 42 to 100%) |
| legal | 1 of 1 (100%, 90% interval 27 to 100%) |
| legal_threat | 1 of 1 (100%, 90% interval 27 to 100%) |
| no_referral | 1 of 1 (100%, 90% interval 27 to 100%) |
| mistaken_identity | 1 of 1 (100%, 90% interval 27 to 100%) |
| mentions_team_no_referral | 1 of 1 (100%, 90% interval 27 to 100%) |
| bounce_hard | 4 of 4 (100%, 90% interval 60 to 100%) |
| gmail_style | 1 of 1 (100%, 90% interval 27 to 100%) |
| exchange_style | 1 of 1 (100%, 90% interval 27 to 100%) |
| bounce_mailbox_full | 1 of 1 (100%, 90% interval 27 to 100%) |
| postfix_style | 1 of 1 (100%, 90% interval 27 to 100%) |
| bounce_dns | 1 of 1 (100%, 90% interval 27 to 100%) |
| delivery_delay_not_failure | 1 of 1 (100%, 90% interval 27 to 100%) |
| ticket_created | 1 of 1 (100%, 90% interval 27 to 100%) |
| unmonitored_inbox | 1 of 1 (100%, 90% interval 27 to 100%) |
| received_confirmation | 1 of 1 (100%, 90% interval 27 to 100%) |
| challenge_response | 1 of 1 (100%, 90% interval 27 to 100%) |
| ambiguous | 1 of 1 (100%, 90% interval 27 to 100%) |
| misdirected_reply | 1 of 1 (100%, 90% interval 27 to 100%) |
| reaction_notification | 1 of 1 (100%, 90% interval 27 to 100%) |
| data_request_no_stop | 1 of 1 (100%, 90% interval 27 to 100%) |

## Misses

- r45: expected other, got question (model). "?"

## Confusion matrix (rows: expected, columns: got)

| expected \ got | auto_reply | bounce | interested | left_company | meeting_request | not_interested | not_now | other | out_of_office | question | referral | unsubscribe | wrong_person |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auto_reply | 5 | 1 |  |  |  |  |  |  |  |  |  |  |  |
| bounce |  | 7 |  |  |  |  |  |  |  |  |  |  |  |
| interested |  |  | 11 |  | 2 |  |  |  |  | 1 |  |  |  |
| left_company |  |  |  | 10 |  |  |  |  |  |  |  |  |  |
| meeting_request |  |  |  |  | 13 |  |  |  |  |  |  |  |  |
| not_interested |  |  |  |  |  | 15 |  |  |  |  |  |  |  |
| not_now |  |  |  |  |  |  | 15 |  |  |  |  |  |  |
| other | 1 |  | 1 |  |  |  |  | 2 |  | 2 |  |  |  |
| out_of_office |  |  |  |  |  |  |  |  | 15 |  |  |  |  |
| question |  |  |  |  |  |  |  |  |  | 13 |  |  |  |
| referral |  |  |  |  |  |  |  |  |  |  | 13 |  |  |
| unsubscribe |  |  |  |  |  |  |  |  |  |  |  | 13 |  |
| wrong_person |  |  |  |  |  |  |  |  |  |  |  |  | 8 |
