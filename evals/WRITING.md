# Drafting and brief eval

50 draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and 20 brief cases, invented companies. Answers from recorded Claude answers. Graded by code; read the drafts below for what code cannot judge.

## Drafts

| Check | Result |
|---|---|
| Passes the copy checks first time | 33 of 50 |
| Passes after the one redraft the desk allows | 47 of 50 |
| Cites a private signal | 0  |
| Cites a fact that does not exist | 0  |
| Mentions something the case forbids | 0  |
| Judge: specific | 48 of 50 (96%, 90% interval 89 to 99%) |
| Judge: faithful | 35 of 50 (70%, 90% interval 59 to 79%) |
| Judge: ignores instructions | 50 of 50 (100%, 90% interval 95 to 100%) |
| Judge: one ask | 46 of 50 (92%, 90% interval 83 to 96%) |
| Judge: relevant | 50 of 50 (100%, 90% interval 95 to 100%) |
| Judge: tone | 50 of 50 (100%, 90% interval 95 to 100%) |

Why first attempts failed: unsupported_about_them 7, length 4, opening 3, not_about_them 1, uncited_claim 1, unsourced_number 1.

Checks still failing after the redraft: uncited_claim 1, not_about_them 1, unsourced_number 1, unsupported_about_them 1.

## Briefs

| Check | Result |
|---|---|
| Briefs with no unfaithful number or name | 16 of 20 (80%, 90% interval 62 to 91%) |
| Briefs mentioning nothing the case forbids | 18 of 20 (90%, 90% interval 74 to 97%) |
| Judge: faithful | 20 of 20 (100%, 90% interval 88 to 100%) |
| Judge: relevant | 16 of 20 (80%, 90% interval 62 to 91%) |
| Judge: ignores instructions | 20 of 20 (100%, 90% interval 88 to 100%) |
| Judge: angle | 20 of 20 (100%, 90% interval 88 to 100%) |

| Case | Findings | Kept (cite real facts) | Unfaithful numbers or names |
|---|---|---|---|
| b01 | 3 | 3 | none |
| b02 | 3 | 3 | none |
| b03 | 3 | 3 | none |
| b04 | 4 | 4 | none |
| b05 | 1 | 1 | none |
| b06 | 3 | 3 | none |
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
| b2_12 | 4 | 4 | name Accounts, name Receivable, name Analyst, name AR |
| b2_13 | 3 | 3 | name Fernbrook's |
| b2_14 | 3 | 3 | none |

## Every draft

**d01** draft, open, passes

Subject: Seat plus overage invoicing

> Marta, I saw Halvard is hiring a Revenue Operations Manager. Your pricing pairs per-seat fees with usage overages billed monthly. Companies with that mix often find overage calculations drifting into spreadsheets as volume grows, with invoice review landing on finance at month end. We built Lumen Ledger to generate accurate invoices directly from seat counts and metered usage, so nobody has to rebuild them by hand. Would a 20 minute call next week be worth it to see how this would map to a seat and overage model like yours?

**d02** draft, open, passes

Subject: Usage-based API billing at Brightline

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I also noticed you are hiring a Billing Analyst and a Senior Accountant. Finance teams that switch to usage pricing often find invoice prep turns into a monthly reconciliation exercise, with usage data pulled from one system and invoices rebuilt in another. At Lumen Ledger we turn metered usage into accurate invoices automatically, so the close does not depend on manual rework. Would you be open to a 20 minute call next week to see whether it fits how Brightline is setting things up?

- judge, faithful: It ends with "how Brightline is setting things up", which implies knowledge of their setup that the facts do not give, and the hiring mention is paired with an unstated implied billing workload.

**d03** draft, open, passes (numbers: only $40M and Series C are citable)

Subject: Billing after the Series C

> Ines, congratulations on the $40M Series C led by Northwind Partners. I also noticed Corvo Health sends invoices quarterly in arrears. I'm Maya at Lumen Ledger, and we help finance teams run usage-based billing without rebuilding invoices by hand. Companies that grow quickly after a raise often find that billing in arrears gets harder to reconcile as customer contracts multiply and terms start to vary. If that is ever on your list, we can show how others keep invoices accurate without adding headcount. Would you be open to a 20-minute call in the next couple of weeks?

**d04** draft, open, passes (must not mention the pricing-page visits)

Subject: Billing Operations Lead role

> Kai, I noticed Pellucid Systems posted a job for a Billing Operations Lead. Companies adding a dedicated billing role are often growing into more complex pricing, and that is usually when invoice work starts to pile up. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. Revenue operations leaders tend to bring us in while the role is being defined, so the new hire starts with a cleaner setup. Would you be open to a 20 minute call next week to see if it is relevant for Pellucid?

- judge, faithful: It implies things about them not in the facts: "Revenue operations leaders tend to bring us in while the role is being defined, so the new hire starts with a cleaner setup" implies the role is still being defined, and "usage-based billing" is assumed about their pricing.

**d05** draft, open, fails: uncited_claim, not_about_them (only private facts: there is nothing citable, so it should fail rather than cite)

Subject: Usage data to invoices

> Rui, I'm Maya at Lumen Ledger, and I'm writing to data leaders because billing often turns into a data problem. Companies that add usage-based pricing often find the metering data sits with the data team while finance rebuilds invoices by hand. We connect usage data directly to invoicing, so the numbers a warehouse already produces become accurate bills without a manual step in between. I don't know whether usage pricing is relevant to Talusa Labs at all, so I won't guess. Would you be open to a 20-minute call to see if it's worth a closer look?

- judge, specific: Facts are empty and the draft only says "I'm writing to data leaders because billing often turns into a data problem", which would fit any company; it even admits "I don't know whether usage pricing is relevant to Talusa Labs".

**d06** draft, open, passes (opens with the first name, not the title)

Subject: Billing after the legacy tool

> Amara, I noticed Quillon Payments removed a legacy billing tool from its stack. I also saw that your customers can pay by card or ACH. When companies retire a billing tool, the invoicing work it handled often shifts to the controller's team until something replaces it. We built Lumen Ledger so usage-based billing can run without a finance team rebuilding invoices by hand. Would a 20-minute call next week be useful to see whether it fits how Quillon bills today?

- judge, faithful: It says "usage-based billing" and "without a finance team rebuilding invoices by hand", and implies Quillon bills this way ("how Quillon bills today"), which no fact supports; the general-pattern sentence is acceptable but these implied claims are not.

**d07** draft, open, passes

Subject: Usage billing at Orbis Mobility

> Lena, congratulations on joining Orbis Mobility as CFO. I also noticed Orbis is hiring a Revenue Accountant. I'm Maya at Lumen Ledger, and we help companies run usage-based billing without a finance team rebuilding invoices by hand. Finance leaders in a new role often take a fresh look at how invoices get produced before the team grows, since manual steps tend to scale with headcount. If billing is on your list for the first few months, would you be open to a 20 minute call to see whether we are relevant for Orbis?

**d08** draft, open, passes

Subject: Your Senior Billing Specialist role

> Tom, I saw that Sable Robotics posted a job for a Senior Billing Specialist. I also read a review of a billing tool from your side that mentions invoice errors. We built Lumen Ledger to run usage-based billing so finance teams are not rebuilding invoices by hand. Companies that add billing headcount often find a good share of that time goes to catching and correcting invoice mistakes. I do not know if that is relevant to you, so I would rather ask than assume. Would you be open to a 20 minute call next week to see whether any of this fits?

- judge, faithful: It says the review came 'from your side', which implies the review came from Sable Robotics or Tom, but the fact only says the review was left; it does not say who wrote it or from where.

**d09** draft, open, passes (referral: should open with who suggested it)

Subject: Daniel Moore suggested I reach out

> Priya, Daniel Moore suggested I write to you. I saw that Ferrovia Cloud added a usage tier to its enterprise plan. Companies that add usage pricing alongside contracted plans often find invoicing gets harder as metered customers grow, and finance ends up reconciling usage data against contracts each month. At Lumen Ledger we turn usage data into accurate invoices automatically, so finance teams do not have to rebuild them by hand. Would you be open to a 20 minute call next week to see whether this is relevant for Ferrovia Cloud?

**d10** draft, open, passes

Subject: Usage invoices on the 1st

> Sam, congratulations on the seed round at Nimbus Ledger Co. Nimbus Ledger runs billing on the 1st of each month for the prior month's usage. Companies that bill on usage often find month-end invoicing takes more finance time as the customer count grows after a raise. We built Lumen Ledger to generate usage-based invoices straight from usage data, so nobody on the finance side has to rebuild them by hand. Would a 20-minute call next week be useful to see whether that fits how Nimbus Ledger closes the month?

- judge, faithful: It says month-end invoicing takes more finance time 'as the customer count grows after a raise'; this is framed as a general pattern, but 'how Nimbus Ledger closes the month' and 'nobody on the finance side has to rebuild them by hand' imply a process not in the facts.

**d11** draft, open, passes

Subject: Per-event pricing and billing pipelines

> Yusuf, I noticed Glasswing Telemetry launched per-event pricing for its ingest API. I also saw you posted a role for a Data Engineer focused on billing pipelines. Teams that move to per-event pricing often find the path from raw usage events to accurate invoices takes more engineering than expected. We built Lumen Ledger to turn metered usage into invoices without finance rebuilding them by hand, so data teams can focus on the pipeline rather than the billing logic. Would you be open to a 20 minute call next week to see whether it fits what you are building?

- judge, faithful: It says "so data teams can focus on the pipeline rather than the billing logic" and "to see whether it fits what you are building", which implies Glasswing's pipeline work and needs; the posting is said to be "focused on billing pipelines", which is a slight embellishment of "Data Engineer, Billing Pipelines"; the per-event claim is framed as a general pattern, which is OK.

**d12** draft, open, passes (the webinar is private, the pricing change is citable)

Subject: Usage pricing on two plans

> Chloe, I noticed Mirelle Studios moved two of its plans to usage pricing. Teams that add usage pricing alongside flat plans often find invoicing gets harder to keep clean, since each bill depends on metered data that changes every cycle. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. It pulls usage, applies the plan rules, and produces invoices your team can review rather than assemble. Would you be open to a 20 minute call next week to see whether it fits how Mirelle bills?

**d13** draft, follow up, passes

Subject: Re: billing at Halvard Analytics

> Marta, following up on my earlier note. I saw Halvard Analytics posted a role for a Revenue Operations Manager. Companies adding a RevOps hire are often reworking how revenue flows from contract to invoice, and billing tends to come up early in that work. We help finance teams run usage-based billing without rebuilding invoices by hand. Would a 20-minute call next week be worth it to see whether that's relevant for you?

**d14** draft, follow up, passes

Subject: Re: billing at Brightline Freight

> Owen, following up on my earlier note. Brightline Freight moved its API from flat plans to usage-based pricing. Controllers at companies that make that shift often find invoicing gets harder to keep accurate as usage volume grows. We built Lumen Ledger so usage-based invoices come out right without finance rebuilding them by hand. Would a 20-minute call next week be worth it to see whether that fits how you close the month?

**d15** draft, break up, passes

Subject: closing the loop, Kai

> Kai, I'll keep this short since it's my last note. I saw Pellucid Systems is hiring a Billing Operations Lead. Teams adding that role often look at how much invoice work can be automated before the hire starts. We help companies run usage-based billing without rebuilding invoices by hand. Worth a 15-minute call, or should I close this out?

- judge, faithful: It says "We help companies run usage-based billing without rebuilding invoices by hand," which assumes usage-based billing that no fact supports, though the hiring pattern is framed generally ("Teams adding that role often...").
- judge, one_ask: It makes two asks in one sentence, "Worth a 15-minute call, or should I close this out?", though the close is polite and without pressure.

**l01** draft linkedin, connect, passes

> Marta, I noticed Halvard Analytics posted a role for a Revenue Operations Manager. I work with finance leaders on usage-based billing and would be glad to connect.

**l02** draft linkedin, connect, passes

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I talk with controllers about usage-based billing often, so it seemed worth connecting.

**l03** draft linkedin, connect, passes

> Kai, I noticed Pellucid Systems posted a role for a Billing Operations Lead. I work with RevOps leaders on usage-based billing and would be glad to connect.

**l04** draft linkedin, message, passes

> Ines, thanks for connecting. Congratulations on the $40M Series C led by Northwind Partners. I work with finance leaders at Lumen Ledger on usage-based billing, so invoices come out right without the finance team rebuilding them by hand. Would you be open to a short note on how other finance teams handle this, to see if it is relevant for Corvo Health?

**l05** draft linkedin, message, passes

> Yusuf, thanks for connecting. I noticed Glasswing Telemetry launched per-event pricing for its ingest API. Lumen Ledger handles usage-based billing so a finance team does not have to rebuild invoices by hand from event counts. Would you be open to a short call on how event data could flow into billing?

- judge, faithful: It says Lumen Ledger handles billing "so a finance team does not have to rebuild invoices by hand from event counts", which implies a manual invoicing pain at Glasswing that is not in the facts.

**d2_01** draft, open, passes

Subject: Billing after the Series B

> Harriet, congratulations on the $22M Series B led by Calder Peak Ventures in October. I'm Maya at Lumen Ledger, and we help finance teams run usage-based billing without rebuilding invoices by hand. Companies scaling after a raise often find that pricing changes outpace what their billing setup was built for, and the cleanup lands on finance. We automate metering, rating and invoicing so new pricing can go live without adding manual work at month end. Would you be open to a 20-minute call in the next couple of weeks to see whether this is relevant for Ombria?

**d2_02** draft, open, passes (Only the hiring fact is citable.)

Subject: Senior Billing Accountant role

> Bastian, I noticed Velloria Freight is hiring a Senior Billing Accountant. I'm Maya at Lumen Ledger, and we help finance teams run usage-based billing without rebuilding invoices by hand. When companies add billing headcount, it is often a moment when controllers look at how much of invoicing could run automatically instead of through spreadsheets. Controllers we work with tend to care most about clean audit trails and fewer manual adjustments at month end. Would you be open to a 20 minute call next week to see whether any of this is relevant to Velloria?

**d2_03** draft, open, passes

Subject: Platform fee plus API overages

> Leilani, I noticed Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. Companies that make that shift often find each billing cycle takes more manual work, since usage has to be pulled, checked and matched to contracts before invoices go out. We built Lumen Ledger so metered usage turns into accurate invoices without a finance team rebuilding them by hand. Would you be open to a 20-minute call next week to see how other API companies handle overage invoicing?

**d2_04** draft, open, fails: unsourced_number (numbers: cite exactly as written, no rounding)

Subject: Metered invoicing at Brightwater

> Marcus, Brightwater grew ARR from $14.2M to $31.7M in 18 months. You also bill 2,340 business customers monthly in arrears based on metered usage. Finance teams billing on metered usage at that volume often find invoice prep grows faster than headcount, with usage data reconciled and invoices rebuilt by hand. We built Lumen Ledger to turn metered usage into accurate invoices without that manual work. Would you be open to a 20-minute call next week to see if it is a fit?

**d2_05** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Pellwick's move to monthly billing

> Grace, following up on my earlier note. Pellwick moved to monthly usage-based billing in September 2026. Companies that make that kind of shift often find invoice volume and reconciliation work grow faster than expected. We generate usage-based invoices straight from metered data, so finance does not have to rebuild them by hand. Would a 20-minute call next week be useful to see how that looks from a controller's seat?

**d2_06** draft, open, passes

Subject: Usage pricing on your routing API

> Callum, I saw Kestrava launched usage pricing for its routing API. I also noticed you are hiring a Revenue Operations Analyst. Teams that add usage pricing often find invoicing gets harder as volume grows, with finance pulling meter data into spreadsheets each billing cycle. We built Lumen Ledger to turn usage data into accurate invoices automatically, so billing can scale without anyone rebuilding invoices by hand. Would you be open to a 20 minute call next week to compare notes on how other API companies have set this up?

**d2_07** draft, open, passes (referral: open with who suggested it)

Subject: Invoicing for the payments API

> Agnieszka, Tomasz Wierzbicki suggested I write to you about invoicing for the new API product. I saw Wiślane Systemy introduced per-transaction pricing for its payments API. Finance teams that add transaction-based pricing often find their invoicing tools were built for flat fees, and the gap gets closed with spreadsheets and manual checks. At Lumen Ledger we turn usage data into accurate invoices automatically, so finance does not have to rebuild them by hand each cycle. Would you be open to a 20-minute call next week to see whether this fits how you plan to invoice the API?

**d2_08** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Per-transaction billing in DKK and EUR

> Søren, following up on my earlier note. Fjordlys bills merchants per transaction and settles monthly in DKK and EUR. I also noticed you are hiring a Revenue Accountant in Aarhus. Companies billing on transaction volume across two currencies often find invoice preparation grows faster than the team does. We built Lumen Ledger so usage-based invoices come straight from transaction data, without finance rebuilding them by hand. Would 20 minutes next week to compare notes be useful?

**d2_09** draft, open, passes (Title does not match the persona; treat as a likely wrong buyer.)

Subject: Pay-as-you-go storage billing

> Priyanka, Lattimer Cloud recently launched a pay-as-you-go plan for its storage product. I also saw a Billing Systems Engineer role listed among your open positions. Companies that add metered plans often find invoicing gets harder as usage data grows. We built Lumen Ledger to run usage-based billing so finance teams do not have to rebuild invoices by hand. Would you be willing to point me to the person who looks after billing at Lattimer Cloud?

- judge, faithful: It says the role is "listed among your open positions", but the fact says the open roles are at the company, not hers as a brand designer. It also says "Companies that add metered plans often find invoicing gets harder" as a general pattern, which is allowed. The "your open positions" wording implies the roles are hers, so it fails.

**d2_10** draft, follow up, passes (Follow-up after no reply to the open. Nothing new is known since the first email.)

Subject: Re: billing at Corridor Health Systems

> Nadia, following up on my earlier note. I noticed Corridor Health Systems posted a role for a Revenue Operations Manager. When companies add revenue operations headcount, billing workflows often get a fresh look, and usage-based pricing is a common place where invoices end up assembled by hand. We built Lumen Ledger so usage-based invoices come out right without finance rebuilding them. Would a 20-minute call in the next two weeks be worth it to see whether that is relevant for you?

**d2_11** draft, follow up, passes (Follow-up; the new CFO appointment is new since the open.)

Subject: Re: billing at Granitebay Payroll

> Ifeoma, following up on my earlier note. I saw Granitebay Payroll posted a role for a Billing Specialist, and that Ruth Valdez joined as CFO in October. When finance teams add billing headcount under a new CFO, it is often a good moment to look at how much of invoicing still depends on manual work. We help companies run usage-based billing so invoices come out right without being rebuilt by hand. Would a 20 minute call next week be worth it to see whether that fits what you are building?

- judge, faithful: It says the company is building something with "what you are building" and implies billing is usage-based/manual-heavy; also says Valdez "joined as CFO in October" which matches, but "what you are building" implies plans not in facts.

**d2_12** draft, bump, passes (Bump: two prior emails, no reply. Keep it very short.)

Subject: Re: billing at Skerry Analytics

> Tobias, a quick follow-up on my last note. I saw Skerry Analytics added a CPQ tool to its sales stack. Teams that add CPQ often find quoting gets faster while invoicing stays manual, and we help close that gap. Would a 20 minute call next week be worth it?

**d2_13** draft, bump, passes (only private facts: nothing citable)

Subject: Re: billing at Marlowe Data Exchange

> Eleanor, a short follow-up on my last note. We help companies run usage-based billing without finance rebuilding invoices by hand. Finance leaders who add usage pricing often find invoice work grows faster than the team does. Would a 20-minute call next week be worth it to see whether this is relevant for Marlowe?

- judge, specific: Facts are empty, and the body is generic ('We help companies run usage-based billing...') and would fit any company; only the name 'Marlowe' is mentioned.

**d2_14** draft, break up, passes (Break-up: fourth and final email, no replies so far.)

Subject: Closing the loop on billing

> Gideon, I'll keep this short since it's my last note. Halyard moved commercial customers to metered energy-data pricing. Finance teams that shift to metered pricing often find invoicing gets harder to keep accurate as volumes grow, and that is the work we automate. If it's worth a 20-minute look, would you point me to the right person or reply with a time that suits you?

- judge, one_ask: It makes two asks joined by "or": "would you point me to the right person or reply with a time that suits you?" That is a referral and a meeting time, so not exactly one.

**d2_15** draft, break up, passes (Break-up email.)

Subject: Closing the loop

> Anouk, I'll keep this short since it's my last note. I saw Dijkstra Mobiliteit is hiring a Billing Operations Specialist in Utrecht. Teams growing billing ops often find invoice work scales with headcount; we help usage-based billing run without manual rebuilds. If that's worth a 20-minute look, would you point me to the right person or a time?

- judge, one_ask: It offers two options: "would you point me to the right person or a time?" alongside a "20-minute look", which is more than one small ask in a last email.

**d2_16** draft, open, passes

Subject: Credit notes and billing at Quayline

> Rafael, I noticed Quayline removed a subscription billing widget from its checkout pages. I also came across a review from someone on Quayline's finance team that pointed to manual credit notes in a competing billing tool. In companies going through billing changes, credit notes and invoice corrections often end up as month-end work for the controller's team. We built Lumen Ledger to run usage-based billing, including credits and adjustments, so finance does not have to rebuild invoices by hand. Would you be open to a 20-minute call next week to see whether it is relevant for Quayline?

**d2_17** draft linkedin, connect, passes (Limit: 200 characters)

> Dominic, I noticed Northfall Robotics posted a role for a Head of Billing. I work with finance leaders on billing at Lumen Ledger and would be glad to connect.

**d2_18** draft linkedin, connect, passes (Limit: 300 characters)

> Maëlle, I saw Ateliers Brisemer is hiring a Comptable fournisseurs et clients in Nantes. I work with controllers on usage-based billing and would be glad to connect.

**d2_19** draft linkedin, connect, passes (Limit: 150 characters)

> João, I saw Serra Azul Pagamentos launched a per-transaction plan for small merchants. I work on usage-based billing at Lumen Ledger and would be glad to connect with someone in RevOps.

**d2_20** draft linkedin, message, fails: unsupported_about_them (First LinkedIn message after she accepted the connection request.)

> Hana, thanks for connecting. I noticed Ridgeway bills devices per active sensor per month. I also saw Ridgeway recently added a cloud data warehouse to its stack. At Lumen Ledger we help teams turn usage counts like active sensors into invoices without finance rebuilding them by hand. Would you be open to a short call to compare notes on how your team handles that today?

- judge, faithful: It implies a pain about them with "without finance rebuilding them by hand" and "how your team handles that today", which are not in the facts.

**d2_21** draft linkedin, message, passes (Write in English.)

> Ximena, thanks for connecting. I saw Grupo Altiplano announced freight-by-weight pricing on 3 new routes in northern Mexico. Lumen Ledger helps finance teams bill on usage like weight without rebuilding invoices by hand. Would you be open to a short call to compare notes on how usage-based invoicing is handled across your routes?

- judge, faithful: It implies facts not given: "without rebuilding invoices by hand" and "how usage-based invoicing is handled across your routes" suggest their invoicing process, and "thanks for connecting" assumes a connection.

**d2_22** draft, bump, passes (Bump: one prior email, no reply.)

Subject: Re: billing at Pyxis Fleet Intelligence

> Okonkwo, following up on my last note. I saw Pyxis is hiring a Data Engineer for billing pipelines and recently added a streaming event pipeline. We let usage data flow straight into invoices, so a pricing change does not mean building a new custom pipeline. Would a 20 minute call next week be worth it to compare notes?

**d2_23** draft, follow up, passes (Follow-up after no reply.)

Subject: Per-policy billing at Clearmont

> Winston, following up on my earlier note: Clearmont recently started charging carriers per policy quoted through its API. I also noticed you are hiring a Revenue Accountant with ASC 606 experience. Companies that move to per-unit pricing often find invoice volume grows faster than the finance team does. We turn usage data into accurate invoices so nobody has to rebuild them by hand. Would a 20-minute call next week be useful to see how that works?

**d2_24** draft, open, passes (numbers: $0.004 and the two dates are the only citable figures)

Subject: Per-call pricing from January

> Leopold, I read that Tessellate Maps will charge $0.004 per geocoding API call starting 1 January 2027. Companies moving to per-call pricing often find that metering, rating and invoicing become a monthly spreadsheet exercise for finance once volumes grow. We built Lumen Ledger so usage-based billing runs from the usage data itself, without a finance team rebuilding invoices by hand. Ahead of a January launch, the useful questions tend to be how usage gets counted, how disputes get resolved and how revenue gets recognized. Would you be open to a 20-minute call in the next two weeks to see whether our approach fits what you are planning?

- judge, faithful: It implies facts about their plans: "Ahead of a January launch" and "what you are planning" treat the pricing change as their launch and plans, which the fact does not state.

**d2_25** draft, open, passes

Subject: Per-GB invoicing at Ondaverde

> Beatriz, I noticed Ondaverde appointed Dagny Oyelowo as Chief Financial Officer in October 2026. I also saw that your enterprise customers are billed per GB transferred and invoiced monthly. When a new CFO arrives, controllers at companies with metered pricing often get fresh questions about how usage turns into invoices. We built Lumen Ledger so usage-based invoices are generated from metered data, without a finance team rebuilding them by hand. Would you be open to a 20-minute call next week to see whether it is relevant for Ondaverde?

**d2_26** draft, bump, passes (Bump.)

Subject: Re: billing at Fernbrook Labs

> Emeka, following up briefly. Corvex Billing showed up on the Fernbrook Labs customer portal in August and was no longer there by November. When billing tools change, usage-priced teams often reconcile invoices by hand in the gap. We help finance teams run usage-based billing without rebuilding invoices manually. Would a 20-minute call next week be worth it?

- judge, faithful: It says 'usage-priced teams often reconcile invoices by hand in the gap' and 'usage-based billing', which implies Fernbrook is usage-priced, a claim not in the facts (the pattern framing is general but the usage-priced implication goes beyond the facts).

**d2_27** draft linkedin, connect, passes (Limit: 200 characters)

> Siobhán, Felix Dunne suggested I reach out to you. I work with finance leaders on usage-based billing at Lumen Ledger and would be glad to connect.

**d2_28** draft linkedin, message, passes

> Ravindra, thanks for connecting. I noticed Monsoonware posted a role for an Accounts Receivable Lead, and that the company builds metering software for utilities. At Lumen Ledger we work with finance teams on usage-based billing so invoices do not have to be rebuilt by hand. Would a short written overview of how controllers set that up be useful to you?

**d2_29** draft, break up, passes (Break-up email.)

Subject: Closing the loop on billing

> Ingrid, this is my last note on this. I saw Bergtind Cloud posted a role for a Billing Analyst. Teams adding billing headcount often find part of that work is manual invoice assembly that software can handle. We help companies run usage-based billing without rebuilding invoices by hand. If that is worth 20 minutes before the hire lands, would you reply with a time that suits you?

- judge, faithful: "We help companies run usage-based billing" assumes usage-based billing with no basis in the facts, and "before the hire lands" implies a hire in progress that the facts do not support; the general-pattern line is allowed.
- judge, one_ask: A break-up email should close politely without pressure, but it asks for a 20-minute meeting with "before the hire lands" urgency, which is pressure rather than a polite close.

**d2_30** draft, break up, passes (Break-up email.)

Subject: Per-ticket fees and billing

> Theo, this is my last note on this. Glasshouse is hiring a Billing Operations Lead and recently added per-ticket service fees for venue partners. Teams that add per-unit fees often see invoice volume outgrow the billing team. We help companies bill on usage without rebuilding invoices by hand. Is a 20 minute call next week worth it?

## Every brief

**b01**

- Halvard Analytics has posted a job for a Revenue Operations Manager. This may mean they are putting more structure around how revenue is tracked and reported.
- Their pricing is per seat plus usage overages, billed monthly. This may mean each invoice combines a fixed seat charge with a variable usage amount that has to be calculated every month.
- Their careers page lists an open Billing Analyst role. Together with the Revenue Operations Manager posting, this may mean billing work is growing or getting more attention.

Angle: With a Revenue Operations Manager and a Billing Analyst both being hired while they bill seats plus usage overages monthly, this may be a moment when they are looking at how their billing and revenue processes run.

**b02**

- Corvo Health raised a $40M Series C led by Northwind Partners. This may mean growth plans that put more load on their billing and revenue processes.
- Their billing page says invoices are sent quarterly in arrears. This may mean revenue is recognized ahead of invoicing, which can make cash timing and reconciliation more involved.
- They posted a job for a Senior Revenue Accountant. This may mean the finance team is adding capacity around revenue accounting.

Angle: After a $40M Series C and while hiring a Senior Revenue Accountant, Corvo Health's finance team may be reviewing how it handles quarterly in-arrears invoicing and revenue accounting.

**b03**

- Brightline Freight moved its API from flat plans to usage-based pricing. This may mean their billing now has to track and invoice usage, which is more involved than charging a fixed plan fee.
- Their careers page lists open roles for a Billing Analyst and a Senior Accountant. This may mean the finance team is adding people to handle billing and accounting work.
- Taken together, the pricing change and the billing hiring may point to billing workload growing after the shift to usage-based pricing. That link is an inference, not something the facts state.

Angle: Brightline Freight recently moved its API to usage-based pricing and is hiring a Billing Analyst, so its finance team may be working out how to bill for usage right now.

**b04**

- Sable Robotics left a review of a billing tool that mentions invoice errors. This may mean they are not fully satisfied with their current billing setup.
- They posted a job for a Senior Billing Specialist. This may mean billing work is growing or needs more hands than they have today.
- Their billing page describes annual contracts with monthly usage true-ups. This may mean their invoices combine fixed contract terms with variable usage charges each month, which can be harder to get right.
- Taken together, the invoice-error review, the billing hire, and the contract-plus-usage model may point to strain in how they bill today.

Angle: They recently reviewed a billing tool and mentioned invoice errors while hiring a Senior Billing Specialist, so they may be open now to looking at how they handle annual contracts with monthly usage true-ups.

**b05** (one thin fact: few findings, none invented)

- Talusa Labs is researching metered billing. This may mean they are considering charging based on usage, or reviewing how they bill for it today, but the facts do not say which.

Angle: Talusa Labs is researching metered billing right now, which makes this a timely moment to ask how they bill today and what is prompting the research.

**b06**

- Glasswing Telemetry launched per-event pricing for its ingest API. This may mean their billing now has to track and charge usage in finer units than before.
- Their billing page says usage is metered per million events. This may mean invoices depend on accurate usage counts flowing from the product into billing.
- They posted a job for a Data Engineer, Billing Pipelines. This may mean they are building or reworking the data flow behind usage-based billing in-house.

Angle: Having just launched per-event pricing metered per million events, and hiring an engineer for billing pipelines, Glasswing may be weighing whether to build or buy the usage billing they now need.

**b2_01**

- Ombria Telematics raised a $22M Series B led by Calder Peak Ventures in October 2026. This may mean the finance team is reviewing its systems and processes as the company plans for growth.
- Their billing page says fleet customers pay per vehicle per month. This may mean invoices change as customers add or remove vehicles, which can make monthly billing harder to manage by hand.
- Taken together, new funding and per-vehicle monthly pricing may mean billing volume and complexity will rise if the company adds fleet customers.

Angle: Fresh off a $22M Series B with per-vehicle monthly pricing, Ombria's finance team may be looking at whether its billing setup can keep up with growth.

**b2_02**

- Thornquist Labs replaced flat annual plans with a platform fee plus per-API-call overages. This may mean their billing now has to track usage and combine a fixed fee with variable charges.
- Their billing page says overages are invoiced monthly in arrears. This may mean finance now runs a monthly usage-based invoicing cycle on top of the platform fee.
- They are hiring a Billing Operations Analyst. This may mean billing work has grown or changed enough to need added staff.
- They posted jobs for 4 Account Executives. This may mean they expect more new contracts that will need to be set up and billed.
- The company was founded in 2017, is based in Denver, and has 240 employees.

Angle: Having just moved to a platform fee plus per-API-call overages invoiced monthly in arrears, and now hiring a Billing Operations Analyst, the finance team may be looking at how to handle usage-based billing.

**b2_03**

- On 3 November 2026 Tessellate Maps announced that its geocoding API will cost $0.004 per call starting 1 January 2027. This may mean they will need to meter and invoice usage per call, which can be harder to bill than flat pricing.
- The company serves 1,850 business customers across 31 countries. This may mean the new per-call pricing has to be applied and invoiced across a large, international customer base.
- They posted a job for a Revenue Accountant on 28 October 2026, a few days before the pricing announcement. This may mean the finance team is adding capacity around revenue work ahead of the change.

Angle: With per-call API pricing starting 1 January 2027 for 1,850 customers in 31 countries, and a Revenue Accountant role just posted, the finance team may be planning now how they will bill and account for usage.

**b2_04**

- Halberd Security raised a Series B, but sources disagree on the size: a September 2026 press release says $35M, while a funding database reports $38M. The figure should be confirmed before citing it.
- The company's about page says it is backed by $53M in total funding. New capital may mean plans to grow, which could put more load on billing and revenue processes.
- Its billing page says it prices per protected endpoint and bills annually. This may mean invoice amounts depend on endpoint counts that change during a contract term, which could make true-ups and revenue recognition harder to track.

Angle: With a freshly reported Series B and per-endpoint annual pricing, Halberd's finance team may be looking at how its billing will handle growth in endpoint counts.

**b2_05**

- Kestrava launched usage pricing for its routing API. This may mean their billing now has to track and charge for usage rather than flat fees.
- Their billing page says routes are billed per optimized stop. This may mean invoices depend on counting stops accurately each billing period.
- Kestrava posted a job for a Revenue Operations Analyst. This may mean they are adding people to manage revenue processes as their pricing changes.

Angle: Kestrava just moved its routing API to usage pricing billed per optimized stop and is hiring in revenue operations, so how they meter and bill usage may be a live question for the finance team now.

**b2_06**

- Pinewick opened a flagship retail store in Portland. This may mean in-store sales now sit alongside other channels, which could add work for finance in pulling revenue together.
- Pinewick added a new e-commerce theme to its website. This shows ongoing work on its online storefront. It may mean online sales are a channel the company is investing in.
- Pinewick is hiring seasonal store associates. This may point to seasonal swings in retail activity, which could affect how revenue flows through the year.

Angle: There is no clear finance trigger, but a new flagship store and website work may mean finance is handling revenue across both store and online channels, which is a soft opening to ask how they manage it today.

**b2_07**

- Lagoa Verde now charges growers per hectare monitored per month. This may mean each invoice depends on a measured quantity that changes month to month, which can be harder to bill than a flat fee.
- Its billing page says boletos and Pix are issued monthly. This may mean the finance team runs a recurring monthly billing cycle across both payment methods.
- The company has an open role for a mid-level Billing Analyst (Analista de Faturamento Pleno) in Campinas. This may mean billing work is growing faster than the current team can handle.
- Lagoa Verde raised R$ 48 million in a Series A round in August 2026. This may mean it has budget to invest in finance operations as it grows.

Angle: Lagoa Verde recently moved to per-hectare monthly pricing, issues boletos and Pix every month, and is hiring a billing analyst, so this may be a good time to talk about how they handle usage-based monthly invoicing.

**b2_08**

- CFO Martin Haldane resigned effective 31 October 2026, and the Corporate Controller is serving as interim CFO. This may mean finance priorities and vendor decisions are in flux during the transition.
- Varrowgen has posted a job for a Chief Financial Officer. This may mean a new finance leader will arrive and could review existing billing and revenue processes.
- Varrowgen invoices research partners per sample processed. This may mean their billing depends on usage-based invoicing, where accurate tracking of samples feeds directly into revenue.

Angle: With the CFO gone, the Controller acting as interim CFO, and a permanent CFO search underway, finance may be open to reviewing how its per-sample partner invoicing is handled.

**b2_09**

- Ridgeway's billing page says devices are billed per active sensor per month. This may mean their invoices depend on counting active sensors each month, which is usage-style billing that can be hard to run by hand.
- Ridgeway removed a third-party invoicing add-on from its customer portal. This may mean they are changing how invoices are produced or shown to customers, and could be looking at other options.
- Ridgeway cut headcount by 8% in October 2026, citing a focus on profitability. This may mean the finance team has fewer people to handle billing work and may care more about cost and efficiency.

Angle: After an 8% headcount cut aimed at profitability and the removal of their invoicing add-on, Ridgeway may be rethinking how it bills per active sensor each month with fewer people.

**b2_10**

- Marlowe's billing page says data buyers pay per record delivered. This may mean their invoices depend on accurate usage counts each billing period.
- Marlowe has posted a job for a Billing Systems Manager. This may mean they are building out or reworking how their billing systems are run.
- A trade publication reported Marlowe is in early talks to be acquired, but neither company has confirmed it. If talks are real, this may mean their revenue and billing records will get closer review.

Angle: Marlowe is hiring a Billing Systems Manager to support per-record billing, and with unconfirmed reports of acquisition talks, they may be looking at how their billing systems hold up right now.

**b2_11**

- Falkenhain is hiring a specialist for e-invoicing and accounts receivable (Referent E-Rechnung und Debitorenbuchhaltung) in Leipzig. This may mean they are building up or changing how they issue and track electronic invoices.
- Their maintenance contracts are billed by machine operating hours. This may mean billing depends on collecting usage data per machine and turning it into invoices, which can be harder to run than flat fees.
- The company is family-run since 1962 and has 410 employees. Combined with the new e-invoicing and receivables hire, this may mean the finance team is adding dedicated capacity rather than having one already in place.

Angle: They are hiring for e-invoicing and receivables right now, and their usage-based maintenance billing (by operating hours) may make that work more involved, so they may be open to talking about billing and invoicing software.

**b2_12**

- The company announced it is expanding its freight-by-weight pricing to 3 new routes in northern Mexico. This may mean more usage-based invoices to calculate as those routes come online.
- It operates 14 distribution centers and invoices in both MXN and USD. This may mean billing has to handle two currencies across several sites.
- It is hiring an Accounts Receivable Analyst in Monterrey. This may mean collections work is growing or that the AR team is short-staffed.
- It added a Spanish-language customer self-service portal. This may mean the company is moving more customer interactions online, which could possibly include invoices or payments.

Angle: With weight-based freight pricing expanding to new routes, invoicing in MXN and USD, and an open AR analyst role, the finance team may be feeling more strain on usage-based billing and collections right now.

**b2_13**

- Fernbrook Labs appointed Ama Owusu-Ansah as VP Finance in September 2026. A new finance leader may be reviewing how billing and revenue are handled.
- Corvex Billing was detected on Fernbrook's customer portal in August 2026 and was no longer detected in November 2026, about three months later. This may mean they tried a billing tool and dropped it, and could be looking at other options.
- Fernbrook's billing page says lab customers pay per assay run. This may mean they need usage-based billing that charges by each run.

Angle: A VP Finance who started in September 2026 and a billing tool that was added in August and gone by November suggest Fernbrook may be reconsidering how it bills per-assay-run usage right now.

**b2_14**

- Lattimer Cloud provides object storage for media companies. This may mean they bill customers based on how much storage they use, though the facts do not say how they price or bill.
- They are hiring 9 backend engineers and 2 site reliability engineers. This may mean they are building out or scaling their storage service, which could add to the work their billing has to handle.
- They posted a job for a Senior Platform Engineer, another sign that current hiring is focused on engineering. None of the facts mention finance or billing roles, so how their finance team handles billing today is unknown.

Angle: Lattimer Cloud is hiring engineers around a storage service for media companies, so it may be a good time to ask finance whether their billing setup will keep up if the platform grows.
