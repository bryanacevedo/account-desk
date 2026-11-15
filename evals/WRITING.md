# Drafting and brief eval

50 draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and 20 brief cases, invented companies. Answers from recorded Claude answers. Graded by code; read the drafts below for what code cannot judge.

## Drafts

| Check | Result |
|---|---|
| Passes the copy checks first time | 44 of 50 |
| Passes after the one redraft the desk allows | 49 of 50 |
| Cites a private signal | 0  |
| Cites a fact that does not exist | 0  |
| Mentions something the case forbids | 0  |
| Judge: specific | 44 of 49 (90%, 90% interval 80 to 95%) |
| Judge: faithful | 44 of 49 (90%, 90% interval 80 to 95%) |
| Judge: ignores instructions | 49 of 49 (100%, 90% interval 95 to 100%) |
| Judge: one ask | 46 of 49 (94%, 90% interval 86 to 98%) |
| Judge: relevant | 48 of 49 (98%, 90% interval 91 to 100%) |
| Judge: tone | 48 of 49 (98%, 90% interval 91 to 100%) |

Why first attempts failed: unsupported_about_them 3, not_about_them 1, stock_line 1, uncited_claim 1.

Checks still failing after the redraft: uncited_claim 1, not_about_them 1, banned_phrase 1.

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

Subject: Revenue operations at Halvard

> Hi Marta, I saw that Halvard Analytics posted a job for a Revenue Operations Manager. I'm Maya at Lumen Ledger, and we turn usage data into accurate invoices automatically. Would a short conversation about how you bill be worth it? If not, just reply no and I won't write again.

**d02** draft, open, passes

Subject: Usage-based billing at Brightline

> Hi Owen, I saw that Brightline Freight moved from flat plans to usage-based pricing for its API. I'm Maya at Lumen Ledger, and we turn metered usage into accurate invoices automatically. Would it be worth a conversation? If not, just reply no and I won't write again.

**d03** draft, open, passes (numbers: only $40M and Series C are citable)

Subject: Invoicing at Corvo Health

> Hi Ines, I saw that Corvo Health raised a $40M Series C led by Northwind Partners. I'm Maya at Lumen Ledger. We turn product usage data into invoices automatically, so nobody builds them by hand. Would a conversation about it be worth having? If not, just reply no and I won't write again.

**d04** draft, open, passes (must not mention the pricing-page visits)

Subject: Billing Operations Lead role

> Hi Kai, I saw that Pellucid Systems posted a job for a Billing Operations Lead. I'm Maya at Lumen Ledger, and we turn usage data into accurate invoices automatically. Is this worth a conversation? If not, just reply no and I won't write again.

**d05** draft, open, fails: uncited_claim, not_about_them, banned_phrase (only private facts: there is nothing citable, so it should fail rather than cite)

Subject: Usage billing at Talusa Labs

> Hi Rui, I'm reaching out cold and don't know how Talusa Labs handles billing today, so I'd rather ask than guess. I'm Maya at Lumen Ledger. We turn product usage data into accurate invoices automatically. Is it worth a conversation? If not, just reply no and I won't write again.

- judge, specific: No facts were given, and the email only names the company: "Usage billing at Talusa Labs" and "don't know how Talusa Labs handles billing today" would fit any company.
- judge, relevant: It is aimed at billing, but Rui is a Director of Data, not a finance or revenue leader, and the pitch "turn product usage data into accurate invoices" is generic with no tie to his role or company.

**d06** draft, open, passes (opens with the first name, not the title)

Subject: Billing at Quillon Payments

> Hi Amara, I saw that Quillon Payments removed a legacy billing tool from its stack. I'm Maya at Lumen Ledger. We turn product usage data into accurate invoices automatically. Would a conversation be worth it? If not, a quick no is fine and I won't write again.

**d07** draft, open, passes

Subject: Usage billing question

> Hi Lena, I saw that you joined Orbis Mobility as CFO. I'm Maya at Lumen Ledger. We help finance teams bill for usage by turning product data into invoices automatically. Would it be worth a conversation? If not, just reply no and I won't write again.

**d08** draft, open, passes

Subject: Your billing tool review

> Hi Tom, I saw you left a review of a billing tool that mentions invoice errors. I'm Maya at Lumen Ledger. We turn product usage data into invoices automatically. Would it be worth a conversation? If not, just reply no and I won't write again.

**d09** draft, open, passes (referral: should open with who suggested it)

Subject: Daniel Moore suggested I write

> Hi Priya, Daniel Moore suggested I write to you. I'm Maya at Lumen Ledger. We turn product usage data into accurate invoices automatically. Would it be worth a conversation? If not, just reply no and I won't write again.

**d10** draft, open, passes

Subject: Usage-based invoicing question

> Hi Sam, I saw that Nimbus Ledger Co raised a seed round. I'm Maya at Lumen Ledger, and we turn product usage data into finished invoices automatically. Would a conversation about it be worth your time? If not, just reply no and I won't write again.

**d11** draft, open, passes

Subject: Billing pipelines at Glasswing

> Hi Yusuf, I saw that Glasswing Telemetry posted a job for a Data Engineer focused on billing pipelines. I'm Maya at Lumen Ledger, and we turn product usage data into accurate invoices automatically. Is it worth a conversation? If not, just reply no and I won't write again.

**d12** draft, open, passes (the webinar is private, the pricing change is citable)

Subject: Usage pricing at Mirelle Studios

> Hi Chloe, I saw that Mirelle Studios moved two of its plans to usage pricing. I'm Maya from Lumen Ledger. We turn product usage data into invoices automatically. Would a conversation about it be worth having? If not, just reply no and I won't write again.

**d13** draft, follow up, passes

Subject: Re: billing at Halvard Analytics

> Marta, My last note mentioned the Revenue Operations Manager role Halvard Analytics posted. At Lumen Ledger we turn product usage into ready-to-send invoices automatically. Would a short overview by email be useful? If not, just say so and I will not write again.

- judge, faithful: The subject 'Re: billing at Halvard Analytics' implies billing is a topic for them, and 'My last note mentioned' invents a prior email; neither is in the facts.

**d14** draft, follow up, passes

Subject: billing at Brightline Freight

> Owen, I wrote recently about Brightline Freight moving its API from flat plans to usage-based pricing. At Lumen Ledger we turn usage records into finished invoices automatically. Would it be worth a look, yes or no?

**d15** draft, break up, passes

Subject: last note on billing

> Kai, I wrote earlier about the Billing Operations Lead role you posted, and this is my last note. Lumen Ledger turns usage data into invoices automatically. Is it worth a conversation, yes or no? If the answer is no, I will not write again.

- judge, one_ask: As a last email it should close politely without pressure, but "Is it worth a conversation, yes or no? If the answer is no, I will not write again." still presses for a reply with a yes/no demand.

**l01** draft linkedin, connect, passes

> Hi Marta, I noticed Halvard Analytics is hiring a Revenue Operations Manager. I work on usage-based billing at Lumen Ledger and would be glad to connect.

**l02** draft linkedin, connect, passes

> Hi Owen, I saw Brightline Freight moved its API from flat plans to usage-based pricing. I talk with controllers about usage billing often and would be glad to connect.

**l03** draft linkedin, connect, passes

> Hi Kai, I noticed Pellucid Systems is hiring a Billing Operations Lead. I work on usage-based billing at Lumen Ledger and would be glad to connect with someone in RevOps.

**l04** draft linkedin, message, passes

> Ines, thanks for connecting. Congratulations on the $40M Series C led by Northwind Partners. I work with finance leaders at Lumen Ledger on usage-based billing, so their teams are not rebuilding invoices by hand each cycle. Would you be open to a short call to compare notes on how Corvo Health handles billing today?

- judge, faithful: It implies Corvo Health has a billing process worth comparing ('how Corvo Health handles billing today') and that teams rebuild invoices by hand, and 'thanks for connecting' assumes a connection not in the facts.
- judge, tone: 'Congratulations on the $40M Series C' is mild flattery and the sentence 'so their teams are not rebuilding invoices by hand each cycle' is awkward and presumptive, so it is not plain.

**l05** draft linkedin, message, passes

> Yusuf, thanks for connecting. I noticed Glasswing Telemetry launched per-event pricing for its ingest API. At Lumen Ledger we help teams run usage-based billing without finance rebuilding invoices by hand. I am not sure who owns billing on your side, so would you be open to pointing me to the right person, or sharing a quick view if it is you?

- judge, one_ask: It makes two asks joined by "or": "pointing me to the right person" and "sharing a quick view if it is you"; the second is a different action, so it is not one clear ask.

**d2_01** draft, open, passes

Subject: Ombria's Series B

> Hi Harriet, I saw that Ombria Telematics raised a $22M Series B led by Calder Peak Ventures in October. I'm Maya at Lumen Ledger. We turn product usage data into accurate invoices automatically, so nobody builds them by hand. Would a conversation about how we do that be worth having? If not, just reply no and I won't write again.

**d2_02** draft, open, passes (Only the hiring fact is citable.)

Subject: Senior Billing Accountant role

> Hi Bastian, I saw that Velloria Freight posted a job for a Senior Billing Accountant. I'm Maya at Lumen Ledger, and we turn usage data into accurate invoices automatically. Would it be worth a conversation to see whether that fits what you need? If not, just reply no and I won't write again.

**d2_03** draft, open, passes

Subject: Invoicing at Thornquist Labs

> Hi Leilani, I saw Thornquist Labs has posted openings for four Account Executives. I'm Maya with Lumen Ledger. We turn product usage data into accurate invoices, so billing runs without manual work. Is it worth a conversation to see if that fits? If not, just reply no and I won't write again.

**d2_04** draft, open, passes (numbers: cite exactly as written, no rounding)

Subject: Usage billing at Brightwater

> Hi Marcus, I read that Brightwater Metering grew ARR from $14.2M to $31.7M in 18 months. I'm Maya at Lumen Ledger, and we turn metered usage data into accurate invoices automatically. Would a conversation be worth it? If not, just reply no and I will not write again.

**d2_05** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: monthly invoicing at Pellwick

> Grace, I wrote to you recently about Pellwick Software moving to monthly usage-based billing in September 2026. At Lumen Ledger we turn usage data into monthly invoices automatically. Would a short look at how that works be useful, yes or no? If not, just reply no and I will not write again.

**d2_06** draft, open, passes

Subject: A question about billing

> Hi Callum, I saw that Kestrava Logistics posted a job for a Revenue Operations Analyst. I'm Maya at Lumen Ledger, and we turn product usage data into accurate invoices automatically. Would a conversation be worth it? If not, just reply no and I won't write again.

**d2_07** draft, open, passes (referral: open with who suggested it)

Subject: Invoicing for your API product

> Hi Agnieszka, Tomasz Wierzbicki suggested I write to you about invoicing for your new API product. I'm Maya at Lumen Ledger, and we turn usage data into accurate invoices automatically. Is this worth a conversation? If not, just say so and I won't write again.

**d2_08** draft, follow up, passes (Follow-up after no reply to the open.)

Subject: Per-transaction billing in DKK and EUR

> Søren, I wrote recently about billing at Fjordlys Betalinger, where merchants are billed per transaction and settled monthly in DKK and EUR. Lumen Ledger turns per-transaction usage into finished invoices automatically. Is this worth a look, yes or no? If not, just say so and I will not write again.

**d2_09** draft, open, passes (Title does not match the persona; treat as a likely wrong buyer.)

Subject: Pay-as-you-go storage billing

> Hi Priyanka, I saw that Lattimer Cloud launched a pay-as-you-go plan for its storage product. I'm Maya at Lumen Ledger, and we turn product usage into accurate invoices automatically. Would a conversation about this be worth it for your team? If not, just reply no and I won't write again.

- judge, one_ask: It asks "Would a conversation about this be worth it for your team?" and also tells her to "just reply no", which gives two asks or a muddled one rather than exactly one clear, small ask.

**d2_10** draft, follow up, passes (Follow-up after no reply to the open. Nothing new is known since the first email.)

Subject: Revenue Operations hire at Corridor

> Nadia, I wrote recently after seeing that Corridor Health Systems posted a job for a Revenue Operations Manager. At Lumen Ledger, we turn usage data into finished invoices automatically. Is this worth a look, yes or no? If not, just say so and I will not write again.

**d2_11** draft, follow up, passes (Follow-up; the new CFO appointment is new since the open.)

Subject: Re: billing at Granitebay Payroll

> Ifeoma, I wrote earlier after seeing that Granitebay Payroll posted a job for a Billing Specialist. At Lumen Ledger, we turn usage data into finished invoices automatically. Is this worth a look, yes or no?

**d2_12** draft, bump, passes (Bump: two prior emails, no reply. Keep it very short.)

Subject: One question on billing

> Tobias, Bringing my earlier note back to the top of your inbox with a shorter version. We turn usage data into finished invoices automatically. Does billing sit with you at Skerry Analytics? If not, a quick no is fine and I will stop writing.

- judge, specific: It only names the company ('Does billing sit with you at Skerry Analytics?') and does not use the CPQ fact, so it would fit any company.

**d2_13** draft, bump, passes (only private facts: nothing citable)

Subject: Re: billing at Marlowe Data Exchange

> Eleanor, I'm bringing my earlier note back to the top of your inbox. At Lumen Ledger we turn product usage data into finished invoices automatically. Is it worth a look, yes or no?

- judge, specific: Facts are empty and the body is generic: "we turn product usage data into finished invoices automatically" would fit any company; only the company name appears in the subject.

**d2_14** draft, break up, passes (Break-up: fourth and final email, no replies so far.)

Subject: last note on billing

> Gideon, I wrote a little while ago about billing, so this will be my last note. Since Halyard moved commercial customers to metered energy-data pricing, we can turn that usage into invoices automatically. Is this worth a look, yes or no? If not, no reply is needed and I won't write again.

**d2_15** draft, break up, passes (Break-up email.)

Subject: Closing the loop on billing

> Hi Anouk, Since my last note about the Billing Operations Specialist role you posted in Utrecht, I haven't heard back, so this will be my last email. We automate usage-based invoicing so it doesn't have to be rebuilt by hand. Should I leave this here, yes or no? Either way, I won't write again unless you reach out.

- judge, faithful: It claims "Since my last note about the Billing Operations Specialist role" and "usage-based invoicing so it doesn't have to be rebuilt by hand", implying their invoicing is usage-based and manually rebuilt, which the facts do not state.

**d2_16** draft, open, passes

Subject: Billing widget on checkout

> Hi Rafael, I saw that Quayline Commerce removed a subscription billing widget from its checkout pages. I'm Maya at Lumen Ledger, and we build software that turns usage data into invoices automatically. Is it worth a conversation? If not, just reply no and I won't write again.

**d2_17** draft linkedin, connect, passes (Limit: 200 characters)

> Dominic, I saw Northfall Robotics raised a $60M Series C and posted a Head of Billing role. I work on usage-based billing at Lumen Ledger and would be glad to connect.

**d2_18** draft linkedin, connect, passes (Limit: 300 characters)

> Maëlle, I saw Ateliers Brisemer is hiring a Comptable fournisseurs et clients in Nantes. I work with controllers on billing and invoicing, so I would be glad to connect.

**d2_19** draft linkedin, connect, passes (Limit: 150 characters)

> João, I saw Serra Azul Pagamentos launched a per-transaction plan for small merchants. I work on usage-based billing at Lumen Ledger and would be glad to connect.

**d2_20** draft linkedin, message, passes (First LinkedIn message after she accepted the connection request.)

> Hana, Saw that Added a cloud data warehouse to its stack. We do usage-based billing for finance teams. Worth a few minutes to compare notes?

**d2_21** draft linkedin, message, passes (Write in English.)

> Ximena, thanks for connecting. I saw that Grupo Altiplano is expanding its freight-by-weight pricing to three new routes in northern Mexico. At Lumen Ledger we help finance teams run usage-based billing so invoices don't have to be rebuilt by hand as pricing models grow. Would you be open to a short call to compare notes on how you handle weight-based invoicing today?

- judge, faithful: It implies a billing pain about them: "so invoices don't have to be rebuilt by hand as pricing models grow" and "how you handle weight-based invoicing today" assume they invoice by weight and rebuild by hand, which the facts don't say.

**d2_22** draft, bump, passes (Bump: one prior email, no reply.)

Subject: usage data to invoices

> Okonkwo, Writing once more about my earlier note. At Lumen Ledger we turn product usage data into invoices, even when pricing changes. Is this worth a look, yes or no?

- judge, specific: The body only says "we turn product usage data into invoices, even when pricing changes" and never mentions Pyxis, the streaming pipeline or the billing pipelines job, so it would fit any company.

**d2_23** draft, follow up, passes (Follow-up after no reply.)

Subject: Re: billing at Clearmont Insurance Tech

> Winston, I wrote to you earlier because Clearmont Insurance Tech started charging carriers per policy quoted through its API. At Lumen Ledger we turn usage data like that into invoices automatically. Is it worth a look, yes or no?

**d2_24** draft, open, passes (numbers: $0.004 and the two dates are the only citable figures)

Subject: Billing the new per-call pricing

> Hi Leopold, I saw that Tessellate Maps announced on 3 November that its geocoding API will cost $0.004 per call from 1 January 2027. I'm Maya from Lumen Ledger, and we turn metered API usage into accurate invoices automatically. Would a conversation about invoicing the new per-call pricing be worth it? If not, just say so and I won't write again.

**d2_25** draft, open, passes

Subject: Invoicing question for Ondaverde

> Hi Beatriz, I saw that Ondaverde Telecom appointed Dagny Oyelowo as Chief Financial Officer in October 2026. I'm Maya from Lumen Ledger, and we turn usage data into accurate invoices automatically. Would a conversation about that be worth it for you? If not, just reply no and I won't write again.

**d2_26** draft, bump, passes (Bump.)

Subject: Usage-based billing question

> Hi Emeka, I wrote to you a little while ago about billing. At Lumen Ledger we run usage-based billing and produce the invoices, so no one rebuilds them by hand. Would a short note on how it works be useful, yes or no? If not, just say so and I will stop writing.

- judge, specific: The body never mentions Fernbrook Labs or Corvex Billing and only says "I wrote to you a little while ago about billing", which would fit any company.
- judge, faithful: It implies a manual process at their company with "so no one rebuilds them by hand" and says "usage-based billing", neither of which is in the facts.

**d2_27** draft linkedin, connect, passes (Limit: 200 characters)

> Siobhán, Felix Dunne suggested I reach out to you. I work with finance leaders on usage-based billing and would be glad to connect.

**d2_28** draft linkedin, message, passes

> Ravindra, thanks for connecting. I saw that Monsoonware builds metering software for utilities and recently posted a role for an Accounts Receivable Lead. At Lumen Ledger we help finance teams run usage-based billing without rebuilding invoices by hand. Would it be useful if I sent a short overview of how other controllers have set that up?

**d2_29** draft, break up, passes (Break-up email.)

Subject: Last note on billing

> Hi Ingrid, I wrote earlier about the Billing Analyst role you posted, and this is my last note. At Lumen Ledger we turn product usage data into finished invoices automatically. Is it a no for now? Either way, I won't write again.

**d2_30** draft, break up, passes (Break-up email.)

Subject: closing the loop

> Theo, I wrote earlier after seeing the per-ticket service fees Glasshouse added for venue partners. At Lumen Ledger we turn usage data into accurate invoices automatically. Is this worth a look at all, yes or no? If it isn't, just say so and I won't write again.

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
