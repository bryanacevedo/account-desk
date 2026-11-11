# Drafting and brief eval

20 draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and 6 brief cases, invented companies. Answers from recorded Claude answers. Graded by code; read the drafts below for what code cannot judge.

## Drafts

| Check | Result |
|---|---|
| Passes the copy checks first time | 17 of 20 |
| Passes after the one redraft the desk allows | 19 of 20 |
| Cites a private signal | 0  |
| Cites a fact that does not exist | 0  |

Why first attempts failed: not_about_them 1, unsourced_name 1, opening 1.

Checks still failing after the redraft: uncited_claim 1, not_about_them 1.

## Briefs

| Case | Findings | Kept (cite real facts) | Unfaithful numbers or names |
|---|---|---|---|
| b01 | 4 | 4 | none |
| b02 | 4 | 4 | none |
| b03 | 3 | 3 | none |
| b04 | 4 | 4 | none |
| b05 | 2 | 2 | none |
| b06 | 4 | 4 | none |

## Every draft

**d01** draft, open, passes

Subject: Monthly overage billing at Halvard

> Marta, Halvard prices per seat plus usage overages billed monthly, which usually means someone on finance reconciles usage data against invoices every close. I also noticed you are hiring a Revenue Operations Manager. We built Lumen Ledger so usage-based charges flow straight from metered data to invoices, without anyone rebuilding them by hand in spreadsheets. That can let a new RevOps hire focus on pricing and forecasting rather than invoice cleanup. Would you be open to a 20 minute call next week to see whether it fits how Halvard bills today?

**d02** draft, open, passes

Subject: Usage-based billing at Brightline

> Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. You are also hiring a Billing Analyst and a Senior Accountant, which suggests the invoicing load is growing. That shift often leaves controllers reconciling usage data and rebuilding invoices by hand each month. We built Lumen Ledger to turn metered usage into accurate invoices automatically, so the close does not depend on spreadsheets. Would you be open to a 20 minute call next week to compare notes on how you are handling usage invoicing today?

**d03** draft, open, passes (numbers: only $40M and Series C are citable)

Subject: Quarterly arrears invoicing after Series C

> Ines, congratulations on the $40M Series C led by Northwind Partners. I noticed Corvo Health sends invoices quarterly in arrears. As customer counts grow after a raise, that model often means finance spends the end of each quarter reconciling usage and rebuilding invoices by hand. We help finance teams run usage-based billing straight from product data, so invoices go out accurate without manual rework. Would you be open to a 20-minute call next week to see whether this fits how your team bills today?

**d04** draft, open, passes (must not mention the pricing-page visits)

Subject: Billing Operations Lead role

> Kai, I noticed Pellucid Systems is hiring a Billing Operations Lead. That hire often comes up when invoices start needing manual rework as pricing gets more usage-based. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices by hand. Teams usually use us to pull usage data straight into accurate invoices, so the new lead can focus on pricing and process rather than spreadsheet cleanup. Would you be open to a 20 minute call next week to compare how your team handles this today?

**d05** draft, open, fails: uncited_claim, not_about_them (only private facts: there is nothing citable, so it should fail rather than cite)

Subject: Usage data to invoices

> Rui, I'm Maya Okafor at Lumen Ledger, and I'm writing to you because you lead data at Talusa Labs. We help companies bill on usage without a finance team rebuilding invoices by hand. In our work, the data team usually ends up owning the usage pipeline that billing depends on, along with the reconciliation questions when numbers don't match. We take metered events as they are and turn them into invoices finance can trust, so the data team stops being the backstop. Would you be open to a 20 minute call next week to compare notes on how usage reaches billing at Talusa Labs today?

**d06** draft, open, passes (opens with the first name, not the title)

Subject: Billing after the legacy tool

> Amara, it looks like Quillon recently removed a legacy billing tool from its stack. With customers paying by card or ACH, that usually leaves the controller's team reconciling two payment streams while the replacement settles in. We built Lumen Ledger so usage-based billing runs without finance rebuilding invoices by hand, and payments map back to the right invoice automatically. If invoicing is still partly manual after the change, I can walk you through how other assistant controllers have closed that gap. Would a 20 minute call next week be worth it?

**d07** draft, open, passes

Subject: Usage billing at Orbis Mobility

> Lena, congratulations on joining Orbis Mobility as CFO. Orbis Mobility currently has an open Revenue Accountant role. We help finance teams run usage-based billing so nobody has to rebuild invoices by hand each cycle. When usage data shifts month to month, that manual work usually lands on the people closing revenue. Would a 20 minute call in the next two weeks be useful to compare notes on how you plan to handle billing as the team grows?

**d08** draft, open, passes

Subject: Billing hire and invoice errors

> Tom, I saw that Sable Robotics is hiring a Senior Billing Specialist. I also came across a review from your side of a billing tool that called out invoice errors. Taken together, that often points to usage data and invoices being reconciled by hand. We built Lumen Ledger so usage-based billing flows from metered data to correct invoices, without finance rebuilding them line by line. That could let your new billing hire focus on pricing and collections instead of fixing errors. Would a 20 minute call next week be useful to see how this would fit your current billing setup?

**d09** draft, open, passes (referral: should open with who suggested it)

Subject: Billing for your new usage tier

> Priya, Daniel Moore suggested I write to you. I saw Ferrovia Cloud added a usage tier to its enterprise plan. Usage pricing tends to put pressure on finance, since invoices built for flat plans often end up being adjusted by hand each cycle. At Lumen Ledger we handle usage-based billing so metered charges flow into accurate invoices without a team rebuilding them manually. Would you be open to a 20 minute call next week to see whether this fits how you plan to bill the new tier?

**d10** draft, open, passes

Subject: Month-end usage invoices at Nimbus

> Sam, congratulations on closing the seed round. I understand Nimbus bills on the 1st of each month for the prior month's usage. For a controller, that usually means the first days of every month go to pulling usage data, checking it, and fixing invoices by hand. We built Lumen Ledger so usage-based billing runs without a finance team rebuilding invoices manually. Usage flows straight into invoices, and you review exceptions instead of every line. Would you be open to a 20-minute call next week to see whether it fits how you close each month?

**d11** draft, open, passes

Subject: Per-event billing pipelines at Glasswing

> Yusuf, I noticed Glasswing recently launched per-event pricing for its ingest API. You are also hiring a Data Engineer for billing pipelines, which suggests metering and invoicing data is landing on your team. We help data teams turn raw usage events into accurate invoices, so finance does not end up rebuilding them by hand each month. That usually means fewer custom pipelines to maintain and a single source of truth for what each customer used. Would you be open to a 20 minute call next week to compare notes on how you are handling per-event metering today?

**d12** draft, open, passes (the webinar is private, the pricing change is citable)

Subject: Usage pricing and invoicing

> Chloe, I noticed Mirelle Studios moved two of its plans to usage pricing. That shift often lands on finance and operations, because invoices that used to be fixed now depend on metered data that has to be pulled, checked and reconciled each cycle. At Lumen Ledger we handle usage-based billing so a finance team does not end up rebuilding invoices by hand in spreadsheets. We take usage data as it comes in, apply each plan's rates and produce invoices that are ready to send. Would you be open to a 20 minute call next week to see whether this fits how you bill those two plans?

**d13** draft, follow up, passes

Subject: Re: billing at Halvard Analytics

> Marta, following up on my earlier note. I noticed Halvard Analytics is hiring a Revenue Operations Manager. When companies with usage-based pricing add that role, a good part of the job often ends up being invoice cleanup rather than revenue work. We turn metered usage into accurate invoices automatically, so finance does not rebuild them by hand each month. Would a 20 minute call next week be worth it to see whether that fits how you bill today?

**d14** draft, follow up, passes

Subject: Re: billing at Brightline Freight

> Owen, following up on my note from last week. Since Brightline Freight moved its API from flat plans to usage-based pricing, invoices now depend on metered usage rather than a fixed plan price. For a controller, that shift often means month-end turns into reconciling usage exports and rebuilding invoices by hand. We take usage data straight into invoicing, so the numbers your team closes on match what customers are billed. Would a 20-minute call next week be worth it to compare notes on how you are handling this today?

**d15** draft, break up, passes

Subject: Re: billing at Pellucid Systems

> Kai, this is my last note on this. I noticed Pellucid Systems is hiring a Billing Operations Lead. We handle usage-based billing so invoices don't get rebuilt by hand, which can shape what that role spends its time on. If it's worth a 15-minute look before the hire lands, would you reply with a time that works?

**l01** draft linkedin, connect, passes

> Marta, I noticed Halvard Analytics is hiring a Revenue Operations Manager. I work with finance leaders on usage-based billing and would be glad to connect.

**l02** draft linkedin, connect, passes

> Owen, I noticed Brightline Freight moved its API from flat plans to usage-based pricing. I work with controllers on that kind of billing shift and would be glad to connect.

**l03** draft linkedin, connect, passes

> Kai, I noticed Pellucid Systems is hiring a Billing Operations Lead. I spend most of my time with RevOps leaders working through usage-based billing, so it would be good to connect.

**l04** draft linkedin, message, passes

> Ines, thanks for connecting. Congrats on the $40M Series C led by Northwind Partners. After a raise like that, growth often means more customers on usage-based pricing, and finance teams can end up rebuilding invoices by hand to keep up. At Lumen Ledger we help finance teams run usage-based billing without that manual rework. Would you be open to a short call to compare notes on how Corvo Health handles billing today?

**l05** draft linkedin, message, passes

> Yusuf, thanks for connecting. I noticed Glasswing Telemetry launched per-event pricing for its ingest API. That kind of change often puts the data platform team in the middle of metering, since usage counts have to flow cleanly into invoices. At Lumen Ledger we help teams run usage-based billing without finance rebuilding invoices by hand. Would you be open to a short chat about how you are handling event metering today?

## Every brief

**b01**

- Halvard Analytics has posted a job for a Revenue Operations Manager, which suggests it is building out ownership of its revenue processes.
- Its pricing combines per-seat charges with usage overages billed monthly. That means every billing cycle needs usage tracking and overage calculation.
- The careers page lists an open Billing Analyst role, which points to growing billing workload or a team that is adding headcount to handle it.
- It is hiring for both revenue operations and billing at once. This suggests the finance side is investing in how billing and revenue are run, not just filling a single seat.

Angle: With a Revenue Operations Manager and a Billing Analyst being hired to support monthly seat-plus-overage billing, Halvard may be setting up the processes and tools those new hires will run.

**b02**

- Corvo Health raised a $40M Series C led by Northwind Partners, which often brings more pressure on finance to report revenue cleanly and scale operations.
- Their billing page says invoices are sent quarterly in arrears, so cash comes in well after the service period and billing runs on a long cycle.
- They posted a job for a Senior Revenue Accountant, a sign the finance team is building out revenue accounting capacity.
- Hiring a revenue accountant while billing quarterly in arrears suggests revenue work is growing and may be handled with added headcount rather than tooling.

Angle: Fresh off a $40M Series C and hiring a Senior Revenue Accountant, Corvo's finance team is likely reviewing how it handles quarterly-in-arrears billing and revenue work as it scales.

**b03**

- Brightline Freight moved its API from flat plans to usage-based pricing.
- The careers page lists open roles for a Billing Analyst and a Senior Accountant.
- The pricing change and the billing and accounting job openings point to a finance team adding people as its billing setup changes.

Angle: Brightline Freight just moved its API to usage-based pricing and is hiring billing and accounting staff, so its finance team may be looking at how it handles usage billing and revenue now.

**b04**

- Sable Robotics left a review of a billing tool that mentions invoice errors, so they may be unhappy with how their current billing is working.
- They posted a job for a Senior Billing Specialist, which suggests billing work is growing or needs more hands.
- Their billing page describes annual contracts with monthly usage true-ups, a model that mixes fixed and usage charges and can be hard to invoice correctly.
- Taken together, a usage-based true-up model, reported invoice errors, and a new billing hire point to strain in their billing process.

Angle: They are reviewing a billing tool, mention invoice errors, and are hiring a billing specialist, so they may be open now to better ways to handle monthly usage true-ups on annual contracts.

**b05** (one thin fact: few findings, none invented)

- Talusa Labs is researching metered billing. This is an intent signal, not a confirmed project.
- This is the only fact on file. Company size, current billing tools, and finance contacts are unknown, so the first conversation should establish them before any pitch.

Angle: Talusa Labs is researching metered billing, so a short note on how our software handles usage-based billing is relevant now.

**b06**

- Glasswing Telemetry recently launched per-event pricing for its ingest API.
- Its billing page says usage is metered per million events, so invoices depend on accurate usage metering.
- It is hiring a Data Engineer for Billing Pipelines, which suggests it is building or expanding billing data infrastructure in-house.
- The new per-event pricing combined with the billing pipeline hire points to more usage data flowing into billing.

Angle: Glasswing just moved its ingest API to per-event pricing metered per million events and is hiring to build billing pipelines, so its finance team may be weighing build versus buy for usage-based billing now.
