# Suggested-play eval

15 patterns written independently of the code, drafted through the desk's own path (catalog without private signals, code checks, one rewrite). Graded by code and by a Claude Sonnet 5.5 judge (15 judged).

| Check | Result |
|---|---|
| Offered and passes every check | 4 of 15 (27%, 90% interval 13 to 48%) |
| Withheld after failing the code checks twice | 0 of 15 (0%, 90% interval 0 to 15%) |
| Code: every trigger and persona from the catalog, the segment among the triggers | 15 of 15 (100%, 90% interval 85 to 100%) |
| Code: no name the case forbids | 15 of 15 (100%, 90% interval 85 to 100%) |
| Fit: triggers within what the case allows | 7 of 15 (47%, 90% interval 28 to 67%) |
| Fit: personas within what the case allows | 2 of 15 (13%, 90% interval 5 to 33%) |
| Judge: follows | 8 of 15 (53%, 90% interval 33 to 72%) |
| Judge: not as fact | 12 of 15 (80%, 90% interval 59 to 92%) |
| Judge: respects case | 10 of 15 (67%, 90% interval 46 to 83%) |

## Every play

**play_01** (new_exec, Month-end close slowed by manual usage reconciliation): fails triggers_allowed, personas_allowed, follows, respects_case

- Name: New finance leader, slow usage-driven close
- Hypothesis: When a new finance leader arrives, they review the stack in their first 90 days, and the controller and billing team feel pressure to shorten the close. Teams that bill on usage often find month-end slowed by manual reconciliation, which our software automates.
- Angle: Lead with what is common for teams under a new finance leader: usage reconciliation done by hand is often what stretches the month-end close. Offer a short, phased rollout that starts with reconciliation so results show up within the first quarter without a long implementation.
- Trigger: new_exec, hiring_function, pricing_change; personas: cfo, controller, billing_ops
- follows: The hypothesis claims 'our software automates' reconciliation and the angle promises 'results show up within the first quarter', and the theme supports neither; the output also lists unrelated triggers 'hiring_function' and 'pricing_change'.
- respects_case: The notes forbid promising a specific timeline, but the angle says 'results show up within the first quarter without a long implementation', which is a timeline promise.

**play_02** (hiring_function, Invoices carry wrong usage quantities, causing disputes): fails triggers_allowed, respects_case

- Name: Finance ops hiring: fix usage quantities on invoices
- Hypothesis: When a company is hiring billing or finance operations staff, billing ops and the controller often need us, because growing manual work tends to come from usage quantities being pulled onto invoices by hand, which leads to wrong amounts and customer disputes.
- Angle: Lead with the open finance operations roles and note that teams hiring for billing often find much of the new workload is correcting usage quantities and handling the invoice disputes they cause. Offer a short look at how automated usage rating cuts that rework, framed against the cost of the added headcount to get ahead of price concerns.
- Trigger: hiring_function, pricing_change; personas: billing_ops, controller, revops
- respects_case: The trigger list includes 'pricing_change', a signal the case never gave (only hiring_function), so it invents a signal; the angle does frame the headcount cost as an offset as the notes ask.

**play_03** (pricing_change, Launching usage-based pricing on a subscription-only billing tool): fails personas_allowed, not_as_fact

- Name: Usage pricing launch on subscription billing
- Hypothesis: When a company changes to usage or hybrid pricing, its billing, revenue operations and controller teams need a billing system that can meter and invoice usage, because subscription-only tools force manual workarounds that slow invoicing and put revenue accuracy at risk.
- Angle: Lead with the account's pricing change and note that teams launching usage-based pricing on a subscription-only tool often end up rating usage in spreadsheets before every invoice run. Offer a phased path that runs usage billing alongside the current system first, so the move carries little migration risk.
- Trigger: pricing_change; personas: billing_ops, revops, controller
- not_as_fact: The angle opens with "Lead with the account's pricing change" and closes with "so the move carries little migration risk", treating the pricing move as the recipient's actual situation, though the spreadsheet line is framed as common ("often end up rating usage in spreadsheets").

**play_04** (competitor_review, Meterline): fails triggers_allowed, personas_allowed, follows, respects_case

- Name: Competitor review: Meterline evaluations
- Hypothesis: When a finance team is actively reviewing a competitor like Meterline, the CFO and Controller have budget and a live decision, so they need a clear comparison on total cost and fit before they commit.
- Angle: Lead with a plain total cost of ownership view, since teams comparing usage billing tools like Meterline often find that list price differs from what they pay once implementation, add-ons and manual work are counted. Offer a short side by side on cost and close and invoicing effort.
- Trigger: competitor_review, tech_removed, closed_lost_revisit; personas: cfo, controller, billing_ops
- follows: The angle adds an unsupported claim that comparison teams "often find that list price differs from what they pay once implementation, add-ons and manual work are counted", which the theme and segment signal do not support.
- respects_case: The angle implies Meterline carries hidden costs ("list price differs from what they pay once implementation, add-ons and manual work are counted"), an unverifiable negative claim, and it is not grounded in documented strengths of our product.

**play_05** (tech_removed, Chargewise): passes

- Name: Replacing a dropped billing tool, Chargewise in the mix
- Hypothesis: When a company drops a billing tool we replace, its finance and billing leads face a replacement decision, and Chargewise often comes up as an option. They need a clear comparison and a low-risk migration path before they settle on the next system.
- Angle: Lead with how teams replacing a billing tool often weigh Chargewise alongside us, and offer a plain side-by-side on migration effort, revenue recognition, and invoicing flexibility so the choice is easier to make.
- Trigger: tech_removed, competitor_review; personas: controller, billing_ops, cfo

**play_06** (hiring_function, Spreadsheets for usage billing): fails triggers_allowed, personas_allowed, follows

- Name: Finance ops hiring as usage billing outgrows spreadsheets
- Hypothesis: When a company starts hiring billing or finance operations staff, the controller and billing team often need us, because usage billing run in spreadsheets tends to scale by adding people rather than fixing the process.
- Angle: Lead with the hiring signal and note that teams adding billing headcount often find usage billing still lives in spreadsheets, so each new hire inherits manual reconciliation. Point out that moving usage billing off spreadsheets can be done without pulling engineering time away from the product.
- Trigger: hiring_function, pricing_change; personas: controller, billing_ops, cfo
- follows: The trigger list adds "pricing_change", a signal the segment (hiring in finance operations) does not support, and the angle claims it "can be done without pulling engineering time away from the product", which the theme does not establish.

**play_07** (new_exec, In-house billing system maintained by engineering): fails triggers_allowed, personas_allowed, follows

- Name: New finance leader inheriting homegrown billing
- Hypothesis: When a new finance leader arrives, they review the stack in their first 90 days, and many find billing runs on an in-house system that engineering maintains. That leaves finance dependent on engineering for every pricing or invoicing change, which a new leader is often looking to fix.
- Angle: Lead with what is common for new finance leaders: many inherit billing built and maintained by engineering, and find that small pricing or invoicing changes wait on the product roadmap. Offer a short look at how teams move billing ownership to finance while engineering keeps control of the integrations they care about.
- Trigger: new_exec, pricing_change; personas: cfo, controller, billing_ops
- follows: The hypothesis adds a claim the theme and segment don't support: "finance dependent on engineering for every pricing or invoicing change, which a new leader is often looking to fix" and the angle's "small pricing or invoicing changes wait on the product roadmap".

**play_08** (funding, Acme Robotics needs audit-ready revenue reports before their Series C): passes

- Name: Audit-ready revenue reporting after a funding round
- Hypothesis: When a company raises a round, its CFO and controller need us because investors and the next round's diligence expect clean, audit-ready revenue reports, and manual billing data rarely holds up to that scrutiny.
- Angle: Lead with the recent raise and note that teams after a funding round often find the next round's diligence asks for audit-ready revenue reports their current billing setup cannot produce quickly. Offer a short look at how finance teams get reporting investor-ready, and frame cost against the time saved before diligence, since price is a common concern.
- Trigger: funding; personas: cfo, controller, revops

**play_09** (pricing_change, Finance wants to expand billing to new regions and currencies): fails personas_allowed, respects_case

- Name: Pricing change plus regional expansion billing
- Hypothesis: When a company changes its pricing model, finance often also plans to bill in new regions and currencies, and the billing setup that handled one model in one currency struggles with both at once. Billing operations, the controller and the CFO need a system that supports new pricing and multi-currency invoicing together.
- Angle: Lead with the account's pricing change and note that teams moving to usage or hybrid pricing often find they also want to bill in new regions and currencies soon after. Offer a short look at how billing can handle new pricing, local currencies and tax without rebuilding the setup twice.
- Trigger: pricing_change, funding; personas: billing_ops, controller, cfo
- respects_case: The trigger list includes "funding", a signal the case does not support for this segment (only pricing_change), so it adds an unsupported trigger that the case's notes say to avoid.

**play_10** (tech_added, Revenue data in the warehouse never matches what was billed): passes

- Name: New warehouse or ERP, billed revenue that matches
- Hypothesis: When a finance team adopts a warehouse or ERP we connect to, controllers and data teams need billed revenue to land there cleanly, because revenue data in the warehouse often fails to match what was actually billed.
- Angle: Lead with the point that teams connecting a new warehouse or ERP often find revenue figures there drift from what was billed. Then explain that a native connection to the tool they just adopted keeps billing and warehouse data in sync and shortens rollout, since much of the integration work is already done.
- Trigger: tech_added; personas: controller, data, revops

**play_11** (closed_lost_revisit, Month-end close slowed by manual usage reconciliation): fails triggers_allowed, personas_allowed, follows, not_as_fact, respects_case

- Name: Closed lost revisit: usage reconciliation at close
- Hypothesis: When a deal lost on timing or budget comes back into view, controllers and finance leaders often still carry a slow month-end close because usage data is reconciled by hand, and the cost of that work tends to grow as usage volume does.
- Angle: Lead with what is common for teams that paused a billing project: manual usage reconciliation tends to keep stretching the close, and a smaller first phase focused on automating that step can fit a tight budget. Offer a short look at how teams in a similar spot scoped it without a large commitment this year.
- Trigger: closed_lost_revisit, pricing_change, hiring_function, new_exec; personas: controller, cfo, billing_ops
- follows: The triggers add signals the segment does not support ("pricing_change", "hiring_function", "new_exec"), and the angle adds a "smaller first phase" scoping offer the theme does not support.
- not_as_fact: The hypothesis says "controllers and finance leaders often still carry a slow month-end close", which asserts the problem still exists for returning accounts, though the angle is hedged with "what is common for teams".
- respects_case: The hypothesis implies their close is still slow ("often still carry a slow month-end close"), which the trap forbids, and it invents extra trigger signals.

**play_12** (job_change, Meterline): fails personas_allowed, follows

- Name: Past champion lands where a competing tool runs
- Hypothesis: When a past champion moves to a new company, the finance team they join often already runs a competing billing tool, and the champion is well placed to compare it against a product they already trust. They need a quick way to judge whether switching is worth it in their new seat.
- Angle: Open by congratulating them on the new role and referencing the work they did with us before. Note that people who move into a new finance team often inherit a different billing tool and find it useful to compare the two early, then offer a short side by side on the workflows they relied on.
- Trigger: job_change; personas: controller, billing_ops, cfo
- follows: The theme is Meterline but the output never mentions it and uses only a generic "competing billing tool"; it also claims "the finance team they join often already runs a competing billing tool", which neither the theme nor the job_change signal supports.

**play_13** (hiring_function, Billing ops team spends days building invoices by hand): fails triggers_allowed, personas_allowed, follows

- Name: Finance ops hiring signals manual invoicing load
- Hypothesis: When a company is hiring billing or finance operations staff, the controller and billing ops lead are often adding headcount to keep up with invoices built by hand, because invoicing work is growing faster than the process can absorb.
- Angle: Lead with the open finance operations roles and note that teams hiring for billing often find much of the new capacity goes to assembling invoices by hand. Offer a short look at how automating invoice creation can let the existing team and new hires take it on without a disruptive rollout.
- Trigger: hiring_function, pricing_change, funding; personas: controller, billing_ops, cfo
- follows: The trigger list adds "pricing_change" and "funding", which the segment's hiring signal and the theme do not support, and the hypothesis claims invoicing work is "growing faster than the process can absorb", which goes beyond the theme.

**play_14** (new_exec, CFO Tom Becker at Northpeak wants real-time usage revenue visibility): passes

- Name: New finance leader wants live usage revenue view
- Hypothesis: When a company brings in a new finance leader, that leader and their controller need clear, current visibility into usage revenue, because new leaders review the stack in their first 90 days and often find usage data arrives late or is assembled by hand.
- Angle: Lead with what is common for teams with a new finance leader: they often find usage revenue is only visible after month end and want a real-time view as part of their first review of the stack. Keep it short, offer a quick look at how live usage revenue reporting works, and be ready to frame cost against the hours spent reconciling usage by hand, since price is a common concern.
- Trigger: new_exec, job_change; personas: cfo, controller, revops

**play_15** (tech_added, In-house billing system maintained by engineering): fails personas_allowed, not_as_fact

- Name: New ERP or warehouse meets in-house billing
- Hypothesis: When a company adopts an ERP or data warehouse we connect to, finance and billing teams running a homegrown billing system face new integration work that falls on engineering. A packaged billing tool that already connects to that system lowers the effort and frees engineering from upkeep.
- Angle: Lead with the new tool they adopted and note that teams in that position often find an in-house billing system maintained by engineering becomes harder to keep in sync. Offer a short look at how our existing connector to that tool shortens rollout.
- Trigger: tech_added; personas: controller, billing_ops, revops
- not_as_fact: The hypothesis states as fact that companies 'running a homegrown billing system face new integration work that falls on engineering', and the angle's 'Lead with the new tool they adopted' presumes the recipient's situation.

