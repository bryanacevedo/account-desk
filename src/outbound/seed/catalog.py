"""The fixed configuration a new install starts with: the seller, personas, signal types, plays, rules.

The seller in the demo is Lumen Ledger (invented): usage-based billing and revenue recognition software for
B2B software companies. Buyers are finance and revenue operations leaders.
"""
from __future__ import annotations

SETTINGS = {
    "kill_switch": False,
    "account_max_active": 3,
    "account_max_active_wide": 5,
    "person_cooldown_days": 90,
    "account_reply_pause_hours": 72,
    "verify_max_age_days": 45,
    "proposal_ttl_days": 5,
    "urgent_proposal_ttl_days": 1,
    "stagger_days": 2,
    "send_window": [["08:30", "11:30"], ["13:30", "16:00"]],
    "mailbox_max_daily": 30,
    "sla_business_hours": 4,
    "approval_lapse_business_days": 5,
    # Inbox placement from seed tests, our defaults (tune per team): under 80% at any provider holds the mailbox at
    # 10 a day, under 50% pauses it; a test older than 10 days counts as unknown.
    "placement_hold_below": 0.8,
    "placement_pause_below": 0.5,
    "placement_max_age_days": 10,
    # LinkedIn caps connection notes, lower on free accounts; set this to what the SDRs' accounts allow.
    "linkedin_note_max_chars": 200,
    # Billing tools we replace. One arriving is not a reason to call; one leaving is ("Dropped a tool we replace").
    "competing_tools": ["Chargewise", "Meterline", "Chargebee", "Zuora"],
    # Calling hours in the person's own time, Monday to Friday.
    "call_window": ["09:00", "18:00"],
    # A prospect with no reply and no activity for this many months is deleted; their opt-outs stay, hashed.
    "retention_months": 12,
}

USERS = [
    # name, email, role, timezone
    ("Maya Okafor", "maya.okafor@lumenledger.example", "sdr", "America/New_York"),
    ("Daniel Reyes", "daniel.reyes@lumenledger.example", "sdr", "America/Chicago"),
    ("Priya Natarajan", "priya.natarajan@lumenledger.example", "sdr", "Europe/London"),
    ("Tom Whitaker", "tom.whitaker@lumenledger.example", "sdr", "America/Los_Angeles"),
    ("Elena Duarte", "elena.duarte@lumenledger.example", "manager", "America/New_York"),
    ("Sam Kowalski", "sam.kowalski@lumenledger.example", "gtm", "America/New_York"),
    # Added when the demo grew to about 3,000 accounts: after the first six, so every earlier id stays the same.
    ("Jonas Weber", "jonas.weber@lumenledger.example", "sdr", "Europe/Berlin"),
    ("Grace Osei", "grace.osei@lumenledger.example", "sdr", "America/Denver"),
]

PERSONAS = [
    # key, label, title patterns, seniority, committee role, angle
    ("cfo", "Finance leader", ["cfo", "chief financial", "vp finance", "vice president of finance", "head of finance"],
     ["c_suite", "vp"], "economic_buyer",
     "Close the books faster and stop revenue leaking between the billing system and the ledger."),
    ("controller", "Controller", ["controller", "head of accounting", "director of accounting", "chief accounting"],
     ["director", "vp"], "champion",
     "Revenue recognition that does not need a spreadsheet at month end."),
    ("revops", "Revenue operations", ["revenue operations", "revops", "sales operations", "billing operations",
                                      "head of billing"], ["director", "manager", "vp"], "user",
     "Quote to cash without hand-offs: what was sold is what gets billed."),
    ("data", "Data and systems", ["head of data", "data engineering", "finance systems", "business systems",
                                  "erp"], ["director", "manager"], "technical",
     "One source for usage data, so finance and product stop arguing about the number."),
]

SIGNAL_TYPES = [
    # key, label, because, level, weight, half-life days
    ("champion_moved", "A past champion joined", "A person who bought or used us before joined this company and already trusts us.",
     "person", 30, 60),
    ("new_exec", "New finance leader", "A new finance leader reviews the tools they inherit in their first 90 days.",
     "account", 22, 45),
    ("hiring_function", "Hiring in finance operations", "Hiring billing or revenue accountants means the manual work is growing.",
     "account", 14, 30),
    ("funding", "Raised a round", "New money comes with a board that wants clean revenue reporting.", "account", 12, 60),
    ("pricing_visit", "Looked at our pricing", "Someone at the company read our pricing page.", "account", 18, 7),
    ("site_visit", "Visited product pages", "Repeat visits to product pages from the company's network.", "account", 8, 10),
    ("intent_topic", "Researching the category", "Reading about usage-based billing across the web.", "account", 10, 14),
    ("competitor_review", "Reviewing a competitor", "Reviewing or complaining about a billing tool we replace.", "account", 16, 21),
    ("tech_added", "Adopted a tool we connect to", "A new data warehouse or ERP means the billing stack is being rebuilt.",
     "account", 9, 60),
    ("tech_removed", "Dropped a tool we replace", "They removed a billing tool, so they need a replacement.", "account", 15, 45),
    ("pricing_change", "Changed their pricing model", "Moving to usage-based pricing breaks seat-based billing systems.",
     "account", 20, 45),
    ("social_engaged", "Engaged with the topic", "A person engaged with posts about usage-based billing.", "person", 7, 14),
    ("job_change", "Someone we know moved", "A person we have been in touch with joined this company.", "person", 12, 60),
    ("closed_lost_revisit", "Closed-lost, time to revisit", "We lost a deal here over timing, and the timing has passed.",
     "account", 14, 60),
    ("product_signup", "Signed up for the free tier", "Trying the product means they already have the problem.", "account", 20, 14),
    ("event_attended", "Came to our event", "Someone from the company attended our webinar or dinner.", "person", 10, 21),
    ("news_negative", "Layoffs or a hiring freeze", "Cost cutting pauses new tools, so priority drops.", "account", -15, 45),
]

SIGNAL_SOURCES = [
    # key, label, adapter, cadence minutes, paid, what it needs. Only first-party data is free.
    ("jobs_feed", "Job postings", "sim", 360, True, "A job-postings data vendor"),
    ("funding_feed", "Funding news", "sim", 720, True, "A funding database (for example Crunchbase or Harmonic)"),
    ("people_moves", "Job changes", "sim", 720, True, "A job-change tracking vendor"),
    ("web_visits", "Website visits", "sim", 60, True,
     "A de-anonymization vendor that matches visitors' networks to companies"),
    ("intent_feed", "Category research", "sim", 1440, True, "A third-party intent data vendor"),
    ("reviews_feed", "Software reviews", "sim", 1440, True, "Buyer intent from a software review site"),
    ("techstack_feed", "Technology changes", "sim", 1440, True, "A technology-detection vendor"),
    ("social_feed", "Social engagement", "sim", 360, True, "A social listening vendor"),
    ("product", "Product sign-ups", "sim", 60, False, "Your own product's sign-ups"),
    ("crm", "CRM", "sim", 360, False, "Your own CRM"),
    ("events", "Events", "sim", 1440, False, "Your own event and webinar registrations"),
    ("news_feed", "Company news", "sim", 720, True, "A company news or events API"),
    ("webhook", "Webhook intake", "webhook", 1440, False, "Anything you push to the desk yourself"),
    ("replies", "Replies", "webhook", 1440, False, "What people tell us in replies, such as a new job"),
]

ICP = {
    "factors": [
        {"key": "industry", "field": "industry", "op": "in",
         "value": ["Software", "Fintech", "Data infrastructure", "Developer tools", "Marketplaces"], "weight": 30},
        {"key": "size", "field": "employees", "op": "between", "value": [120, 2000], "weight": 25},
        {"key": "region", "field": "region", "op": "in", "value": ["North America", "Europe"], "weight": 15},
        {"key": "revenue", "field": "revenue_band", "op": "in", "value": ["$20M-$100M", "$100M-$500M"], "weight": 15},
        {"key": "stack", "field": "tech", "op": "has_any", "value": ["Snowflake", "NetSuite", "Salesforce", "Stripe"],
         "weight": 15},
    ],
    "penalties": [
        {"key": "legacy_erp", "field": "tech", "op": "has_any", "value": ["Legacy on-prem ERP"], "weight": 20},
    ],
    "excludes": [
        {"field": "industry", "op": "in", "value": ["Government", "Education"], "reason": "Sector we do not sell to"},
        {"field": "employees", "op": "between", "value": [0, 19], "reason": "Too small to need us"},
    ],
    "tiers": {"A": 85, "B": 65},
}

def _seq(*steps):
    return [dict(zip(("day", "channel", "job", "by"), s)) for s in steps]

STANDARD = _seq((0, "email", "open", "desk"), (2, "linkedin_connect", "connect", "sdr"), (4, "email", "follow_up", "desk"),
                (7, "call", "call", "sdr"), (10, "email", "break_up", "desk"))
SHORT = _seq((0, "email", "open", "desk"), (3, "email", "follow_up", "desk"), (6, "call", "call", "sdr"),
             (9, "email", "break_up", "desk"))
# A past champion usually knows the SDR already: connect, then a short LinkedIn message before the follow-up.
CHAMPION = _seq((0, "email", "open", "desk"), (1, "linkedin_connect", "connect", "sdr"),
                (3, "linkedin_message", "message", "sdr"), (5, "email", "follow_up", "desk"), (8, "call", "call", "sdr"),
                (10, "email", "break_up", "desk"))

PLAYS = [
    # key, name, hypothesis, trigger, personas, max people, sequence, angle, autonomy, urgent, latency hours
    ("champion_moved", "A past champion joined",
     "People who bought us before buy again at their next company, faster than anyone else.",
     {"any_of": ["champion_moved"], "fit_tiers": ["A", "B"], "min_priority": 0, "within_days": 30},
     ["controller", "cfo"], 2, CHAMPION,
     "Open with the person's history with us, then why it applies to the new company.", "draft", True, 24),
    ("new_finance_leader", "New finance leader, first 90 days",
     "A new CFO or VP Finance reviews the stack they inherited and has budget to change it.",
     {"any_of": ["new_exec"], "fit_tiers": ["A", "B"], "min_priority": 35, "within_days": 45},
     ["cfo", "controller", "revops"], 3, STANDARD,
     "Congratulate briefly, then the one finance problem new leaders find in their first quarter.", "draft", True, 24),
    ("pricing_model_change", "Moving to usage-based pricing",
     "Companies changing to usage-based pricing outgrow seat-based billing within two quarters.",
     {"any_of": ["pricing_change"], "fit_tiers": ["A", "B"], "min_priority": 30, "within_days": 30},
     ["revops", "controller", "data"], 3, STANDARD,
     "Name the pricing change and the billing work it creates.", "draft", False, 48),
    ("finance_ops_hiring", "Hiring in finance operations",
     "Hiring billing and revenue accountants is the cost of manual billing showing up in the budget.",
     {"any_of": ["hiring_function"], "fit_tiers": ["A", "B"], "min_priority": 40, "within_days": 30},
     ["controller", "cfo", "revops"], 3, STANDARD,
     "The roles they are hiring for, and the work those people would spend their first year on.", "draft", False, 48),
    ("in_market", "Researching billing tools",
     "A pricing visit, a competitor review or a dropped billing tool, at an account already scoring high, means an evaluation may be under way.",
     {"any_of": ["pricing_visit", "competitor_review", "tech_removed"], "fit_tiers": ["A", "B"], "min_priority": 45,
      "within_days": 14},
     ["revops", "controller", "cfo"], 3, SHORT,
     "Be useful to an evaluation: what to test, without naming that we saw them.", "draft", True, 24),
    ("funded", "Raised a round",
     "A new round brings a board that wants clean revenue numbers.",
     {"any_of": ["funding"], "fit_tiers": ["A"], "min_priority": 50, "within_days": 30},
     ["cfo", "controller"], 2, STANDARD,
     "What boards ask finance for after a round, and how long it takes without us.", "research", False, 72),
]

HOLIDAYS = [
    ("US", "2026-09-07", "Labor Day"),
    ("US", "2026-11-26", "Thanksgiving"), ("US", "2026-11-27", "Day after Thanksgiving"),
    ("US", "2026-12-25", "Christmas Day"), ("US", "2027-01-01", "New Year's Day"),
    ("US", "2027-01-18", "Martin Luther King Jr. Day"), ("US", "2026-10-12", "Columbus Day"),
    ("GB", "2026-08-31", "Summer bank holiday (England, Wales and Northern Ireland)"),
    ("GB", "2026-12-25", "Christmas Day"), ("GB", "2026-12-28", "Boxing Day (substitute)"),
    ("GB", "2027-01-01", "New Year's Day"), ("DE", "2026-10-03", "German Unity Day"),
    ("DE", "2026-12-25", "Christmas Day"), ("DE", "2026-12-26", "St Stephen's Day"),
    ("DE", "2027-01-01", "New Year's Day"), ("FR", "2026-11-11", "Armistice Day"),
    ("FR", "2026-12-25", "Christmas Day"), ("FR", "2027-01-01", "New Year's Day"),
    ("NL", "2026-12-25", "Christmas Day"), ("NL", "2026-12-26", "Second Christmas Day"),
    # Remembrance Day (11 November) is not a statutory holiday in Ontario or Quebec, where most of the demo's Canadian
    # contacts work, so it is not a day off here.
    ("CA", "2026-09-07", "Labour Day"), ("CA", "2026-10-12", "Thanksgiving"),
    ("CA", "2026-12-25", "Christmas Day"), ("CA", "2026-12-26", "Boxing Day"),
    ("ES", "2026-10-12", "National Day"), ("ES", "2026-12-08", "Immaculate Conception"),
    ("ES", "2026-12-25", "Christmas Day"),
    ("IE", "2026-10-26", "October bank holiday"), ("IE", "2026-12-25", "Christmas Day"),
    ("IE", "2026-12-28", "St Stephen's Day (substitute)"), ("IE", "2027-01-01", "New Year's Day"),
    # Brazil's national holidays (Lei 662/1949, Lei 6.802/1980, Lei 14.759/2023).
    ("BR", "2026-09-07", "Independence Day"), ("BR", "2026-10-12", "Our Lady of Aparecida"),
    ("BR", "2026-11-02", "All Souls' Day"), ("BR", "2026-11-20", "Black Consciousness Day"),
    ("BR", "2026-12-25", "Christmas Day"), ("BR", "2027-01-01", "New Year's Day"),
]

# A country not listed here gets no cold email at all until a manager adds its rule (gate.no_rule_message).
REGION_RULES = [
    ("US", "allowed"), ("CA", "consent_required"), ("GB", "basis_required"), ("DE", "consent_required"),
    # Spain (LSSI art. 21) and the Netherlands (Telecommunicatiewet 11.7) ask for opt-in before commercial email, to
    # businesses too. Counsel to confirm.
    ("FR", "basis_required"), ("NL", "consent_required"), ("ES", "consent_required"), ("IE", "basis_required"),
    # Brazil's LGPD allows legitimate interest (art. 7 IX) with a recorded assessment (art. 10). Counsel to confirm.
    ("BR", "basis_required"),
    # Not a legal rule: the demo's seller does not sell in Singapore yet, so it does not email there. Australia has no
    # rule at all, so nobody there is cold-emailed until a manager adds one.
    ("SG", "blocked"),
]

# Calls, per country: whether the SDRs call there, and the do-not-call register screened first. A country not listed
# is not called. Germany needs presumed consent for a business call (UWG section 7) and the Netherlands keeps no
# register for business lines, so neither is called by default. Counsel to confirm.
CALL_RULES = {
    "US": ("allowed", "National Do Not Call Registry"), "CA": ("allowed", "National Do Not Call List"),
    "GB": ("allowed", "TPS and CTPS"), "FR": ("allowed", "Bloctel"), "ES": ("allowed", "Lista Robinson"),
    "IE": ("allowed", "National Directory Database opt-out"), "BR": ("allowed", "Nao Me Perturbe"),
}

SENDING_DOMAINS = [
    # domain, registered days before start, mailboxes per (user index)
    ("getlumenledger.com", 220), ("lumenledger-hq.com", 210), ("trylumenledger.com", 190), ("lumenledgerapp.com", 25),
    ("hellolumenledger.com", 200), ("meetlumenledger.com", 180),
]
# Domains that send too little to Gmail for Postmaster Tools to report on: the sim never returns data for them.
POSTMASTER_SILENT = ("lumenledgerapp.com",)

# The monthly cap each demo play was launched with (credits per vendor, AI in cents). Phone lookups were 60 when the
# desk had four SDRs; at 3,000 accounts the three busiest plays ran out by mid-month and their accounts arrived on the 1st.
PLAY_CAP = {"people_search": 120, "email_finder": 120, "email_verifier": 240, "phone_finder": 150, "anthropic_cents": 1500}

# Flat fees, demo assumptions in the range public price lists show. A manager replaces them from real bills.
SUBSCRIPTIONS = [
    ("mail", 700, "mailbox", "A mailbox seat at the mail provider"),
    ("telemetry", 4900, "month", "Inbox placement tests"),
    ("warmup", 2900, "month", "Mailivery Starter: unlimited mailboxes, 200 warm-up emails a day shared"),
    ("linkedin", 7900, "sender", "One LinkedIn sender at HeyReach"),
    ("jobs_feed", 9900, "month", None), ("funding_feed", 4900, "month", None), ("people_moves", 14900, "month", None),
    ("web_visits", 19900, "month", None), ("intent_feed", 29900, "month", None), ("reviews_feed", 24900, "month", None),
    ("techstack_feed", 9900, "month", None), ("social_feed", 4900, "month", None), ("news_feed", 4900, "month", None),
]

BUDGETS = [("people_search", 400000), ("email_finder", 300000), ("email_verifier", 300000),
           ("phone_finder", 200000), ("email_resolver", 100000), ("company_data", 100000), ("anthropic", 30000)]  # vendor units: credits; anthropic in cents
