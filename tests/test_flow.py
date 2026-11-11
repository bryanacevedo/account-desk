"""Three simulated weeks of the whole desk, then every promise checked against what actually happened."""
from __future__ import annotations

from outbound import db, monitors


def q(sql, *args):
    with db.tx() as cur:
        return db.all(cur, sql, *args)


def v(sql, *args):
    with db.tx() as cur:
        return db.val(cur, sql, *args)


def test_the_desk_did_real_work(world):
    assert v("select count(*) from signals where status = 'matched'") > 100
    assert v("select count(*) from account_plays where arm = 'treated'") > 5
    assert v("select count(*) from messages where status = 'sent'") > 10
    assert v("select count(*) from replies") > 0


def test_no_job_died(world):
    assert q("select kind, last_error from jobs where status = 'dead'") == []


def test_every_monitor_passes(world):
    with db.tx() as cur:
        results = monitors.run_all(cur, {})
    failing = [r for r in results if not r["ok"] and r["monitor"] not in ("source_silent", "alerts_undelivered")]
    assert failing == []


def test_comparison_group_never_contacted(world):
    assert v("""select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                join account_plays ap on ap.id = e.account_play_id where ap.arm = 'holdout'""") == 0
    assert v("""select count(*) from touches t join account_plays ap on ap.account_id = t.account_id
                where ap.arm = 'holdout' and t.direction = 'out' and t.at between ap.proposed_at
                and ap.proposed_at + interval '90 days'""") == 0


def test_every_sent_message_matches_what_was_approved(world):
    assert v("select count(*) from messages where status = 'sent' and approved_hash is distinct from body_hash") == 0


def test_no_desk_email_after_a_reply_except_out_of_office(world):
    bad = q("""select m.id from messages m join enrollments e on e.id = m.enrollment_id
               join replies r on r.person_id = e.person_id
               where m.status = 'sent' and m.sent_at > r.received_at
                 and coalesce(r.label, '') not in ('out_of_office', 'auto_reply')""")
    assert bad == []


def test_no_two_people_at_one_company_got_a_first_email_the_same_day(world):
    bad = q("""select ap.account_id, m.sent_at::date, count(*) from messages m join enrollments e on e.id = m.enrollment_id
               join account_plays ap on ap.id = e.account_play_id
               where m.status = 'sent' and m.step_index = 0 group by 1, 2 having count(*) > 1""")
    assert bad == []


def test_mailbox_caps_were_respected(world):
    bad = q("""select m.mailbox_id, m.sent_at::date, count(*) from messages m where m.status = 'sent'
               group by 1, 2 having count(*) > 30""")
    assert bad == []


def test_every_email_carries_the_legal_footer(world):
    assert v("select count(*) from messages where status = 'sent' and body not like '%%won''t write again%%'") == 0
    assert v("select count(*) from messages where status = 'sent' and body not like '%%400 Market Street%%'") == 0


def test_no_sent_email_cites_tracking_data(world):
    bad = q("""select m.id from messages m, jsonb_array_elements_text(m.citations->'ids') c(id)
               join facts f on f.id = c.id::bigint
               where m.status = 'sent' and f.kind in ('signal:pricing_visit', 'signal:site_visit', 'signal:intent_topic',
                 'signal:product_signup', 'signal:social_engaged', 'signal:event_attended')""")
    assert bad == []


def test_every_paid_call_left_a_ledger_row(world):
    assert v("""select count(*) from adapter_calls c where c.paid and c.ok
                and not exists (select 1 from ledger l where l.adapter_call_id = c.id)""") == 0


def test_hot_replies_reached_a_person(world):
    assert v("""select count(*) from replies r where r.hot and not exists
                (select 1 from tasks t where t.reply_id = r.id and t.kind = 'reply')""") == 0
