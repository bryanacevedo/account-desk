# Suggested-play eval

15 patterns written independently of the code, drafted through the desk's own path (catalog without private signals, code checks, one rewrite). Graded by code and by a Claude Sonnet 5.5 judge (15 judged).

| Check | Result |
|---|---|
| Offered and passes every check | 10 of 15 (67%, 90% interval 46 to 83%) |
| Withheld after failing the code checks twice | 0 of 15 (0%, 90% interval 0 to 15%) |
| Code: every trigger and persona from the catalog, the segment among the triggers | 15 of 15 (100%, 90% interval 85 to 100%) |
| Code: no name the case forbids | 15 of 15 (100%, 90% interval 85 to 100%) |
| Fit: triggers within what the case allows | 15 of 15 (100%, 90% interval 85 to 100%) |
| Fit: personas within what the case allows | 2 of 15 (13%, 90% interval 5 to 33%) |
| Judge: follows | 11 of 15 (73%, 90% interval 52 to 87%) |
| Judge: not as fact | 14 of 15 (93%, 90% interval 75 to 98%) |
| Judge: respects case | 15 of 15 (100%, 90% interval 85 to 100%) |

## Every play

**play_01** (new_exec, Month-end close slowed by manual usage reconciliation): fails personas_allowed, follows

- Name: Month-end close slowed by manual usage reconciliation
- Hypothesis: Accounts with a new finance leader raise this on first calls: month-end close is slowed by reconciling usage by hand.
- Angle: Ask the new leader how usage gets reconciled at month-end today and whether that is on their review list. Offer to share how other finance teams stopped doing it by hand.
- Trigger: new_exec; personas: cfo, controller, billing_ops
- follows: The angle's "Offer to share how other finance teams stopped doing it by hand" implies a result or capability (teams eliminated manual reconciliation) that the theme does not support.

**play_02** (hiring_function, Invoices carry wrong usage quantities, causing disputes): fails follows

- Name: Invoices carry wrong usage quantities, causing disputes
- Hypothesis: Accounts hiring in finance operations raise this on first calls: invoices go out with wrong usage quantities and customers dispute them.
- Angle: Ask whether usage quantities on their invoices ever come out wrong and lead to customer disputes. Offer to share how other finance teams cut those disputes down.
- Trigger: hiring_function; personas: billing_ops, controller, revops
- follows: The angle's "Offer to share how other finance teams cut those disputes down" implies a result (reduced disputes) the theme does not support.

**play_03** (pricing_change, Launching usage-based pricing on a subscription-only billing tool): passes

- Name: Launching usage-based pricing on a subscription-only billing tool
- Hypothesis: Accounts that changed their pricing model raise this on first calls: they are launching usage-based pricing on a billing tool built only for subscriptions.
- Angle: Ask how their billing tool is handling the move to usage-based pricing and whether any of it is being worked around by hand. Ask what would worry them about changing how they bill, and say how other finance teams approached that.
- Trigger: pricing_change; personas: billing_ops, controller, revops

**play_04** (competitor_review, Meterline): passes

- Name: Meterline
- Hypothesis: Accounts reviewing a competitor raise this on first calls: Meterline.
- Angle: Open without naming what we saw, and ask how their team is thinking about billing and revenue tooling this year. If they bring up Meterline, ask what matters most to them in the decision, cost included.
- Trigger: competitor_review; personas: controller, billing_ops, cfo

**play_05** (tech_removed, Chargewise): passes

- Name: Chargewise
- Hypothesis: Accounts that dropped a billing tool we replace bring up Chargewise on first calls.
- Angle: Ask how they are handling billing now and whether Chargewise is part of what they are weighing. Ask what matters most to their team in the next billing tool they choose.
- Trigger: tech_removed; personas: controller, billing_ops, cfo

**play_06** (hiring_function, Spreadsheets for usage billing): passes

- Name: Spreadsheets for usage billing
- Hypothesis: Accounts hiring in finance operations raise this on first calls: usage billing is run in spreadsheets.
- Angle: Ask whether usage billing still runs through spreadsheets as the team grows, and who keeps them up to date. Ask what engineering time any change on their side could get, and say how other finance teams moved off spreadsheets.
- Trigger: hiring_function; personas: billing_ops, controller, revops

**play_07** (new_exec, In-house billing system maintained by engineering): fails personas_allowed, follows

- Name: In-house billing system maintained by engineering
- Hypothesis: Accounts with a new finance leader raise this on first calls: billing runs on an in-house system that engineering maintains.
- Angle: Ask the new finance leader who owns billing changes today and how finance gets a pricing or invoice change made. Say how other finance teams worked with engineering when they took billing ownership.
- Trigger: new_exec; personas: cfo, controller, billing_ops
- follows: The angle adds an unsupported claim: "how other finance teams worked with engineering when they took billing ownership" asserts a result/precedent the theme does not support.

**play_08** (funding, Acme Robotics needs audit-ready revenue reports before their Series C): passes

- Name: Audit-ready revenue reports before the next funding round
- Hypothesis: Accounts that recently raised a round raise this on first calls: they need audit-ready revenue reports before their next round.
- Angle: Ask how they plan to get revenue reporting ready for investor and audit review ahead of their next round. Ask what still slows their team down when pulling those reports together today.
- Trigger: funding; personas: cfo, controller, revops

**play_09** (pricing_change, Finance wants to expand billing to new regions and currencies): passes

- Name: Finance wants to expand billing to new regions and currencies
- Hypothesis: Accounts that changed their pricing model raise this on first calls: finance wants to expand billing to new regions and currencies.
- Angle: Ask whether new regions or currencies are on their billing roadmap now that their pricing has changed. Offer to share how other finance teams have approached that expansion.
- Trigger: pricing_change; personas: cfo, controller, billing_ops

**play_10** (tech_added, Revenue data in the warehouse never matches what was billed): passes

- Name: Revenue data in the warehouse never matches what was billed
- Hypothesis: Accounts that adopted a tool we connect to raise this on first calls: revenue data in the warehouse never matches what was billed.
- Angle: Ask whether the revenue numbers in their warehouse line up with what was actually billed each month. Ask how their team handles it when the two disagree, and offer to share how other finance teams approached it.
- Trigger: tech_added; personas: controller, data, revops

**play_11** (closed_lost_revisit, Month-end close slowed by manual usage reconciliation): fails personas_allowed, follows

- Name: Month-end close slowed by manual usage reconciliation
- Hypothesis: Closed lost accounts worth a revisit raised this on earlier calls: month-end close slowed by manual usage reconciliation.
- Angle: Ask whether reconciling usage by hand still slows their month-end close, and whether priorities or budget have shifted since you last spoke. Offer to share how other finance teams stopped reconciling usage manually.
- Trigger: closed_lost_revisit; personas: controller, cfo, billing_ops
- follows: The angle adds an unsupported claim: "Offer to share how other finance teams stopped reconciling usage manually" implies a result and capability the theme does not support.

**play_12** (job_change, Meterline): passes

- Name: Meterline
- Hypothesis: Accounts where a past champion moved bring up Meterline on first calls.
- Angle: Congratulate them on the new role and ask how billing is handled at the new company, including whether Meterline is in the picture. Ask what they would want to set up differently this time.
- Trigger: job_change; personas: controller, cfo, billing_ops

**play_13** (hiring_function, Billing ops team spends days building invoices by hand): passes

- Name: Billing ops team spends days building invoices by hand
- Hypothesis: Accounts hiring in finance operations raise this on first calls: their billing ops team spends days building invoices by hand.
- Angle: Ask how their billing team builds invoices today and whether the new hires are meant to absorb more of that work. Ask what would make a change in process easy for the team to take on.
- Trigger: hiring_function; personas: billing_ops, controller, cfo

**play_14** (new_exec, CFO Tom Becker at Northpeak wants real-time usage revenue visibility): passes

- Name: Wants real-time visibility into usage revenue
- Hypothesis: Accounts with a new finance leader raise this on first calls: they want real-time visibility into usage revenue.
- Angle: Ask the new finance leader how they currently see usage revenue during the month and whether that view is as current as they want. Ask what they plan to review in the finance stack first.
- Trigger: new_exec; personas: cfo, controller, revops

**play_15** (tech_added, In-house billing system maintained by engineering): fails personas_allowed, not_as_fact

- Name: In-house billing system maintained by engineering
- Hypothesis: Accounts that adopted a tool we connect to raise this on first calls: their billing runs on an in-house system maintained by engineering.
- Angle: Ask who maintains their billing today and whether finance waits on engineering for changes. Offer to share how other finance teams handled billing after adding a new ERP or warehouse.
- Trigger: tech_added; personas: controller, billing_ops, cfo
- not_as_fact: The hypothesis asserts "their billing runs on an in-house system maintained by engineering" as the recipient's own situation instead of framing it as something to check.

