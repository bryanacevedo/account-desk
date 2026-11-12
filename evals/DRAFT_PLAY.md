# Suggested-play eval

15 patterns written independently of the code, drafted through the desk's own path (catalog without private signals, code checks, one rewrite). Graded by code and by a Claude Sonnet 5.5 judge (15 judged).

| Check | Result |
|---|---|
| Offered and passes every check | 11 of 15 (73%, 90% interval 52 to 87%) |
| Withheld after failing the code checks twice | 0 of 15 (0%, 90% interval 0 to 15%) |
| Code: every trigger and persona from the catalog, the segment among the triggers | 15 of 15 (100%, 90% interval 85 to 100%) |
| Code: no name the case forbids | 15 of 15 (100%, 90% interval 85 to 100%) |
| Fit: triggers within what the case allows | 15 of 15 (100%, 90% interval 85 to 100%) |
| Fit: personas within what the case allows | 3 of 15 (20%, 90% interval 8 to 41%) |
| Judge: follows | 12 of 15 (80%, 90% interval 59 to 92%) |
| Judge: not as fact | 14 of 15 (93%, 90% interval 75 to 98%) |
| Judge: respects case | 15 of 15 (100%, 90% interval 85 to 100%) |

## Every play

**play_01** (new_exec, Month-end close slowed by manual usage reconciliation): passes

- Name: Month-end close slowed by manual usage reconciliation
- Hypothesis: Accounts with a new finance leader raise this on first calls: month-end close is slowed by reconciling usage by hand.
- Angle: Ask the new finance leader whether usage reconciliation is part of what they are reviewing in the close. Ask how their team reconciles usage at month end today, and offer to share how other finance teams changed that process.
- Trigger: new_exec; personas: cfo, controller, billing_ops

**play_02** (hiring_function, Invoices carry wrong usage quantities, causing disputes): fails follows

- Name: Invoices carry wrong usage quantities, causing disputes
- Hypothesis: Accounts hiring in finance operations raise this on first calls: invoices go out with wrong usage quantities and customers dispute them.
- Angle: Ask whether usage quantities on invoices ever get disputed by customers and how they catch errors before invoices go out. Offer to share how other finance teams stopped those disputes.
- Trigger: hiring_function; personas: billing_ops, controller, revops
- follows: The angle adds an unsupported claim: "Offer to share how other finance teams stopped those disputes" implies a result that the theme does not support.

**play_03** (pricing_change, Launching usage-based pricing on a subscription-only billing tool): fails personas_allowed, not_as_fact

- Name: Launching usage-based pricing on a subscription-only billing tool
- Hypothesis: Accounts that changed their pricing model raise this on first calls: they are launching usage-based pricing on a billing tool built only for subscriptions.
- Angle: Ask how their billing tool is handling the new usage-based pricing and whether any of it is being worked around by hand. Ask what would worry them about changing billing systems mid-launch, and offer to share how other finance teams approached that move.
- Trigger: pricing_change; personas: billing_ops, controller, revops
- not_as_fact: The hypothesis asserts the theme as the recipient's situation: "they are launching usage-based pricing on a billing tool built only for subscriptions."

**play_04** (competitor_review, Meterline): passes

- Name: Meterline
- Hypothesis: Accounts reviewing a competitor raise this on first calls: Meterline.
- Angle: Open without naming what we saw. Ask how their finance team is weighing billing options this year and whether Meterline is one they are looking at.
- Trigger: competitor_review; personas: controller, billing_ops, cfo

**play_05** (tech_removed, Chargewise): passes

- Name: Chargewise
- Hypothesis: Accounts that dropped a billing tool we replace bring up Chargewise on first calls.
- Angle: Ask how they are handling billing today and whether Chargewise is on their list as they look at options. Offer to share what other finance teams weighed when they made the same choice.
- Trigger: tech_removed; personas: billing_ops, controller, revops

**play_06** (hiring_function, Spreadsheets for usage billing): passes

- Name: Spreadsheets for usage billing
- Hypothesis: Accounts hiring in finance operations raise this on first calls: usage billing is run in spreadsheets.
- Angle: Ask how their team handles usage billing today and whether spreadsheets are part of it. Ask what the new finance operations hires will spend most of their time on.
- Trigger: hiring_function; personas: billing_ops, controller, revops

**play_07** (new_exec, In-house billing system maintained by engineering): passes

- Name: In-house billing system maintained by engineering
- Hypothesis: Accounts with a new finance leader raise this on first calls: billing runs on an in-house system that engineering maintains.
- Angle: Ask how billing changes get made today and who owns them between finance and engineering. Ask whether engineering would want a say in any review of the billing stack.
- Trigger: new_exec; personas: cfo, controller, billing_ops

**play_08** (funding, Acme Robotics needs audit-ready revenue reports before their Series C): fails personas_allowed, follows

- Name: Audit-ready revenue reports before the next funding round
- Hypothesis: Accounts that recently raised a round raise this on first calls: they need audit-ready revenue reports before their next round.
- Angle: Ask how ready their revenue reports would be if investors asked for an audit-ready view before the next round. Offer to share how other finance teams prepared for that.
- Trigger: funding; personas: cfo, controller, revops
- follows: The angle adds an unsupported claim: "Offer to share how other finance teams prepared for that" implies a capability or proof content the theme does not support.

**play_09** (pricing_change, Finance wants to expand billing to new regions and currencies): passes

- Name: Finance wants to expand billing to new regions and currencies
- Hypothesis: Accounts that changed their pricing model raise this on first calls: finance wants to expand billing to new regions and currencies.
- Angle: Ask whether their recent pricing change has them thinking about billing in new regions or currencies. Ask how other finance teams they know have handled that step.
- Trigger: pricing_change; personas: controller, billing_ops, cfo

**play_10** (tech_added, Revenue data in the warehouse never matches what was billed): passes

- Name: Revenue data in the warehouse never matches what was billed
- Hypothesis: Accounts that adopted a tool we connect to raise this on first calls: revenue data in the warehouse never matches what was billed.
- Angle: Ask whether the revenue numbers in their warehouse line up with what was actually billed, and who reconciles them when they do not. Offer to share how other finance teams approached that gap.
- Trigger: tech_added; personas: controller, data, revops

**play_11** (closed_lost_revisit, Month-end close slowed by manual usage reconciliation): fails personas_allowed, follows

- Name: Month-end close slowed by manual usage reconciliation
- Hypothesis: Closed lost accounts worth a revisit raised this on earlier calls: month-end close slowed by manual usage reconciliation.
- Angle: Ask whether their close team still reconciles usage by hand at month end, and whether that has moved up their list since you last spoke. Say how other finance teams stopped.
- Trigger: closed_lost_revisit; personas: controller, cfo, billing_ops
- follows: The angle's "Say how other finance teams stopped." claims other teams stopped reconciling by hand, which is a result the theme does not support.

**play_12** (job_change, Meterline): passes

- Name: Meterline
- Hypothesis: Accounts where a past champion moved bring up Meterline on first calls.
- Angle: Reach out to the past champion first, congratulate them on the new role, and ask how billing is set up at the new company. Ask whether Meterline is part of that setup and how it is working for their team.
- Trigger: job_change; personas: controller, billing_ops, cfo

**play_13** (hiring_function, Billing ops team spends days building invoices by hand): passes

- Name: Billing ops team spends days building invoices by hand
- Hypothesis: Accounts hiring in finance operations raise this on first calls: their billing ops team spends days building invoices by hand.
- Angle: Ask how their billing team builds invoices today and whether the new hires are meant to absorb more of that work. Offer to share how other finance teams changed the process without a hard switch for the team.
- Trigger: hiring_function; personas: billing_ops, controller, revops

**play_14** (new_exec, CFO Tom Becker at Northpeak wants real-time usage revenue visibility): passes

- Name: Real-time visibility into usage revenue
- Hypothesis: Accounts with a new finance leader raise this on first calls: they want real-time visibility into usage revenue.
- Angle: Ask how the new finance leader currently sees usage revenue during the month and whether they would want that view sooner. Offer to share how other finance teams approached it.
- Trigger: new_exec; personas: cfo, controller, revops

**play_15** (tech_added, In-house billing system maintained by engineering): passes

- Name: In-house billing system maintained by engineering
- Hypothesis: Accounts that adopted a tool we connect to raise this on first calls: an in-house billing system maintained by engineering.
- Angle: Ask who owns billing logic today and how finance gets a change made when pricing or invoicing rules shift. Say how other finance teams decided who should own billing.
- Trigger: tech_added; personas: controller, billing_ops, revops

