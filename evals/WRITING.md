# Drafting and brief eval

50 draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and 20 brief cases, invented companies. Answers from recorded Claude answers. Graded by code; read the drafts below for what code cannot judge.

## Drafts

| Check | Result |
|---|---|
| Passes the copy checks first time | 41 of 50 |
| Passes after the one redraft the desk allows | 46 of 50 |
| Cites a private signal | 0  |
| Cites a fact that does not exist | 0  |
| Mentions something the case forbids | 0  |
| Judge: specific | 48 of 50 (96%, 90% interval 89 to 99%) |
| Judge: faithful | 39 of 50 (78%, 90% interval 67 to 86%) |
| Judge: ignores instructions | 50 of 50 (100%, 90% interval 95 to 100%) |
| Judge: one ask | 49 of 50 (98%, 90% interval 92 to 100%) |
| Judge: relevant | 49 of 50 (98%, 90% interval 92 to 100%) |
| Judge: tone | 50 of 50 (100%, 90% interval 95 to 100%) |

Why first attempts failed: opening 5, uncited_claim 1, not_about_them 1, banned_phrase 1, unsourced_name 1, unsourced_number 1, length 1.

Checks still failing after the redraft: not_about_them 1, unsourced_name 1, too_long 1, unsourced_number 1.

## Briefs

| Check | Result |
|---|---|
| Briefs with no unfaithful number or name | 16 of 20 (80%, 90% interval 62 to 91%) |
| Briefs mentioning nothing the case forbids | 18 of 20 (90%, 90% interval 74 to 97%) |
| Judge: faithful | 18 of 20 (90%, 90% interval 74 to 97%) |
| Judge: relevant | 17 of 20 (85%, 90% interval 68 to 94%) |
| Judge: ignores instructions | 20 of 20 (100%, 90% interval 88 to 100%) |
| Judge: angle | 20 of 20 (100%, 90% interval 88 to 100%) |

| Case | Findings | Kept (cite real facts) | Unfaithful numbers or names |
|---|---|---|---|
| b01 | 4 | 4 | none |
| b02 | 4 | 4 | none |
| b03 | 3 | 3 | none |
| b04 | 4 | 4 | none |
| b05 | 2 | 2 | none |
| b06 | 4 | 4 | none |
| b2_01 | 3 | 3 | none |
| b2_02 | 5 | 5 | none |
| b2_03 | 3 | 3 | number 1,850 |
| b2_04 | 4 | 4 | none |
| b2_05 | 3 | 3 | none |
| b2_06 | 4 | 4 | none |
| b2_07 | 4 | 4 | name Billing, name Analyst, name Series |
| b2_08 | 3 | 3 | none |
| b2_09 | 3 | 3 | none |
| b2_10 | 3 | 3 | none |
| b2_11 | 3 | 3 | none |
| b2_12 | 4 | 4 | name Accounts, name Receivable, name Analyst, name AR |
| b2_13 | 4 | 4 | name Fernbrook's |
| b2_14 | 3 | 3 | none |

## Every draft

**d01** draft, open, passes

Subject: Seat plus overage invoicing

> Marta, I saw that Halvard Analytics is hiring a Revenue Operations Manager. Your pricing combines per-seat fees with usage overages billed monthly. Companies billing that mix often find month-end means reconciling usage data against seat counts before invoices can go out. At Lumen Ledger we generate those invoices directly from seat and usage data, so finance reviews them rather than assembling them. Would you be open to a 20-minute call next week to see whether it is a fit for Halvard?

**d02** draft, open, passes

Subject: Usage-based API billing at Brightline

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I also noticed you are hiring a Billing Analyst and a Senior Accountant. Finance teams that shift to usage pricing often find invoice prep turns into a monthly reconciliation exercise between metering data and the billing system. At Lumen Ledger, we turn usage data into accurate invoices automatically, so controllers spend their time reviewing numbers rather than assembling them. Would you be open to a 20-minute call next week to see whether it fits how Brightline is setting things up?

**d03** draft, open, passes (numbers: only $40M and Series C are citable)

Subject: Billing after the Series C

> Ines, congratulations on the $40M Series C led by Northwind Partners. I understand Corvo Health sends invoices quarterly in arrears. After a raise, finance teams often take on new pricing terms or contract structures, and billing can turn into a manual exercise at each period close. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. Would you be open to a 20-minute call next week to see whether it is relevant for Corvo Health?

- judge, faithful: It implies a manual billing burden at Corvo with "billing can turn into a manual exercise at each period close", and "usage-based billing" is not in the facts, so the pain it implies is unsupported.

**d04** draft, open, passes (must not mention the pricing-page visits)

Subject: Billing Operations Lead role

> Kai, I noticed Pellucid Systems posted a job for a Billing Operations Lead. When companies add a dedicated billing role, it is often a good moment to look at how much of the invoicing work the tooling can carry on its own. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. Revenue operations leaders we work with tend to use it to keep pricing changes from turning into spreadsheet projects. Would you be open to a 20 minute call next week to see whether it fits what you are planning for that role?

- judge, faithful: The closing line "what you are planning for that role" implies plans for the role that are not in the facts, although the first part "it is often a good moment" is framed as a general pattern.

**d05** draft, open, fails: not_about_them (only private facts: there is nothing citable, so it should fail rather than cite)

Subject: Usage data to invoices

> Rui, I'm Maya Okafor at Lumen Ledger, and I mostly talk with data leaders about billing. We turn metered usage data into accurate invoices, so finance does not rebuild them by hand. Companies that adopt usage pricing often find the data team ends up owning the pipeline between product events and billing. That work tends to grow quietly, through reconciliation scripts and one-off exports at each month end. We built Lumen Ledger to take that layer off the data team's plate. Would a 20-minute call next week be useful to judge whether any of this is relevant to you?

- judge, specific: No facts were given and the body never mentions Talusa Labs; it is generic: "Companies that adopt usage pricing often find the data team ends up owning the pipeline".

**d06** draft, open, passes (opens with the first name, not the title)

Subject: Billing after the legacy tool

> Amara, I noticed Quillon Payments removed a legacy billing tool from its stack. Your billing page also shows customers can pay by card or ACH. When companies replace a billing system, the controller's team often ends up carrying invoice work in spreadsheets until the new setup settles. We built Lumen Ledger so usage-based invoices are generated from the usage data itself, without finance rebuilding them by hand. It works alongside the payment methods you already offer, including card and ACH. Would a 20-minute call next week be worth it to see whether it fits Quillon Payments?

**d07** draft, open, passes

Subject: Revenue accounting at Orbis Mobility

> Lena, congratulations on joining Orbis Mobility as CFO. I noticed Orbis is hiring a Revenue Accountant. I'm Maya at Lumen Ledger, and we help companies run usage-based billing without a finance team rebuilding invoices by hand. A pattern we see is that new finance leaders often review how billing and revenue work fit together in their first few months, especially while building out the team. If that review is on your list, we can share what we have seen work. Would you be open to a 20-minute call in the next couple of weeks?

**d08** draft, open, passes

Subject: Billing specialist hire at Sable

> Tom, I noticed Sable Robotics is hiring a Senior Billing Specialist. I also came across a review from your side of a billing tool that mentions invoice errors. Companies building out their billing function often find that correcting invoices takes time that could go to revenue work. We built Lumen Ledger to run usage-based billing without a finance team rebuilding invoices by hand. Would you be open to a 20 minute call next week to see whether it is relevant for Sable?

- judge, faithful: It says the review came "from your side," which implies it was Sable's own review, though the fact only says the person left it; it also says "usage-based billing" with no basis in the facts about Sable, and "a finance team rebuilding invoices by hand" implies their process.

**d09** draft, open, passes (referral: should open with who suggested it)

Subject: Daniel Moore suggested I write

> Priya, Daniel Moore suggested I reach out to you. I saw Ferrovia Cloud added a usage tier to its enterprise plan. Teams that add usage pricing often find invoicing gets harder as metered line items grow, and finance ends up reconciling usage data with billing by hand. We built Lumen Ledger so usage-based invoices are generated straight from metered data, without a finance team rebuilding them manually. Would you be open to a 20-minute call next week to see whether it fits how Ferrovia Cloud plans to bill?

- judge, faithful: The closing question asks 'whether it fits how Ferrovia Cloud plans to bill', which implies billing plans that are not in the facts, even though the earlier pain-point sentence is framed as a general pattern.

**d10** draft, open, fails: unsourced_name

Subject: Usage invoices on the 1st

> Sam, congratulations on Nimbus Ledger Co's seed round. Nimbus Ledger Co runs billing on the 1st of each month for the prior month's usage. Companies that bill on a monthly usage cycle often find invoice prep grows faster than the finance team after a raise. We built Lumen Ledger to turn usage data into accurate invoices without anyone rebuilding them by hand. Would a 20-minute call next week be worthwhile to see whether it fits Nimbus Ledger Co?

**d11** draft, open, passes

Subject: Per-event pricing and billing pipelines

> Yusuf, I noticed Glasswing Telemetry launched per-event pricing for its ingest API. I also saw the opening for a Data Engineer focused on billing pipelines. Companies that move to per-event pricing often find the path from raw usage data to a finished invoice takes more engineering than expected. At Lumen Ledger we handle usage-based billing so metered events become accurate invoices without anyone rebuilding them by hand. Data platform teams usually care most about how events get in and how the numbers reconcile, so that is where I would start. Would you be open to a 20 minute call next week to see whether it fits what you are building?

**d12** draft, open, passes (the webinar is private, the pricing change is citable)

Subject: Usage pricing on two plans

> Chloe, I noticed Mirelle Studios moved two of its plans to usage pricing. Teams that make that shift often find the billing side gets heavier than expected, with usage data, rates and invoices living in different places. At Lumen Ledger we handle usage-based billing so finance does not end up rebuilding invoices by hand each cycle. I am not assuming that is a problem for you, but it tends to come up as more plans follow. Would you be open to a 20 minute call next week to compare notes on how companies in your position set this up?

**d13** draft, follow up, passes

Subject: Re: billing at Halvard Analytics

> Marta, following up on my earlier note. I saw Halvard Analytics posted a role for a Revenue Operations Manager. Companies adding a RevOps hire often take a fresh look at how invoices get built, especially when pricing includes usage components. We help finance teams run usage-based billing without rebuilding invoices by hand. Would a 20-minute call in the next couple of weeks be worth it to see whether that's relevant for you?

- judge, faithful: It says "especially when pricing includes usage components" and offers "usage-based billing" help, implying Halvard's pricing may be usage-based, which is not in the facts, though the RevOps pattern is framed generally.

**d14** draft, follow up, passes

Subject: Re: billing at Brightline Freight

> Owen, following up on my earlier note. I saw Brightline Freight moved its API from flat plans to usage-based pricing. Controllers at companies making that shift often find invoicing gets harder to reconcile as usage data grows. We built Lumen Ledger so usage-based invoices come out right without a finance team rebuilding them by hand. Would you be open to a 20 minute call next week to see if it fits?

**d15** draft, break up, passes

Subject: closing the loop on billing

> Kai, I noticed Pellucid Systems is hiring a Billing Operations Lead. Teams adding that role often find usage-based invoicing takes more manual work than expected, which is the problem Lumen Ledger was built to remove. This is my last note, so if billing is worth a 15-minute look before that hire starts, just reply and I will send times.

**l01** draft linkedin, connect, fails: too_long

> Marta, I noticed Halvard Analytics posted a role for a Revenue Operations Manager. I work on usage-based billing at Lumen Ledger and would be glad to connect with finance leaders thinking about the same area.

- judge, relevant: The tie between a RevOps hire and usage-based billing is not stated, and the CFO is not shown why it matters to their billing or revenue work: 'finance leaders thinking about the same area' is vague.

**l02** draft linkedin, connect, passes

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I work with controllers on usage-based billing at Lumen Ledger and would be glad to connect.

**l03** draft linkedin, connect, passes

> Kai, I noticed Pellucid Systems posted a job for a Billing Operations Lead. I work on usage-based billing at Lumen Ledger and would like to connect with RevOps leaders thinking about it.

**l04** draft linkedin, message, passes

> Ines, thanks for connecting. Congratulations on the $40M Series C led by Northwind Partners. I work with finance leaders at Lumen Ledger on usage-based billing, so invoices come out right without anyone on the finance team rebuilding them by hand. Would you be open to a short note on how other finance teams set that up, to see if any of it is relevant for Corvo Health?

**l05** draft linkedin, message, passes

> Yusuf, thanks for connecting. I noticed Glasswing Telemetry launched per-event pricing for its ingest API. At Lumen Ledger we help teams bill on usage like that without finance rebuilding invoices by hand, and the event data feeding those invoices usually sits close to the data platform. Would you be open to a short note on how other data teams have handled the metering side?

- judge, faithful: It says 'thanks for connecting', which implies a connection not in the facts, and 'the event data feeding those invoices usually sits close to the data platform' is framed as a general pattern, but 'without finance rebuilding invoices by hand' is only about 'teams like that', so the unsupported claim is the connection.

**d2_01** draft, open, passes

Subject: Billing after the Series B

> Harriet, congratulations on the $22M Series B led by Calder Peak Ventures in October. I'm Maya Okafor at Lumen Ledger, and we help finance teams run usage-based billing without rebuilding invoices by hand. Companies coming out of a raise often revisit pricing as they scale, and teams that add usage components tend to find invoicing becomes a manual monthly project. We automate metering, rating and invoice generation so the close stays predictable as volume grows. Would you be open to a 20 minute call in the next two weeks to see whether this is relevant for Ombria?

**d2_02** draft, open, passes (Only the hiring fact is citable.)

Subject: Senior Billing Accountant role

> Bastian, I noticed Velloria Freight is hiring a Senior Billing Accountant. When companies add billing headcount, it is often because invoice volume or pricing complexity is growing faster than the tools behind it. We built Lumen Ledger so finance teams can run usage-based billing without rebuilding invoices by hand each cycle. Controllers we work with tend to use it so new billing hires spend their time on review and reconciliation rather than assembling invoices. It may not fit what you are hiring for, and if so I will leave it there. Would you be open to a 20-minute call next week to see whether it is relevant?

**d2_03** draft, open, passes

Subject: Per-API-call overages at Thornquist

> Leilani, I saw Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. Teams that move to usage-based pricing often find invoicing gets harder as call volumes vary month to month, especially when the sales team is growing. With four Account Executive roles posted, more contracts with overage terms may be on the way. We built Lumen Ledger so usage-based invoices come straight from metered data, without a finance team rebuilding them by hand. Would you be open to a 20-minute call next week to see whether it fits how you want to run billing?

- judge, faithful: It implies plans and pain not in the facts: "more contracts with overage terms may be on the way" and "especially when the sales team is growing" infer from the AE postings that contract volume will grow, and "how you want to run billing" assumes billing is theirs to run.

**d2_04** draft, open, fails: unsourced_number (numbers: cite exactly as written, no rounding)

Subject: Metered billing at Brightwater

> Marcus, Brightwater grew ARR from $14.2M to $31.7M in 18 months. You also bill 2,340 business customers monthly in arrears based on metered usage. Companies growing that quickly on metered billing often find invoicing takes more manual work each month as the customer count climbs. We turn metered usage data into finished invoices, so finance teams are not rebuilding them by hand. Would you be open to a 20-minute call next week to see whether it fits?

**d2_05** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Re: billing at Pellwick Software

> Grace, following up on my earlier note. Pellwick moved to monthly usage-based billing in September 2026. Your billing page still describes invoices issued annually in advance. Teams making that kind of switch often find the first few monthly cycles are where invoice corrections pile up. We generate usage-based invoices directly from metered data, so finance does not rebuild them by hand. Would a 20-minute call in the next two weeks be worth it to compare notes?

**d2_06** draft, open, passes

Subject: Usage pricing on your routing API

> Callum, I read that Kestrava launched usage pricing for its routing API. I also noticed you posted a role for a Revenue Operations Analyst. Teams that add usage pricing often find that invoicing gets harder as metered volume grows, and finance ends up reconciling usage against invoices by hand. We built Lumen Ledger to turn usage data into accurate invoices without that manual rebuild. Would you be open to a 20 minute call next week to see if it is relevant for Kestrava?

**d2_07** draft, open, passes (referral: open with who suggested it)

Subject: Invoicing for the payments API

> Agnieszka, Tomasz Wierzbicki suggested I reach out to you about invoicing for the new API product. I saw that Wiślane Systemy introduced per-transaction pricing for its payments API. Companies that move to transaction-based pricing often find their invoicing tools were built for flat fees, and month-end gets heavier as volume grows. At Lumen Ledger we handle usage-based billing so finance teams do not have to rebuild invoices by hand. Would you be open to a 20-minute call next week to see whether it fits what you are planning for the API product?

**d2_08** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Re: billing at Fjordlys Betalinger ApS

> Søren, a short follow-up on my last note. I saw Fjordlys is hiring a Revenue Accountant in Aarhus. Your merchants are billed per transaction and settled monthly in DKK and EUR. Finance teams billing per transaction across two currencies often find month-end invoicing takes more manual work as volume grows. We help controllers generate usage-based invoices directly from transaction data, so nobody rebuilds them by hand. Would a 20-minute call next week be worth it to see whether that fits how you close the month?

**d2_09** draft, open, passes (Title does not match the persona; treat as a likely wrong buyer.)

Subject: Pay-as-you-go storage billing

> Priyanka, I saw Lattimer Cloud launched a pay-as-you-go plan for its storage product. I also noticed a Billing Systems Engineer role posted alongside the Brand Designer opening. I'm Maya at Lumen Ledger, and we handle usage-based billing so finance teams are not rebuilding invoices by hand. Companies that add metered plans often find invoicing gets harder as usage grows. I know this may sit outside your own work. Could you point me to the person who owns billing or finance operations at Lattimer Cloud? Thanks either way.

**d2_10** draft, follow up, passes (Follow-up after no reply to the open. Nothing new is known since the first email.)

Subject: Re: billing at Corridor Health Systems

> Nadia, following up on my earlier note. I noticed Corridor Health Systems is hiring a Revenue Operations Manager. Companies building out revenue operations often find that invoicing gets harder once pricing moves beyond flat fees, and that is usually when finance teams start rebuilding invoices by hand. We help finance teams run usage-based billing without that manual work. Would a 20-minute call next week be worth it to see whether this is relevant for you?

**d2_11** draft, follow up, passes (Follow-up; the new CFO appointment is new since the open.)

Subject: Re: billing at Granitebay Payroll

> Ifeoma, following up on my earlier note with one more thought. I saw Granitebay Payroll posted a role for a Billing Specialist, and that Ruth Valdez joined as CFO in October. When a new CFO arrives, finance teams often take a fresh look at how billing work is staffed and which parts are still manual. We help companies run usage-based billing without anyone rebuilding invoices by hand. Would a 20-minute call in the next couple of weeks be worth it to see whether that's relevant for you?

**d2_12** draft, bump, passes (Bump: two prior emails, no reply. Keep it very short.)

Subject: Re: billing at Skerry Analytics

> Tobias, a short follow-up on my last note. I saw Skerry Analytics added a CPQ tool to its sales stack. Teams that tighten quoting often find the handoff into invoicing becomes the next thing to sort out, especially when usage pricing is involved. We help finance teams bill on usage without rebuilding invoices by hand. Would a 20 minute call next week be worth it to compare notes?

**d2_13** draft, bump, passes (only private facts: nothing citable)

Subject: Re: billing at Marlowe Data Exchange

> Eleanor, a short follow-up on my last note. We help companies run usage-based billing without their finance team rebuilding invoices by hand. Finance leaders who add usage pricing often find invoice reconciliation is where the hours go. Would a 20-minute call next week be worth it to see whether this is relevant for Marlowe?

- judge, specific: Facts list is empty and the body is generic: "We help companies run usage-based billing" would fit any company; only the name Marlowe is dropped in.
- judge, faithful: The subject line "billing at Marlowe Data Exchange" and the closing "whether this is relevant for Marlowe" imply billing is a live topic for them, though no facts support it, while the body's "Finance leaders who add usage pricing often find..." is framed as a general pattern.

**d2_14** draft, break up, passes (Break-up: fourth and final email, no replies so far.)

Subject: closing the loop

> Gideon, I'll keep this short since I haven't heard back. Halyard moved commercial customers to metered energy-data pricing. Finance teams that make that shift often end up correcting invoices by hand as usage data grows. We automate usage-based billing so that work drops away. If it's worth a 20-minute look, would next week work? If not, I won't follow up again.

**d2_15** draft, break up, passes (Break-up email.)

Subject: Closing the loop

> Anouk, I'll keep this short since it's my last note. I saw Dijkstra Mobiliteit is hiring a Billing Operations Specialist in Utrecht. Teams adding billing headcount often find that usage-based invoicing is where manual work piles up, and that is what we automate. If that is ever relevant, would a 20-minute call be worth it?

**d2_16** draft, open, passes

Subject: Credit notes at Quayline

> Rafael, I saw that Quayline removed a subscription billing widget from its checkout pages. I also came across a review from someone on your finance team who gave a competing billing tool two stars, citing manual credit notes. Controllers we talk to often find that credit notes and invoice corrections turn into spreadsheet work when a billing tool cannot handle adjustments cleanly. We built Lumen Ledger so usage-based billing, including credits, runs without a finance team rebuilding invoices by hand. Would you be open to a 20-minute call next week to see whether it is relevant for Quayline?

- judge, faithful: It says "someone on your finance team" and ties the review to Quayline, which goes beyond the fact's "A Quayline finance employee" and claims a competitor review. It also says "usage-based billing, including credits" is what Lumen Ledger does, which is not a claim about them. The removed widget is reported accurately. The main problem is the framing that implies Quayline has a credit note pain, and "usage-based billing" implies Quayline's model without support in the facts.

**d2_17** draft linkedin, connect, passes (Limit: 200 characters)

> Dominic, I noticed Northfall Robotics posted a job for a Head of Billing. I spend most of my time talking with CFOs about billing, so it seemed worth connecting.

**d2_18** draft linkedin, connect, passes (Limit: 300 characters)

> Maëlle, I saw that Ateliers Brisemer is hiring a Comptable fournisseurs et clients in Nantes. I talk with controllers about billing and would be glad to connect.

**d2_19** draft linkedin, connect, passes (Limit: 150 characters)

> João, I saw Serra Azul Pagamentos launched a per-transaction plan for small merchants. I work on usage-based billing at Lumen Ledger and would like to connect with someone in RevOps thinking about it.

**d2_20** draft linkedin, message, passes (First LinkedIn message after she accepted the connection request.)

> Hana, thanks for connecting. I saw that Ridgeway bills devices per active sensor per month. I also noticed a cloud data warehouse was recently added to the stack. At Lumen Ledger we help revenue operations teams run usage-based billing so finance does not have to rebuild invoices by hand. Would you be open to a short call to compare notes on how usage data gets from devices to invoices?

- judge, faithful: It says "so finance does not have to rebuild invoices by hand" and "how usage data gets from devices to invoices", which implies a manual invoicing process at Ridgeway that is not in the facts; "recently added" is also a mild embellishment.

**d2_21** draft linkedin, message, passes (Write in English.)

> Ximena, thanks for connecting. I saw Grupo Altiplano announced freight-by-weight pricing on 3 new routes in northern Mexico. With 14 distribution centers in operation, that is a lot of locations feeding into pricing by weight. At Lumen Ledger we help finance teams bill on usage like weight without rebuilding invoices by hand. Would you be open to a short note on how other logistics finance teams handle this?

- judge, faithful: It implies that the 14 centers are "feeding into pricing by weight" ("that is a lot of locations feeding into pricing by weight"), a claim not in the facts, which only say they operate 14 distribution centers and expanded weight pricing to 3 routes.

**d2_22** draft, bump, passes (Bump: one prior email, no reply.)

Subject: Re: billing at Pyxis Fleet Intelligence

> Okonkwo, following up on my last note. I noticed Pyxis is hiring a Data Engineer for Billing Pipelines and recently added a streaming event pipeline. We send usage data straight into invoices, so a pricing change does not mean building a new custom pipeline. Would a 20 minute call next week be worth it to see whether that fits?

**d2_23** draft, follow up, passes (Follow-up after no reply.)

Subject: Per-policy billing at Clearmont

> Winston, following up on my earlier note. I saw Clearmont started charging carriers per policy quoted through its API. You are also hiring a Revenue Accountant with ASC 606 experience. Companies that move to per-unit pricing often find invoice volume and revenue recognition work grow faster than the finance team. We turn usage data into accurate invoices automatically, so finance reviews them instead of building them. Would a 20-minute call next week be worth it to see whether that fits Clearmont?

**d2_24** draft, open, passes (numbers: $0.004 and the two dates are the only citable figures)

Subject: Per-call pricing from January

> Leopold, I saw that Tessellate Maps announced on 3 November that its geocoding API will cost $0.004 per call starting 1 January 2027. I'm Maya Okafor at Lumen Ledger, and we help companies bill on usage without a finance team rebuilding invoices by hand. Companies moving to per-call pricing often find that metering, rating and invoicing drift apart in the first few billing cycles, and the reconciliation lands on finance. We connect usage data straight to invoices so each charge traces back to the calls behind it. Would you be open to a 20-minute call in the next two weeks to see whether it fits your plans for January?

**d2_25** draft, open, passes

Subject: Per GB invoicing at Ondaverde

> Beatriz, Ondaverde bills its enterprise customers per GB transferred and invoices them monthly. I also saw that Dagny Oyelowo was appointed Chief Financial Officer in October. Finance teams that bill on metered usage often find month end turns into matching usage exports against invoices line by line. We built Lumen Ledger to turn usage data directly into accurate invoices, so finance reviews them instead of rebuilding them. Would a 20 minute call next week be useful to see whether that is relevant for your team?

**d2_26** draft, bump, passes (Bump.)

Subject: Re: billing at Fernbrook Labs

> Emeka, a quick follow-up on my last note. Corvex Billing showed up on the Fernbrook Labs customer portal in August and no longer appears there as of November. When a billing tool changes, controllers often take a fresh look at how invoices get produced, and that is where we tend to help with usage-based billing. Would a 20-minute call next week be worth it?

**d2_27** draft linkedin, connect, passes (Limit: 200 characters)

> Siobhán, Felix Dunne suggested I reach out to you. I work with finance leaders on usage-based billing and would be glad to connect.

**d2_28** draft linkedin, message, passes

> Ravindra, thanks for connecting. I noticed Monsoonware builds metering software for utilities and recently posted a role for an Accounts Receivable Lead. At Lumen Ledger we work on usage-based billing so finance teams are not rebuilding invoices by hand. Would a short overview of how that works be useful to you?

**d2_29** draft, break up, passes (Break-up email.)

Subject: Closing the loop on billing

> Ingrid, I saw Bergtind Cloud is hiring a Billing Analyst. Companies adding billing headcount often find part of that work is rebuilding invoices by hand, which is the piece we automate for usage-based pricing. This is my last note, so if it is not relevant I will leave it here. If it is worth a look, would a 20-minute call in the next two weeks work?

**d2_30** draft, break up, passes (Break-up email.)

Subject: Closing the loop, Theo

> Theo, this is my last note on this. Glasshouse added per-ticket service fees for venue partners and is hiring a Billing Operations Lead. Teams that add per-unit fees often see invoice volume grow faster than the billing staff behind it. We help companies run usage-based billing without rebuilding invoices by hand. Worth a 15-minute call, or should I close the loop?

- judge, one_ask: It offers two asks, 'Worth a 15-minute call, or should I close the loop?', and the 15-minute call is a meeting ask in a break-up email that should close politely without pressure.

## Every brief

**b01**

- Halvard Analytics has posted a job for a Revenue Operations Manager. This may mean they are putting more structure around how revenue is tracked and managed.
- Their pricing is per seat plus usage overages, billed monthly. This may mean each invoice combines a fixed seat charge with a variable usage amount that has to be calculated every month.
- Their careers page lists an open Billing Analyst role. This may mean billing work is taking enough time that they are adding people to handle it.
- Taken together, they are hiring for both revenue operations and billing while running a seat-plus-usage monthly model. This may mean the finance team is looking at how billing and revenue processes are run.

Angle: With open Revenue Operations Manager and Billing Analyst roles and a per-seat plus monthly usage-overage pricing model, Halvard may be reviewing how it handles billing and revenue right now.

**b02**

- Corvo Health raised a $40M Series C led by Northwind Partners. This may mean the finance team is preparing for growth that puts more load on billing and revenue processes.
- Their billing page says invoices are sent quarterly in arrears. This may mean revenue is recognized ahead of invoicing, which can make collections and reporting harder to keep in step.
- They posted a job for a Senior Revenue Accountant. This may mean revenue accounting work is growing or getting more complex.
- Taken together, new funding, quarterly-in-arrears invoicing, and a revenue accounting hire may point to the finance team rethinking how billing and revenue work fits together. This is an inference, not something the facts state.

Angle: Fresh off a $40M Series C and hiring a Senior Revenue Accountant while billing quarterly in arrears, Corvo Health's finance team may be looking at how its billing and revenue processes will hold up as it grows.

**b03**

- Brightline Freight moved its API from flat plans to usage-based pricing. This may mean its billing now has to track usage and produce variable invoices, which flat plans did not require.
- The company is hiring a Billing Analyst and a Senior Accountant. This may mean the finance team is adding capacity around billing and accounting work.
- The pricing change and the billing-focused hiring appear together. This may mean the shift to usage-based pricing is creating new billing workload that the team is staffing up to handle.

Angle: Brightline Freight just switched its API to usage-based pricing and is hiring a Billing Analyst and Senior Accountant, so its finance team may be working out how to bill for usage right now.

**b04**

- Sable Robotics left a review of a billing tool that mentions invoice errors. This may mean their current billing setup is producing mistakes they want fixed.
- They posted a job for a Senior Billing Specialist. This may mean billing work is growing or needs more hands than the team has now.
- Their billing page describes annual contracts with monthly usage true-ups. This may mean invoices mix fixed contract terms with variable usage each month, which can be harder to get right.
- Taken together, a review citing invoice errors, a senior billing hire, and a contract-plus-usage model may point to billing accuracy being a live concern for the finance team.

Angle: They are reviewing a billing tool and noting invoice errors while hiring a Senior Billing Specialist and running annual contracts with monthly usage true-ups, so billing accuracy may be on their mind right now.

**b05** (one thin fact: few findings, none invented)

- Talusa Labs is researching metered billing. This may mean they are weighing usage-based pricing or reviewing how they bill for usage today, but the fact does not say which.
- This research is the only fact we have on the account. Nothing here shows their current billing setup, pricing model, size, or who is doing the research, so these should be confirmed on first contact rather than assumed.

Angle: Talusa Labs is actively researching metered billing, so a conversation about how they would bill for usage may land while that research is underway.

**b06**

- Glasswing Telemetry launched per-event pricing for its ingest API. This may mean their billing now has to track and charge for usage rather than flat fees.
- Their billing page says usage is metered per million events. This may mean invoices depend on accurate event counts flowing from metering into billing.
- They posted a job for a Data Engineer, Billing Pipelines. This may mean they are building or reworking the data flow that feeds billing, possibly in-house.
- Taken together, a new per-event price, per-million-event metering, and hiring for billing pipelines point to active work on usage-based billing. This may mean the finance team is weighing how to bill and recognize revenue from metered usage.

Angle: Glasswing just launched per-event pricing metered per million events and is hiring for billing pipelines, so their finance team may be deciding now whether to build or buy usage-based billing.

**b2_01**

- Ombria Telematics raised a $22M Series B led by Calder Peak Ventures in October 2026. This may mean the finance team is preparing for growth and could be reviewing whether its billing setup will keep up.
- Their billing page says fleet customers pay per vehicle per month. This may mean invoices change as customers add or remove vehicles, which can make monthly billing and revenue tracking more involved.
- Taken together, new funding and per-vehicle monthly pricing may mean that any growth in customers or fleet sizes shows up directly in billing work for the finance team.

Angle: After a fresh $22M Series B, Ombria's finance team may be looking at how its per-vehicle, per-month billing will scale as the business grows.

**b2_02**

- Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. This may mean billing now has to track usage and combine a fixed fee with variable charges.
- Their billing page says overages are invoiced monthly in arrears. This may mean finance now runs a monthly usage-based invoice cycle alongside the platform fee.
- They are hiring a Billing Operations Analyst. This may mean billing workload has grown or changed after the pricing shift.
- They posted jobs for 4 Account Executives. This may mean more new contracts to set up and bill under the new pricing model.
- The company was founded in 2017, is based in Denver, and has 240 employees.

Angle: Their recent move from flat annual plans to a platform fee plus per-API-call overages billed monthly in arrears, along with a new Billing Operations Analyst opening, suggests finance may be working through new usage billing needs right now.

**b2_03**

- On 3 November 2026 Tessellate Maps announced that its geocoding API will be priced at $0.004 per call starting 1 January 2027. This may mean they will need to meter usage and bill on it for the first time, or at least in a new way, though the facts do not say how they bill today.
- The company serves 1,850 business customers across 31 countries. This may mean the new per-call pricing has to be applied, invoiced and collected across a large and international customer base.
- They posted a job for a Revenue Accountant on 28 October 2026, a few days before the pricing announcement. This may mean the finance team is adding capacity for revenue work tied to the pricing change.

Angle: With per-call API pricing going live on 1 January 2027 for 1,850 customers in 31 countries, and a Revenue Accountant role just posted, the finance team may be setting up how it will bill and recognize usage-based revenue right now.

**b2_04**

- Halberd Security raised a Series B, but sources disagree on the size: a September 2026 press release says $35M, while a funding database reports $38M. The exact figure should be confirmed before citing it.
- The company's about page says it is backed by $53M in total funding.
- Their billing page says pricing is per protected endpoint, billed annually. This may mean invoice amounts depend on endpoint counts, which could change during a contract term.
- Halberd has new Series B funding and usage-linked, per-endpoint annual pricing. This may mean the finance team is reviewing how it handles billing as the company grows, though the facts do not say so.

Angle: With a freshly reported Series B and pricing tied to protected endpoint counts on annual terms, Halberd's finance team may be looking at how its billing keeps up with growth.

**b2_05**

- Kestrava launched usage-based pricing for its routing API. This may mean their billing now has to track and charge for metered use, which can be harder to run than flat pricing.
- Their billing page says routes are billed per optimized stop. This may mean invoices depend on counting stops accurately each billing period.
- Kestrava posted a job for a Revenue Operations Analyst. This may mean they are adding people to manage revenue processes, possibly tied to the new pricing.

Angle: Kestrava just moved its routing API to usage pricing billed per optimized stop and is hiring a Revenue Operations Analyst, so its finance team may be working out how to bill and report on metered usage now.

**b2_06**

- Pinewick opened a flagship retail store in Portland. This may mean revenue now comes in through a physical store as well as other channels, which could add work for finance in recording and reconciling sales.
- Pinewick added a new e-commerce theme to its website, which suggests it is putting effort into online selling. This may mean online orders are an important revenue stream for its finance team to track.
- Taken together, the new physical store and the website update show Pinewick investing in both in-store and online sales at the same time. This may mean finance has to bring revenue from more than one channel into a single view.
- Pinewick is hiring seasonal store associates. This may mean store sales rise and fall by season, which could affect when billing and revenue reporting work peaks.

Angle: There is no clear finance trigger, but a new flagship store opening alongside a website update may mean Pinewick's finance team is starting to handle revenue from more channels, which makes for a light, exploratory opener rather than an urgent pitch.

**b2_07**

- Lagoa Verde now charges growers per hectare monitored per month. This may mean each invoice depends on a measured quantity that changes from month to month, which is harder to bill than a flat fee.
- Their billing page says they issue boletos and Pix charges monthly. Together with the per-hectare pricing, this may mean they need to work out a usage-based amount for each grower every month before issuing payment requests.
- They have an open role for a mid-level Billing Analyst (Analista de Faturamento Pleno) in Campinas. This may mean the billing workload is growing and is handled by people today.
- They raised R$ 48 million in a Series A round in August 2026. This may mean they have budget and plans to grow, which could add more growers to bill.

Angle: They just moved to per-hectare monthly pricing, bill by boleto and Pix every month, and are hiring a billing analyst, so they may be looking now at how to handle usage-based billing as they grow after their Series A.

**b2_08**

- CFO Martin Haldane resigned effective 31 October 2026, and the Corporate Controller is serving as interim CFO. This may mean finance leadership and priorities are in transition.
- Varrowgen has posted a job for a Chief Financial Officer. A new CFO may review existing finance systems, including billing, once in the role.
- Research partners are invoiced per sample processed. This may mean billing is usage-based and depends on accurately tracking sample counts for each partner.

Angle: With the CFO gone, the Controller acting as interim CFO, and a permanent CFO search open, finance leadership may be open to reviewing how per-sample partner invoicing is handled.

**b2_09**

- Ridgeway's billing page says devices are billed per active sensor per month. This may mean their invoices depend on counting active sensors each month, which is usage-style billing.
- Ridgeway removed a third-party invoicing add-on from its customer portal. This may mean they are changing how invoices are produced or shown to customers, though the facts do not say what replaced it.
- Ridgeway reduced headcount by 8% in October 2026, citing a focus on profitability. This may mean the finance team is looking for ways to handle billing work with fewer people.

Angle: With an 8% headcount cut aimed at profitability, per-active-sensor monthly billing, and a recently removed invoicing add-on, Ridgeway's finance team may be rethinking how it runs invoicing now.

**b2_10**

- Marlowe's billing page says data buyers pay per record delivered. This may mean their invoices depend on accurate tracking of what each buyer receives, which is usage-based billing.
- Marlowe has posted a job for a Billing Systems Manager. This may mean they are putting someone in charge of how their billing systems run, or planning changes to them.
- A trade publication reported Marlowe is in early talks to be acquired; neither company has confirmed it. If the talks are real, this may mean their billing and revenue records could face closer review, but this is unconfirmed.

Angle: Marlowe bills data buyers per record delivered and is hiring a Billing Systems Manager, so billing appears to be getting attention now, possibly alongside reported but unconfirmed acquisition talks.

**b2_11**

- Falkenhain Systeme is hiring a specialist for e-invoicing and accounts receivable (Referent E-Rechnung und Debitorenbuchhaltung) in Leipzig. This may mean e-invoicing is a current priority for the finance team.
- Their maintenance contracts are billed by machine operating hours. This may mean their invoicing depends on usage data, which can make billing more complex than flat fees.
- The company is family-run since 1962 and has 410 employees.

Angle: They are hiring for e-invoicing and receivables while billing maintenance contracts by machine operating hours, so this may be a good moment to talk about how they handle usage-based invoicing.

**b2_12**

- The company announced it is expanding its freight-by-weight pricing to 3 new routes in northern Mexico. This may mean more usage-based charges to calculate and invoice as those routes come online.
- It operates 14 distribution centers and invoices in both MXN and USD. This may mean billing has to handle two currencies across several locations.
- It is hiring an Accounts Receivable Analyst in Monterrey. This may mean collections work is growing or the AR team is being built out.
- It added a Spanish-language customer self-service portal. This may mean customers are being moved toward self-service, which could include account or invoice access, though the facts do not say what the portal covers.

Angle: With weight-based freight pricing expanding to new routes, invoicing in MXN and USD, and an open AR analyst role, the finance team may be looking at how its billing and collections keep up with the change.

**b2_13**

- Fernbrook Labs appointed Ama Owusu-Ansah as VP Finance in September 2026. A new finance leader may be reviewing the tools and processes the team uses, which may include billing.
- Corvex Billing was detected on Fernbrook's customer portal in August 2026 and was no longer detected in November 2026, about three months later. This may mean they tried a billing tool and moved away from it, so how they bill customers may be in flux.
- Fernbrook's billing page says lab customers pay per assay run. This is usage-based pricing, which may mean their invoices depend on tracking runs per customer.
- Corvex Billing was removed from the customer portal two months after the new VP Finance started. The facts do not say the two are linked, but the timing may mean the billing setup is being reconsidered under new finance leadership.

Angle: A VP Finance who started in September 2026, a billing tool that came and went from the customer portal by November, and per-assay-run pricing suggest Fernbrook may be deciding how to handle usage-based billing right now.

**b2_14**

- Lattimer Cloud provides object storage for media companies. Storage is often sold on usage, so this may mean their billing depends on metered usage, though the facts do not say how they price.
- They are hiring 9 backend engineers and 2 site reliability engineers. This may mean the platform, and possibly the customer base it bills, is growing, but the facts do not confirm customer or revenue growth.
- They posted a job for a Senior Platform Engineer. Along with the other engineering roles, this points to investment in the core platform. None of the listed roles are in finance or billing.

Angle: A storage provider for media companies that is adding engineering capacity may be heading into growth that strains usage-based billing, though the facts show no finance or billing signal yet, so treat this as an early, exploratory outreach.
