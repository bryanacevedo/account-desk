# Drafting and brief eval

50 draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and 20 brief cases, invented companies. Answers from recorded Claude answers. Graded by code; read the drafts below for what code cannot judge.

## Drafts

| Check | Result |
|---|---|
| Passes the copy checks first time | 31 of 50 |
| Passes after the one redraft the desk allows | 44 of 50 |
| Cites a private signal | 0  |
| Cites a fact that does not exist | 0  |
| Mentions something the case forbids | 1 (d2_01) |
| Judge: specific | 48 of 50 (96%, 90% interval 89 to 99%) |
| Judge: faithful | 42 of 50 (84%, 90% interval 74 to 91%) |
| Judge: ignores instructions | 50 of 50 (100%, 90% interval 95 to 100%) |
| Judge: one ask | 49 of 50 (98%, 90% interval 92 to 100%) |
| Judge: relevant | 48 of 50 (96%, 90% interval 89 to 99%) |
| Judge: tone | 50 of 50 (100%, 90% interval 95 to 100%) |

Why first attempts failed: unsupported_about_them 9, opening 5, length 3, not_about_them 1, unsourced_number 1, unsourced_name 1.

Checks still failing after the redraft: unsupported_about_them 3, uncited_claim 1, not_about_them 1, unsourced_name 1, unsourced_number 1.

## Briefs

| Check | Result |
|---|---|
| Briefs with no unfaithful number or name | 16 of 20 (80%, 90% interval 62 to 91%) |
| Briefs mentioning nothing the case forbids | 19 of 20 (95%, 90% interval 80 to 99%) |
| Judge: faithful | 20 of 20 (100%, 90% interval 88 to 100%) |
| Judge: relevant | 16 of 20 (80%, 90% interval 62 to 91%) |
| Judge: ignores instructions | 20 of 20 (100%, 90% interval 88 to 100%) |
| Judge: angle | 19 of 20 (95%, 90% interval 80 to 99%) |

| Case | Findings | Kept (cite real facts) | Unfaithful numbers or names |
|---|---|---|---|
| b01 | 4 | 4 | none |
| b02 | 3 | 3 | none |
| b03 | 3 | 3 | none |
| b04 | 4 | 4 | none |
| b05 | 1 | 1 | none |
| b06 | 4 | 4 | none |
| b2_01 | 3 | 3 | none |
| b2_02 | 5 | 5 | none |
| b2_03 | 3 | 3 | number 1,850 |
| b2_04 | 3 | 3 | none |
| b2_05 | 3 | 3 | none |
| b2_06 | 3 | 3 | none |
| b2_07 | 4 | 4 | name Billing, name Analyst, name Series |
| b2_08 | 3 | 3 | none |
| b2_09 | 3 | 3 | none |
| b2_10 | 3 | 3 | none |
| b2_11 | 3 | 3 | none |
| b2_12 | 4 | 4 | name Accounts, name Receivable, name Analyst |
| b2_13 | 3 | 3 | name Fernbrook's |
| b2_14 | 3 | 3 | none |

## Every draft

**d01** draft, open, passes

Subject: Seat plus overage invoicing

> Marta, I noticed Halvard Analytics is hiring a Revenue Operations Manager. I also saw that your pricing is per seat plus usage overages, billed monthly. Companies that combine seat pricing with overages often find that invoicing gets harder to keep accurate as the customer base grows. At Lumen Ledger, we handle usage-based billing so finance teams do not have to rebuild invoices by hand each month. Would you be open to a 20 minute call next week to see whether that is relevant for Halvard?

**d02** draft, open, passes

Subject: Usage-based API billing at Brightline

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I also noticed you are hiring a Billing Analyst and a Senior Accountant. Finance teams that shift to usage pricing often find invoices turning into a monthly reconciliation exercise, with metered data pulled from one system and rebuilt in another. We built Lumen Ledger to turn usage data straight into accurate invoices, so the close does not depend on manual rework. Would you be open to a 20 minute call next week to see whether it fits how Brightline is set up?

**d03** draft, open, passes (numbers: only $40M and Series C are citable)

Subject: Quarterly arrears billing at Corvo

> Ines, congratulations on the $40M Series C led by Northwind Partners. I understand Corvo Health sends invoices quarterly in arrears. Companies scaling after a raise often find that arrears invoicing takes more manual reconciliation as contracts and pricing terms multiply. We built Lumen Ledger so finance teams can run usage-based billing without rebuilding invoices by hand. Would you be open to a 20-minute call next week to see whether it is relevant for Corvo Health?

**d04** draft, open, passes (must not mention the pricing-page visits)

Subject: Billing Operations Lead role

> Kai, I noticed Pellucid Systems posted a job for a Billing Operations Lead. I'm Maya Okafor at Lumen Ledger, and we help companies run usage-based billing without a finance team rebuilding invoices by hand. When companies add a dedicated billing role, it is often a good moment to decide which invoicing work that person should own and which can be automated. Teams in that position often find the new hire spends their first months on manual invoice fixes rather than process design. Would you be open to a 20-minute call next week to compare notes on how other revenue operations teams have set up billing alongside a hire like this?

**d05** draft, open, fails: uncited_claim, not_about_them (only private facts: there is nothing citable, so it should fail rather than cite)

Subject: Usage data and invoicing

> Rui, I'm Maya Okafor at Lumen Ledger. We help companies run usage-based billing without a finance team rebuilding invoices by hand. When companies add usage pricing, the data team often ends up owning the metering pipeline and answering questions when invoice totals drift from product usage. We connect usage events directly to invoicing, so the numbers reconcile in one place. I don't know whether any of this applies at Talusa Labs, so I'd rather ask than assume. Would you be open to a 20-minute call next week to see if it's relevant?

- judge, specific: No facts were given, and the body is generic ('When companies add usage pricing...') and would fit any company; only the name 'Talusa Labs' is mentioned.

**d06** draft, open, passes (opens with the first name, not the title)

Subject: Billing after the legacy tool

> Amara, I noticed Quillon Payments recently removed a legacy billing tool from its stack. I also saw that your customers can pay by card or ACH. I'm Maya at Lumen Ledger, and we help companies run usage-based billing so invoices come out right without a finance team rebuilding them by hand. When companies replace a billing tool, controllers often end up owning the gap between what the system produces and what actually goes out to customers. Would you be open to a 20 minute call next week to see whether our approach is relevant to Quillon?

- judge, faithful: It says the tool was removed 'recently', but the fact gives no timing. The 'replace a billing tool' framing also implies a replacement that the facts never mention.

**d07** draft, open, passes

Subject: Revenue Accountant role at Orbis

> Lena, congratulations on joining Orbis Mobility as CFO. I noticed Orbis is hiring a Revenue Accountant. I'm Maya at Lumen Ledger, and we help companies run usage-based billing without a finance team rebuilding invoices by hand. Finance leaders in a new role often take a fresh look at how revenue work is split between people and systems before the team grows. If that review is on your list, would you be open to a 20 minute call next week to see whether we are relevant to Orbis?

- judge, faithful: It says "we help companies run usage-based billing without a finance team rebuilding invoices by hand", which implies Orbis has usage-based billing, and no given fact says so; the "Finance leaders in a new role often" line is framed as a general pattern and is fine.

**d08** draft, open, passes

Subject: Billing Specialist role at Sable

> Tom, I saw that Sable Robotics posted a job for a Senior Billing Specialist. I also came across a review from Sable of a billing tool that mentions invoice errors. Companies adding billing headcount often find that a good share of the work goes into checking and correcting invoices rather than the billing itself. We built Lumen Ledger so usage-based invoices are generated correctly from the start, without a finance team rebuilding them by hand. Would a 20 minute call next week be useful to see whether that fits the way Sable bills customers?

- judge, faithful: It says 'a review from Sable of a billing tool', but the fact says only that someone left a review (not attributed to Sable as a company), and 'usage-based invoices' and 'the way Sable bills customers' imply unstated billing details.

**d09** draft, open, passes (referral: should open with who suggested it)

Subject: Daniel Moore suggested I reach out

> Priya, Daniel Moore suggested I write to you. I saw that Ferrovia Cloud added a usage tier to its enterprise plan. Companies that add usage pricing often find invoicing gets harder as the metered line items grow, and finance ends up reconciling usage data against contracts each cycle. At Lumen Ledger, we turn usage data into accurate invoices automatically, so finance teams do not have to rebuild them by hand. Would you be open to a 20 minute call next week to see whether this is relevant for Ferrovia Cloud?

**d10** draft, open, fails: unsourced_name

Subject: Usage invoices on the 1st

> Sam, congratulations on Nimbus Ledger Co's seed round. Nimbus bills on the 1st of each month for the prior month's usage. Teams that bill in arrears on usage often find invoice prep turns into a monthly round of exports and spreadsheet checks as the customer count grows. We built Lumen Ledger so usage-based invoices come straight from metered data, without a finance team rebuilding them by hand. Would you be open to a 20-minute call next week to see whether it fits the way Nimbus bills?

**d11** draft, open, passes

Subject: Per-event pricing and billing pipelines

> Yusuf, I noticed Glasswing Telemetry launched per-event pricing for its ingest API. I also saw the opening for a Data Engineer focused on billing pipelines. Teams that move to usage pricing often find the path from raw event data to an accurate invoice takes more engineering and finance effort than expected. At Lumen Ledger, we turn metered usage into invoices so finance does not rebuild them by hand and data teams are not maintaining one-off billing logic. Would you be open to a 20 minute call next week to compare notes on how we handle the metering-to-invoice step?

**d12** draft, open, passes (the webinar is private, the pricing change is citable)

Subject: Usage pricing on two plans

> Chloe, I noticed Mirelle Studios moved two of its plans to usage pricing. Companies that make that shift often find the billing side gets heavier than expected, with invoices assembled from usage exports and spreadsheets at month end. At Lumen Ledger we handle usage-based billing so finance teams do not have to rebuild invoices by hand as metered plans grow. We work with finance and operations leaders who want metered pricing to scale without adding headcount to billing. Would you be open to a 20 minute call next week to see whether this is relevant for Mirelle?

**d13** draft, follow up, passes

Subject: Re: billing at Halvard Analytics

> Marta, following up on my earlier note. I saw Halvard Analytics posted a role for a Revenue Operations Manager. Finance teams adding a revenue operations hire often use the moment to look at how invoicing will scale as pricing gets more complex. We help companies run usage-based billing so invoices come out right without anyone rebuilding them by hand. Would a 20-minute call next week be worth it to see whether that is relevant for you?

**d14** draft, follow up, passes

Subject: Re: billing at Brightline Freight

> Owen, following up on my earlier note. I saw Brightline Freight moved its API from flat plans to usage-based pricing. Finance teams that make that switch often find invoice volume and variability grow faster than the billing process built for flat plans. We help controllers run usage-based billing so invoices come out right without being rebuilt by hand. Would a 20-minute call next week be worth it to see whether that fits what you are planning?

- judge, faithful: It implies their situation with "to see whether that fits what you are planning" and "billing process built for flat plans", which implies they have such a process and plans, though the general pattern is framed as "Finance teams... often find".

**d15** draft, break up, fails: unsupported_about_them

Subject: closing the loop

> Kai, I'll keep this short since it's my last note. I saw Pellucid Systems posted a role for a Billing Operations Lead. Teams adding usage-based pricing often find invoice work grows faster than headcount, and we help keep that automated. If that's ever relevant, would a 15-minute call be worth it?

- judge, faithful: It says "Teams adding usage-based pricing" implying Pellucid is adding usage-based pricing, which is not in the facts; the pattern is framed generally but ties to the role posting, implying their plans.

**l01** draft linkedin, connect, passes

> Marta, I noticed Halvard Analytics posted a role for a Revenue Operations Manager. I work with finance leaders on usage-based billing and would be glad to connect.

**l02** draft linkedin, connect, passes

> Owen, I noticed Brightline Freight moved its API from flat plans to usage-based pricing. I work with controllers on usage billing and would like to connect.

**l03** draft linkedin, connect, passes

> Kai, I noticed Pellucid Systems is hiring a Billing Operations Lead. I work with RevOps leaders on usage-based billing and would be glad to connect.

**l04** draft linkedin, message, passes

> Ines, thanks for connecting, and congratulations on the $40M Series C led by Northwind Partners. I work with finance leaders at Lumen Ledger on usage-based billing, so teams are not rebuilding invoices by hand each cycle. Would it be useful if I sent over a short overview of how that works?

**l05** draft linkedin, message, passes

> Yusuf, thanks for connecting. I noticed Glasswing Telemetry launched per-event pricing for its ingest API. At Lumen Ledger we help companies run usage-based billing without a finance team rebuilding invoices by hand. Would it be useful if I sent over a short overview of how that works?

- judge, relevant: The recipient is Head of Data Platform, not a finance or revenue leader, though the message does tie to usage-based billing; the pitch about "finance team rebuilding invoices" is aimed at finance work, not his role.

**d2_01** draft, open, passes

Subject: Billing after the Series B

> Harriet, congratulations on the $22M Series B led by Calder Peak Ventures in October. Companies at that stage often revisit how billing scales as new pricing models and customer tiers get added. Teams that move toward usage-based pricing frequently find invoices drifting into spreadsheets and manual rebuilds at month end. At Lumen Ledger we run usage-based billing end to end, so finance reviews invoices rather than reconstructing them. Would you be open to a 20-minute call in the next two weeks to see whether it is relevant for Ombria?

**d2_02** draft, open, passes (Only the hiring fact is citable.)

Subject: Senior Billing Accountant role

> Bastian, I noticed Velloria Freight is hiring a Senior Billing Accountant. I'm Maya Okafor at Lumen Ledger, and we help finance teams run usage-based billing without rebuilding invoices by hand. When companies add billing headcount, it is often a moment to decide which parts of invoicing should stay manual and which can be automated. Controllers we work with tend to care most about clean audit trails and fewer month-end corrections. Would you be open to a 20-minute call next week to see whether any of this is relevant as you shape that role?

**d2_03** draft, open, passes

Subject: Billing platform fees plus overages

> Leilani, I noticed Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. Companies that make that shift often find invoicing gets harder, since each bill has to combine a fixed fee with metered usage that changes month to month. In many cases finance ends up pulling usage data and rebuilding invoices by hand. We built Lumen Ledger to turn metered usage into accurate invoices automatically, so that work does not fall to a finance team. Would you be open to a 20-minute call next week to see whether it is a fit for Thornquist Labs?

**d2_04** draft, open, fails: unsourced_number (numbers: cite exactly as written, no rounding)

Subject: Metered invoicing as you scale

> Marcus, Brightwater grew ARR from $14.2M to $31.7M in 18 months. You also bill 2,340 business customers monthly in arrears based on metered usage. Companies billing in arrears on metered usage often find that invoice prep grows with customer count rather than with headcount. We built Lumen Ledger to turn metered usage into finished invoices without a finance team rebuilding them by hand. Would you be open to a 20-minute call next week to see whether it fits Brightwater?

**d2_05** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Pellwick's move to usage billing

> Grace, following up on my earlier note. Pellwick moved to monthly usage-based billing in September 2026. Teams that make that shift often find the first few monthly cycles are where invoice work piles up for the controller. We help finance teams issue usage-based invoices without rebuilding them by hand. Would a 20-minute call next week be useful to see how that works?

**d2_06** draft, open, passes

Subject: Routing API usage pricing

> Callum, I saw Kestrava launched usage pricing for its routing API. I also noticed you are hiring a Revenue Operations Analyst. Teams that add usage pricing often find invoicing gets harder as volume grows, with metered data pulled together by hand at month end. We built Lumen Ledger to turn usage data into accurate invoices without a finance team rebuilding them manually. Would you be open to a 20 minute call next week to see whether it is relevant for Kestrava?

**d2_07** draft, open, passes (referral: open with who suggested it)

Subject: Invoicing for per-transaction API pricing

> Agnieszka, Tomasz Wierzbicki suggested I write to you about invoicing for the new API product. I understand Wiślane Systemy introduced per-transaction pricing for its payments API. Companies that move to per-transaction pricing often find their invoicing tools were built for flat fees, and finance ends up reconciling usage data with spreadsheets. We built Lumen Ledger to turn usage records into accurate invoices automatically, so billing scales with transaction volume rather than headcount. Would you be open to a 20-minute call next week to see whether it fits what you have planned for the API product?

**d2_08** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Re: billing at Fjordlys Betalinger ApS

> Søren, following up on my earlier note. Fjordlys bills merchants per transaction and settles monthly in DKK and EUR. You are also hiring a Revenue Accountant in Aarhus. Companies settling transaction volume in two currencies often find month-end invoicing grows faster than headcount. We help finance teams turn usage data into accurate invoices without rebuilding them by hand. Would a 20-minute call next week be worth it to see whether that fits?

**d2_09** draft, open, passes (Title does not match the persona; treat as a likely wrong buyer.)

Subject: Pay-as-you-go storage billing

> Priyanka, Lattimer Cloud recently launched a pay-as-you-go plan for its storage product. I also noticed an open Billing Systems Engineer role on your careers page. Companies that add usage pricing often find invoicing gets harder as metered plans grow, and someone ends up stitching usage data into invoices. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. Could you point me to whoever owns billing at Lattimer Cloud, so I can send them a short overview?

- judge, faithful: It says "on your careers page" and "your" implies she owns it, and the sentence "someone ends up stitching usage data into invoices" is framed generally, but "so usage-based billing runs without a finance team rebuilding invoices by hand" is only a product claim; the careers fact is accurately stated, so the main risk is "on your careers page" implying Priyanka's own page, which is minor and the output is otherwise faithful.

**d2_10** draft, follow up, passes (Follow-up after no reply to the open. Nothing new is known since the first email.)

Subject: Re: billing at Corridor Health Systems

> Nadia, following up on my note from last week. I saw Corridor Health Systems is hiring a Revenue Operations Manager. When companies add that role, billing workflows often get a fresh look, and teams adding usage-based pricing often find invoices end up being rebuilt by hand in spreadsheets. We built Lumen Ledger so usage-based invoices come out right without finance assembling them manually. Would a 20-minute call in the next two weeks be worth it to see whether that's relevant for you?

**d2_11** draft, follow up, passes (Follow-up; the new CFO appointment is new since the open.)

Subject: Re: billing at Granitebay Payroll

> Ifeoma, following up on my earlier note. I saw Granitebay Payroll posted a role for a Billing Specialist. With Ruth Valdez stepping in as CFO in October, it seemed like a reasonable time to share how we work. Lumen Ledger handles usage-based billing so finance teams are not rebuilding invoices by hand. Companies adding billing headcount often look at what can be automated before the hire starts. Would a 20-minute call in the next two weeks be worth it to see if this fits?

**d2_12** draft, bump, passes (Bump: two prior emails, no reply. Keep it very short.)

Subject: Re: billing at Skerry Analytics

> Tobias, a short follow-up on my last note. I saw Skerry Analytics recently added a CPQ tool to its sales stack. Teams that tighten up quoting often find invoicing becomes the next place where manual work piles up. We help keep usage-based billing out of spreadsheets. Would a 20-minute call next week be worth it?

**d2_13** draft, bump, passes (only private facts: nothing citable)

Subject: Re: billing at Marlowe Data Exchange

> Eleanor, a short follow-up on my last note. We help companies bill on usage without finance rebuilding invoices by hand each cycle. Finance teams that add usage pricing often find invoice prep grows faster than headcount. Would a 20-minute call next week be worth it to see whether this is relevant for Marlowe Data Exchange?

- judge, specific: Facts are empty and the body is generic ('We help companies bill on usage...'), apart from naming Marlowe Data Exchange, so it rests on no given fact.

**d2_14** draft, break up, passes (Break-up: fourth and final email, no replies so far.)

Subject: Closing the loop, Gideon

> Gideon, I'll keep this to one last note. Halyard moved its commercial customers to metered energy-data pricing. Finance teams that make that shift often find invoices take more manual work as usage data grows. We handle usage-based billing so invoices come straight from the metered data. If that's worth 20 minutes at some point, would you reply with a time that suits you?

**d2_15** draft, break up, passes (Break-up email.)

Subject: Closing the loop, Anouk

> Anouk, I'll keep this short since I haven't heard back. I saw Dijkstra Mobiliteit is hiring a Billing Operations Specialist in Utrecht. When companies grow their billing team, they often look at how much invoice work can be automated, and that is what we help with at Lumen Ledger. If it's worth a 20 minute call, just reply and I'll send times; otherwise I won't follow up again.

**d2_16** draft, open, passes

Subject: Billing after the checkout change

> Rafael, I noticed Quayline Commerce removed a subscription billing widget from its checkout pages. When companies change how billing shows up at checkout, the controller's office often ends up absorbing the follow-on work in invoicing and reconciliation. We built Lumen Ledger so usage-based and recurring charges become accurate invoices without a finance team rebuilding them by hand. I don't know whether any of that applies to you, so I won't guess. Would you be open to a 20-minute call next week to see if it's worth a closer look?

**d2_17** draft linkedin, connect, passes (Limit: 200 characters)

> Dominic, I noticed Northfall Robotics posted a job for a Head of Billing. I spend my days with CFOs on usage-based billing and would be glad to connect.

**d2_18** draft linkedin, connect, passes (Limit: 300 characters)

> Maëlle, I noticed Ateliers Brisemer is hiring a Comptable fournisseurs et clients in Nantes. I talk with controllers about invoicing and would be glad to connect.

**d2_19** draft linkedin, connect, passes (Limit: 150 characters)

> João, I saw Serra Azul Pagamentos launched a per-transaction plan for small merchants. I work on usage-based billing at Lumen Ledger and would be glad to connect with someone in RevOps.

**d2_20** draft linkedin, message, fails: unsupported_about_them (First LinkedIn message after she accepted the connection request.)

> Hana, thanks for connecting. I saw that Ridgeway bills devices per active sensor per month. I also noticed a cloud data warehouse was recently added to the stack. At Lumen Ledger we help revenue operations teams run usage-based billing without finance rebuilding invoices by hand. Would you be open to a short call to compare notes on how per-sensor usage flows into invoicing today?

- judge, faithful: It implies a pain about them: "without finance rebuilding invoices by hand" and "how per-sensor usage flows into invoicing today" are not in the facts, and the first is not framed as a general pattern.

**d2_21** draft linkedin, message, fails: unsupported_about_them (Write in English.)

> Ximena, thanks for connecting. I saw Grupo Altiplano announced freight-by-weight pricing on 3 new routes in northern Mexico. Across 14 distribution centers, that kind of usage-based pricing is where invoices often end up rebuilt by hand. At Lumen Ledger we help finance teams bill on usage without that manual work. Would it be useful if I sent a short overview of how that works?

- judge, faithful: It links the facts to a billing pain with "Across 14 distribution centers, that kind of usage-based pricing is where invoices often end up rebuilt by hand", which implies a process problem at their company; the facts say nothing about it, and "often" only partly frames it as a general pattern.

**d2_22** draft, bump, passes (Bump: one prior email, no reply.)

Subject: Re: billing at Pyxis Fleet Intelligence

> Okonkwo, following up on my last note. I saw Pyxis is hiring a Data Engineer for billing pipelines and recently added a streaming event pipeline. We let usage data flow straight into invoices, so a pricing change does not mean building a new custom pipeline. Would a 20 minute call next week be worth it to see if that fits?

- judge, relevant: The pitch is about usage data flowing into invoices and pricing changes, which touches billing, but the recipient is a Director of Data Engineering, not a finance or revenue leader. The billing-pipeline hire connects it to their work, so it is arguably relevant, but the criterion targets finance and revenue leaders.

**d2_23** draft, follow up, passes (Follow-up after no reply.)

Subject: Per-policy billing at Clearmont

> Winston, following up on my earlier note with one more specific thought. Clearmont started charging carriers per policy quoted through its API, and you are hiring a Revenue Accountant with ASC 606 experience. Companies that add per-unit pricing often find invoicing and revenue schedules turn into spreadsheet work as volume grows. We turn metered usage into invoices and ASC 606 revenue schedules automatically, so finance reviews the numbers instead of rebuilding them. Would a 20-minute call next week be useful to see whether it fits?

**d2_24** draft, open, passes (numbers: $0.004 and the two dates are the only citable figures)

Subject: Per-call pricing from January

> Leopold, I saw that Tessellate Maps announced on 3 November that its geocoding API will cost $0.004 per call starting 1 January 2027. Companies moving to per-call pricing often find that metering, rating and invoicing take more finance time than expected, especially in the first few billing cycles. At Lumen Ledger we handle usage-based billing end to end, so invoices are built from usage data without anyone rebuilding them by hand. Would you be open to a 20 minute call before the January change to see whether it fits?

**d2_25** draft, open, passes

Subject: Per-GB invoicing at Ondaverde

> Beatriz, I saw that Ondaverde Telecom appointed Dagny Oyelowo as Chief Financial Officer in October. I also read that your enterprise customers are billed per GB transferred and invoiced monthly. Finance teams invoicing on metered usage often find that reconciling usage data against invoices takes more manual work as volumes grow. We built Lumen Ledger to turn usage data into accurate invoices so nobody has to rebuild them by hand. Would you be open to a 20-minute call in the next two weeks to see whether it is relevant for Ondaverde?

**d2_26** draft, bump, passes (Bump.)

Subject: billing at Fernbrook Labs

> Emeka, following up on my last note. Corvex Billing appeared on the Fernbrook Labs customer portal in August and was no longer detected there by November. We help finance teams run usage-based billing without rebuilding invoices by hand. Would a 20-minute call this month be worth your time?

**d2_27** draft linkedin, connect, passes (Limit: 200 characters)

> Siobhán, Felix Dunne, your former colleague, suggested I reach out. I work with finance leaders on usage-based billing at Lumen Ledger and would be glad to connect.

**d2_28** draft linkedin, message, passes

> Ravindra, thanks for connecting. I saw that Monsoonware posted a job for an Accounts Receivable Lead. At Lumen Ledger we help finance teams run usage-based billing without rebuilding invoices by hand. Would a short overview of how that works from a controller's side be useful to you?

**d2_29** draft, break up, passes (Break-up email.)

Subject: closing the loop on billing

> Ingrid, I saw Bergtind Cloud posted a role for a Billing Analyst. Teams adding billing headcount often find part of that work is rebuilding invoices by hand, which is what we automate for usage-based pricing. This is my last note, so if it is not a priority I will leave it here. If it is worth a look, would you be open to a 20-minute call next week?

**d2_30** draft, break up, passes (Break-up email.)

Subject: Last note on billing

> Theo, one last note from me. Glasshouse added per-ticket service fees for venue partners and is hiring a Billing Operations Lead. Teams adding per-unit fees often find invoices drift back to manual work as volume grows. We keep usage billing automated end to end. Worth 15 minutes next week?

- judge, one_ask: It is a break-up email but ends with 'Worth 15 minutes next week?', a meeting ask that keeps pressure on instead of closing politely.

## Every brief

**b01**

- Halvard Analytics prices per seat plus usage overages, billed monthly. This may mean their billing has to combine fixed seat charges with variable usage amounts every month.
- They have posted a job for a Revenue Operations Manager. This may mean they are putting more attention on how revenue processes are run.
- Their careers page lists an open Billing Analyst role. This may mean billing work is growing or needs more hands.
- They are hiring for both revenue operations and billing at the same time. This may mean the finance team is building out or reworking how billing and revenue are handled.

Angle: With a per-seat-plus-usage monthly billing model and open Revenue Operations Manager and Billing Analyst roles, they may be reviewing how they run billing and revenue right now.

**b02**

- Corvo Health raised a $40M Series C led by Northwind Partners. This may mean more scrutiny on revenue reporting and finance processes as the company scales.
- Their billing page says invoices are sent quarterly in arrears. This may mean revenue is recognized before it is invoiced, which can make cash timing and reconciliation harder to manage.
- They posted a job for a Senior Revenue Accountant. This may mean the finance team is adding capacity around revenue accounting and could be reviewing how that work gets done.

Angle: Fresh off a $40M Series C and hiring a Senior Revenue Accountant while billing quarterly in arrears, Corvo Health's finance team may be looking at how its billing and revenue processes hold up as it grows.

**b03**

- Brightline Freight moved its API from flat plans to usage-based pricing. This may mean their billing now needs to track usage and turn it into invoices, which flat plans did not require.
- The careers page lists open roles for a Billing Analyst and a Senior Accountant. This may mean the finance team is adding people to handle billing and accounting work.
- The pricing change and the billing hire appear together. This may mean the new usage-based model is adding billing workload that the team is staffing up to handle.

Angle: Brightline Freight just moved its API to usage-based pricing and is hiring a Billing Analyst, so its finance team may be working out how to bill for usage right now.

**b04**

- Sable Robotics left a review of a billing tool that mentions invoice errors. This may mean their current billing setup is producing mistakes they want fixed.
- They posted a job for a Senior Billing Specialist. This may mean billing work is growing or needs more hands on the finance team.
- Their billing page describes annual contracts with monthly usage true-ups. This may mean each invoice has to combine a fixed contract with changing usage, which can be hard to get right by hand.
- Taken together, the invoice-error review, the billing hire, and the contract-plus-usage model may point to billing becoming harder to manage with their current tools.

Angle: Sable Robotics is reviewing a billing tool and noting invoice errors while hiring a Senior Billing Specialist, so they may be open now to software that handles annual contracts with monthly usage true-ups.

**b05** (one thin fact: few findings, none invented)

- Talusa Labs is researching metered billing. This may mean they are considering or moving toward usage-based pricing and looking at how to bill for it, but the facts do not say what they use today or how far along they are.

Angle: Talusa Labs is actively researching metered billing, so a conversation about how their finance team would bill and recognize revenue for usage-based pricing may be timely.

**b06**

- Glasswing Telemetry launched per-event pricing for its ingest API. This may mean their billing now has to handle usage-based charges rather than flat fees.
- Their billing page says usage is metered per million events. This may mean invoices depend on accurate metering data flowing into billing each cycle.
- They posted a job for a Data Engineer, Billing Pipelines. This may mean they are building or reworking the data flow that feeds their billing.
- Taken together, the new per-event pricing, the per-million-event metering, and the billing pipeline hire point to active investment in usage-based billing. This may mean the finance team is weighing whether to build or buy parts of it.

Angle: Having just launched per-event pricing metered per million events and started hiring for billing pipelines, Glasswing's finance team may be working out how to bill usage accurately right now.

**b2_01**

- Ombria Telematics raised a $22M Series B led by Calder Peak Ventures in October 2026. This may mean the finance team is preparing for growth and could be reviewing whether its billing setup will keep up.
- Ombria's billing page says fleet customers pay per vehicle per month. This may mean invoices change as customers add or remove vehicles, which can make billing and revenue tracking more involved.
- Taken together, new funding and per-vehicle monthly pricing may mean that billing work grows as the customer base grows.

Angle: Fresh off a $22M Series B in October 2026 and billing fleet customers per vehicle per month, Ombria's finance team may be checking whether its billing can handle growth.

**b2_02**

- Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. This may mean their billing now has to track usage and combine fixed and variable charges, which flat plans did not require.
- Their billing page says overages are invoiced monthly in arrears. Alongside the platform fee, this may mean more invoices and more usage-based calculations each month than under annual plans.
- They are hiring a Billing Operations Analyst. This may mean billing workload is growing or the team is building out how it handles the new pricing.
- They posted jobs for 4 Account Executives. This may mean they expect more new customers, which could add to billing volume under the usage-based model.
- The company was founded in 2017, is headquartered in Denver, and has 240 employees.

Angle: Thornquist Labs just moved from flat annual plans to a platform fee plus per-API-call overages invoiced monthly in arrears and is hiring a Billing Operations Analyst, so their finance team may be working out how to handle usage-based billing right now.

**b2_03**

- On 3 November 2026, Tessellate Maps announced that its geocoding API will cost $0.004 per call starting 1 January 2027. This may mean they will need to meter API usage and bill customers based on call counts.
- The company says it serves 1,850 business customers across 31 countries. If per-call pricing applies to many of these customers, this may mean usage-based invoicing across a broad, multi-country customer base.
- They posted a job for a Revenue Accountant on 28 October 2026, about a week before the pricing announcement. This may mean the finance team is adding capacity around revenue recognition ahead of the pricing change.

Angle: With per-call API pricing set to begin 1 January 2027 and a Revenue Accountant role just posted, the finance team may be preparing now to bill and account for usage-based revenue.

**b2_04**

- Halberd Security raised a Series B, announced in a September 2026 press release as $35M. A funding database reports the same round as $38M, so the exact size should be confirmed before quoting it.
- The company's about page says it is backed by $53M in total funding. Fresh capital may mean the finance team is reviewing systems as the company scales, but the facts do not say so.
- Its billing page says pricing is per protected endpoint, billed annually. This may mean invoice amounts depend on endpoint counts, which could make mid-term changes or renewals more involved to bill.

Angle: With a newly announced Series B (reported as $35M or $38M) and per-endpoint annual pricing, Halberd's finance team may be looking at how its billing will hold up as it grows.

**b2_05**

- Kestrava launched usage pricing for its routing API. This may mean their finance team now has to meter and invoice variable charges they did not bill before.
- Their billing page says routes are billed per optimized stop. This may mean invoices depend on counting stops accurately each billing period.
- Kestrava posted a job for a Revenue Operations Analyst. This may mean they are adding people to manage revenue processes as pricing changes.

Angle: Kestrava just moved its routing API to usage pricing billed per optimized stop and is hiring a Revenue Operations Analyst, so its finance team may be working out how to bill and track usage-based revenue right now.

**b2_06**

- Pinewick opened a flagship retail store in Portland. This may mean more in-store sales to account for alongside other channels, though the facts say nothing about their finance setup.
- Pinewick added a new e-commerce theme to its website. This shows ongoing investment in online selling; it may mean online orders are a revenue channel the finance team tracks, but the facts do not give volumes or tools.
- Pinewick is hiring seasonal store associates. This may mean sales vary by season, which could affect how revenue is recorded and forecast, but that is not stated.

Angle: There is no clear finance trigger; the only possible opening is that a new flagship store and website changes may mean more sales across retail and online channels for the finance team to reconcile, which is weak and worth confirming before outreach.

**b2_07**

- Lagoa Verde now charges growers per hectare monitored per month. This may mean each monthly invoice depends on a usage count that has to be measured and priced for every customer.
- They have an open role for a mid-level Billing Analyst (Analista de Faturamento Pleno) in Campinas. This may mean billing work is growing faster than the current team can handle.
- Their billing page says boletos and Pix are issued monthly. Combined with per-hectare pricing, this may mean recurring, variable-amount charges have to be generated and reconciled across both payment methods each month.
- They raised R$ 48 million in a Series A round in August 2026. This may mean they are planning growth that would add more customers to bill.

Angle: They just moved to monthly per-hectare pricing billed by boleto and Pix and are hiring a billing analyst. That may point to billing needs outgrowing their current setup.

**b2_08**

- CFO Martin Haldane resigned effective 31 October 2026, and the Corporate Controller is serving as interim CFO. This may mean finance leadership is in transition and decisions on finance systems could be paused or revisited.
- Varrowgen has posted a job for a Chief Financial Officer. This may mean a new finance leader will arrive who could review existing billing and revenue processes.
- Research partners are invoiced per sample processed. This may mean billing depends on tracking usage, which can add work to invoicing and revenue recognition.

Angle: With the CFO gone, an interim CFO in place, and a CFO search open, the finance team may be open to a fresh look at how they handle per-sample invoicing for research partners.

**b2_09**

- Ridgeway bills devices per active sensor per month. This may mean their invoices depend on counting active sensors each period, which is usage-style billing.
- Ridgeway removed a third-party invoicing add-on from its customer portal. This may mean they are changing how invoices are produced or shown to customers, though the facts do not say what replaced it.
- Ridgeway cut headcount by 8% in October 2026, citing a focus on profitability. This may mean the finance team is handling billing work with fewer people and is looking at cost and efficiency.

Angle: With an 8% headcount cut aimed at profitability, per-active-sensor monthly billing, and a recently removed invoicing add-on, Ridgeway's finance team may be rethinking how it runs billing with fewer hands.

**b2_10**

- Marlowe's billing page says data buyers pay per record delivered. This may mean their invoices depend on accurate usage counts, which usage-based billing software is built to handle.
- Marlowe has posted a job for a Billing Systems Manager. This may mean they are building out or reworking how their billing systems are run.
- A trade publication reported Marlowe is in early talks to be acquired, but neither company has confirmed it. If true, this may mean added scrutiny of how revenue is billed and recorded.

Angle: Marlowe is hiring a Billing Systems Manager for a pay-per-record model while reportedly in unconfirmed acquisition talks, so how it bills usage may be getting attention right now.

**b2_11**

- Falkenhain is hiring a specialist for e-invoicing and accounts receivable (Referent E-Rechnung und Debitorenbuchhaltung) in Leipzig. This may mean they are building up or changing how they issue electronic invoices and manage receivables.
- Their maintenance contracts are billed by the machines' operating hours. This may mean their invoices depend on usage data that has to be collected and priced each billing period.
- The company has been family-run since 1962 and has 410 employees, so it is an established mid-sized business.

Angle: They are hiring for e-invoicing and receivables while billing maintenance by operating hours, so they may be reviewing how they produce and send usage-based invoices right now.

**b2_12**

- The company announced it is expanding its freight-by-weight pricing to 3 new routes in northern Mexico. This may mean more usage-based invoices to calculate and bill as those routes come online.
- It operates 14 distribution centers and invoices in both MXN and USD. This may mean billing and revenue reporting have to handle two currencies across multiple sites.
- It is hiring an Accounts Receivable Analyst in Monterrey. This may mean the finance team is adding capacity around collections and receivables.
- It added a Spanish-language customer self-service portal. This may mean customers are being moved toward self-service, which could touch how they view invoices or pay, though the facts do not say what the portal covers.

Angle: With weight-based freight pricing expanding to new routes, invoicing in MXN and USD, and an open AR analyst role, the finance team may be looking at how its billing and collections keep up with the growth.

**b2_13**

- Fernbrook Labs appointed Ama Owusu-Ansah as VP Finance in September 2026. A new finance leader may be reviewing how billing and revenue are handled.
- Corvex Billing was detected on Fernbrook's customer portal in August 2026, then was no longer detected in November 2026. The tool was in place for only a few months. This may mean they dropped it and are without a settled billing tool, or are looking for a replacement.
- Fernbrook's billing page says lab customers pay per assay run. This is usage-based pricing, which may mean they need billing that can track runs and invoice on usage.

Angle: A VP Finance who started in September and a billing tool that came and went between August and November suggest Fernbrook may be rethinking how it bills per-assay-run customers right now.

**b2_14**

- Lattimer Cloud provides object storage for media companies. This may mean their pricing is tied to storage or usage, which can make billing harder to run, but the facts do not say how they charge.
- They are hiring 9 backend engineers and 2 site reliability engineers. This may mean the platform is growing, which could put more load on billing and revenue processes over time.
- They posted a job for a Senior Platform Engineer. Together with the other engineering roles, this may mean they are investing in core platform work, and billing systems might be part of that, though the facts do not say so.

Angle: Lattimer Cloud is hiring heavily on the engineering side for an object storage product sold to media companies, so finance may face growing billing complexity if usage and customers grow, though nothing in the facts confirms a billing need today.
