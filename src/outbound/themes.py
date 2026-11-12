"""Themes: each learning from a call is filed under one short label for one idea, so the same reason said ten ways
counts as one reason (docs/PLAY-SUGGESTIONS.md section 1).

The model files a learning; code checks the answer. A picked theme must exist and be of the learning's kind; a new
label is short, holds no person's name and no email address, and is unique per kind whatever its case. A failed answer
is asked again once with the failures named; after that the learning stays unfiled and the team is told.

Filing runs as a background job queued by `pipeline.learn_from`, never inside the request that marked the notes."""
from __future__ import annotations

import logging
import re

from . import alerts, db, jobs, llm

log = logging.getLogger("outbound.themes")

FILED = ("reason_to_buy", "competitor", "objection", "reason_not")  # a quote is not filed
LABEL_MAX = 80
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _word_in(name: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w])" + re.escape(name.lower()) + r"(?![\w])", text.lower()))


def names_in(cur, text: str, *, companies: bool = False) -> list[str]:
    """Names of people and users in the desk that appear in the text, as whole words. A user's first name counts too,
    since a label or an angle naming an SDR is the leak most likely to happen. With companies, account names count."""
    if not text:
        return []
    found = [r["name"] for r in db.all(cur, """
        select full_name as name from people where length(full_name) >= 4 and position(lower(full_name) in lower(%s)) > 0
        union select name from users where position(lower(name) in lower(%s)) > 0
        union select split_part(name, ' ', 1) from users where length(split_part(name, ' ', 1)) >= 3
          and position(lower(split_part(name, ' ', 1)) in lower(%s)) > 0""", text, text, text)]
    if companies:
        found += [r["name"] for r in db.all(cur, """
            select name from accounts where length(name) >= 3 and position(lower(name) in lower(%s)) > 0
            union select primary_domain from accounts where position(lower(primary_domain) in lower(%s)) > 0""", text, text)]
    return sorted({n for n in found if _word_in(n, text)})


def check_choice(cur, out: dict, kind: str, existing: dict[int, str]) -> list[str]:
    """What is wrong with the model's answer, in words it can act on. Empty when it can be used."""
    tid, label = out.get("theme_id"), (out.get("new_label") or "").strip()
    if tid is not None and label:
        return ["Return either an existing theme id or a new label, not both."]
    if tid is not None:
        return [] if tid in existing else [f"Theme {tid} is not one of the {kind.replace('_', ' ')} themes given."]
    if not label:
        return ["Return an existing theme id or a new label."]
    fails = []
    if len(label) > LABEL_MAX:
        fails.append(f"The label is {len(label)} characters; keep it to {LABEL_MAX}.")
    if EMAIL.search(label):
        fails.append("The label contains an email address.")
    for name in names_in(cur, label):
        fails.append(f"The label names {name}; a theme never names a person.")
    return fails


def _existing(cur, kind: str) -> dict[int, str]:
    return {r["id"]: r["label"] for r in db.all(cur, "select id, label from learning_themes where kind = %s order by id", kind)}


def theme_for_label(cur, kind: str, label: str) -> int:
    """The theme with this label, made if new. The same label in another case is the same theme, and two workers
    filing the same new label at once end on one theme: the second insert waits for the first and does nothing."""
    label = label.strip()
    db.run(cur, "insert into learning_themes (kind, label) values (%s, %s) on conflict (kind, lower(label)) do nothing",
           kind, label)
    return db.val(cur, "select id from learning_themes where kind = %s and lower(label) = lower(%s)", kind, label)


def file_learning(cur, learning_id: int) -> int | None:
    """File one learning. Returns its theme id, or None when it is not filed (a quote, or two failed answers)."""
    item = db.one(cur, "select id, kind, text, theme_id from learnings where id = %s for update", learning_id)
    if item is None or item["kind"] not in FILED:
        return None
    if item["theme_id"] is not None:
        return item["theme_id"]
    # The model sees each theme by its place in the list (1, 2, 3), not its database id, so the same question is
    # always asked the same way and a recorded answer replays.
    real = list(_existing(cur, item["kind"]).items())
    existing = {i + 1: label for i, (_, label) in enumerate(real)}
    payload: dict = {"kind": item["kind"], "text": item["text"],
                     "themes": [{"id": k, "label": v} for k, v in existing.items()]}
    for _ in (1, 2):
        out = llm.run(cur, "theme", payload)
        fails = check_choice(cur, out, item["kind"], existing)
        if not fails:
            tid = real[out["theme_id"] - 1][0] if out["theme_id"] is not None else None
            if tid is None:
                tid = theme_for_label(cur, item["kind"], out["new_label"])
            db.run(cur, "update learnings set theme_id = %s where id = %s", tid, learning_id)
            return tid
        payload = {**payload, "failures": fails}
    alerts.raise_alert(cur, kind="theme_failed", severity="info", channel="#outbound-ops",
                       title="A learning from a call could not be filed under a theme",
                       body="The model's answer failed the checks twice, so it stays unfiled. " + " ".join(fails)[:400],
                       object_kind="learning", object_id=learning_id, dedup_key=f"theme_failed:{learning_id}")
    return None


@jobs.handler("file_learnings")
def file_learnings(cur, payload: dict) -> None:
    """File the learnings of one call note, then look for patterns again."""
    for r in db.all(cur, """select id from learnings where call_note_id = %s and theme_id is null and kind = any(%s)
                            order by id""", payload["call_note_id"], list(FILED)):
        file_learning(cur, r["id"])
    jobs.enqueue(cur, "check_patterns", {}, dedupe_key="check_patterns")


def backfill(batch: int = 50) -> int:
    """File every unfiled learning, a batch per transaction, then look for patterns. Returns how many were filed."""
    from . import suggestions
    filed = 0
    while True:
        with db.tx() as cur:
            ids = [r["id"] for r in db.all(cur, """select id from learnings where theme_id is null and kind = any(%s)
                                                   and not exists (select 1 from alerts a where a.kind = 'theme_failed'
                                                                   and a.object_id = learnings.id)
                                                   order by id limit %s""", list(FILED), batch)]
            for i in ids:
                filed += file_learning(cur, i) is not None
        if len(ids) < batch:
            break
    suggestions.sweep()
    return filed
