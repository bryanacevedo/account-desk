import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowSquareOut, X } from "@phosphor-icons/react";
import { api } from "./api";
import { Avatar, Logo } from "./marks";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Status, ago, ahead, cap, day, dayTime, money, n0, navigate, pct,
  useBusy, useData, withParam, type Glyph,
} from "./lib";

// ---------------------------------------------------------------- the sheet frame

export function openSheet(kind: string, id: number | string) {
  const cur = new URLSearchParams(window.location.search).get("sheet");
  const u = new URL(window.location.href);
  u.searchParams.set("sheet", `${kind}:${id}`);
  if (cur && cur !== `${kind}:${id}`) u.searchParams.set("from", cur); else u.searchParams.delete("from");
  navigate(u.pathname + "?" + u.searchParams.toString());
}

export function closeSheet() {
  const u = new URL(window.location.href);
  u.searchParams.delete("sheet");
  u.searchParams.delete("from");
  navigate(u.pathname + (u.searchParams.toString() ? "?" + u.searchParams.toString() : ""));
}

function Frame({ crumb, children, foot }: { crumb: ReactNode; children: ReactNode; foot?: ReactNode }) {
  const from = new URLSearchParams(window.location.search).get("from");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeSheet(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, []);
  const back = () => {
    if (!from) return;
    const u = new URL(window.location.href);
    u.searchParams.set("sheet", from);
    u.searchParams.delete("from");
    navigate(u.pathname + "?" + u.searchParams.toString());
  };
  return (
    <>
      <div className="scrim" onClick={closeSheet} aria-hidden="true" />
      <aside className="sheet" role="dialog" aria-modal="true" tabIndex={-1} ref={ref}>
        <div className="sheet-top">
          {from ? <button className="iconbtn" onClick={back} aria-label="Back"><ArrowLeft size={18} /></button> : null}
          <div className="crumb clip">{crumb}</div>
          <button className="iconbtn" onClick={closeSheet} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="sheet-body">{children}</div>
        {foot ? <div className="sheet-foot">{foot}</div> : null}
      </aside>
    </>
  );
}

export function SheetHost() {
  const params = new URLSearchParams(window.location.search);
  const sheet = params.get("sheet");
  if (!sheet) return null;
  const [kind, id] = sheet.split(":");
  const key = sheet;
  if (kind === "account") return <AccountSheet key={key} id={Number(id)} />;
  if (kind === "message") return <MessageSheet key={key} id={Number(id)} />;
  if (kind === "reply") return <ReplySheet key={key} id={Number(id)} />;
  if (kind === "play") return <PlaySheet key={key} id={Number(id)} />;
  return null;
}

// ---------------------------------------------------------------- shared vocab

export const PLAY_STATE: Record<string, [Glyph, string]> = {
  proposed: ["wait", "Proposed"], accepted: ["half", "Accepted"], researching: ["half", "Researching"],
  approving: ["wait", "Drafts to approve"], active: ["go", "In sequence"], engaged: ["ok", "Replied"],
  meeting: ["ok", "Meeting"], converted: ["ok", "Opportunity"], lost: ["stop", "Not interested"],
  stopped: ["off", "Ended"], skipped: ["off", "Skipped"], expired: ["off", "Expired"], held_out: ["none", "Comparison group"],
};
export const LABEL: Record<string, [Glyph, string]> = {
  interested: ["ok", "Interested"], meeting_request: ["ok", "Wants a meeting"], question: ["ok", "Asked a question"],
  not_now: ["hold", "Not now"], not_interested: ["stop", "Not interested"], referral: ["go", "Referred someone"],
  left_company: ["off", "Left the company"], out_of_office: ["none", "Out of office"], unsubscribe: ["stop", "Unsubscribed"],
  wrong_person: ["off", "Wrong person"], bounce: ["stop", "Bounced"], auto_reply: ["none", "Automatic reply"], other: ["wait", "Unclear"],
};
export const MSG: Record<string, [Glyph, string]> = {
  draft: ["none", "Draft"], failed_gate: ["stop", "Needs a rewrite"], awaiting_approval: ["wait", "To approve"],
  approved: ["half", "Approved"], rejected: ["off", "Rejected"], scheduled: ["half", "Scheduled"], sending: ["go", "Sending"],
  sent: ["ok", "Sent"], send_unknown: ["wait", "Outcome unknown"], failed: ["stop", "Failed"], cancelled: ["off", "Cancelled"],
};
const ENROLL: Record<string, [Glyph, string]> = {
  pending: ["wait", "First email to approve"], active: ["go", "In sequence"], paused: ["hold", "Paused"],
  stopped: ["off", "Stopped"], done: ["off", "Finished"],
};
const STOP: Record<string, string> = {
  replied_positive: "Replied", meeting_booked: "Meeting booked", bounced: "Bounced", unsubscribed: "Unsubscribed",
  not_interested: "Not interested", not_now: "Not now", wrong_person: "Wrong person", left_company: "Left",
  approval_lapsed: "Approval came too late", person_moved: "Changed jobs", referral: "Referred someone",
  reply_received: "Replied, reading it", account_reply: "Colleague replied", out_of_office: "Out of office",
};
const stopWord = (r: string | null) => (r ? STOP[r] || cap(r.replace(/^play_|^gate:|^rejected: /, "")) : "");

const PERSONA: Record<string, string> = { cfo: "Finance leader", controller: "Controller", revops: "Revenue operations", data: "Data and systems" };

// ---------------------------------------------------------------- account

export function AccountSheet({ id }: { id: number }) {
  const { data, error, reload } = useData<any>(`/api/accounts/${id}`);
  const [tab, setTab] = useState("overview");
  if (error) return <Frame crumb="Account"><Failed error={error} retry={reload} /></Frame>;
  if (!data) return <Frame crumb="Account"><Loading rows={8} /></Frame>;
  const a = data.account, s = data.score, cur = data.current;
  const tabs: [string, string, number?][] = [["overview", "Overview"], ["people", "People", data.people.length],
    ["signals", "Signals", data.signals.length], ["outreach", "Outreach", data.messages.length + data.replies.length]];
  return (
    <Frame crumb={<>Account</>}>
      <div className="who">
        <Logo domain={a.primary_domain} name={a.name} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{a.name}</h2>
          <div className="meta clip">{a.primary_domain} &middot; {a.industry}, {n0(a.employees)} people, {a.hq_country}</div>
        </div>
      </div>
      <div className="figs">
        <Fig value={s?.priority ?? 0} label="Priority" />
        <Fig value={s?.fit ?? a.fit_score ?? 0} label={`Fit, tier ${a.fit_tier}`} />
        <Fig value={s?.intent ?? 0} label="Intent" />
        <Fig value={a.owner || "Unassigned"} label="Owner" sm />
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([k, l, n]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}{n !== undefined ? <span className="n">{n}</span> : null}</button>)}
      </div>
      {tab === "overview" && <AccountOverview d={data} />}
      {tab === "people" && <AccountPeople d={data} />}
      {tab === "signals" && <SignalTimeline signals={data.signals} />}
      {tab === "outreach" && <AccountOutreach d={data} />}
      {cur ? null : data.holds.length ? <Section title="On hold"><div className="small mute">{data.holds[0].reason}, until {day(data.holds[0].until)}</div></Section> : null}
    </Frame>
  );
}

function WhyNow({ why }: { why: any }) {
  return (
    <div className="why">
      <span className="lbl">Why now</span>
      <div className="what">{why.summary}</div>
      <div className="because">{why.because}</div>
      <div className="actions small mute" style={{ justifyContent: "space-between" }}>
        <span>{why.label}, {ago(why.observed_at)}</span>
        {why.url ? <a className="src" href={why.url} target="_blank" rel="noreferrer noopener">Source <ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a> : null}
      </div>
    </div>
  );
}

function AccountOverview({ d }: { d: any }) {
  const cur = d.current;
  const max = Math.max(1, ...d.contributions.map((c: any) => c.value));
  const fit = (d.account.fit_breakdown?.factors || []) as any[];
  return (
    <>
      {cur ? (
        <Section title="In play" right={<Status kind={PLAY_STATE[cur.state][0]}>{PLAY_STATE[cur.state][1]}</Status>}>
          <div className="small mute">{cur.play}, proposed {ago(cur.proposed_at)}{cur.owner ? `, owned by ${cur.owner}` : ""}</div>
          <WhyNow why={cur.why_now} />
          {cur.brief?.findings?.length ? (
            <div className="section">
              <h2 style={{ fontSize: 13.5 }}>Brief</h2>
              <ul className="facts">
                {cur.brief.findings.map((f: any, i: number) => (
                  <li key={i}><span className="id">{i + 1}</span><span>{f.text} <span className="mono faint">{f.fact_ids.map((x: number) => `#${x}`).join(" ")}</span></span></li>
                ))}
              </ul>
            </div>
          ) : null}
        </Section>
      ) : d.plays[0]?.state === "held_out" ? (
        <Section title="Comparison group"><div className="mute">Matched {d.plays[0].play} on {day(d.plays[0].proposed_at)}. Not contacted, so the desk can measure what outreach adds.</div></Section>
      ) : null}
      <Section title="What moves the score">
        {d.contributions.length ? (
          <div className="bars">
            {d.contributions.slice(0, 7).map((c: any) => <Bar key={c.signal_id} label={c.label} value={c.value} of={max} shown={c.value.toFixed(1)} />)}
          </div>
        ) : <Empty title="No recent signals">The score is fit alone.</Empty>}
      </Section>
      <Section title="Fit">
        {d.account.fit_breakdown?.excluded ? <div className="mute">{d.account.fit_breakdown.excluded}</div> : (
          <div className="ledger">
            {fit.map((f) => (
              <div key={f.key} className="row" style={{ gridTemplateColumns: "1fr auto", minHeight: 36 }}>
                <span>{cap(f.key)}</span>
                <Status kind={f.matched ? (f.weight < 0 ? "stop" : "ok") : "none"}>{f.matched ? (f.weight < 0 ? `${f.contribution}` : `+${f.contribution}`) : "No match"}</Status>
              </div>
            ))}
          </div>
        )}
      </Section>
      {d.opportunities.length ? (
        <Section title="Pipeline">
          <div className="ledger">
            {d.opportunities.map((o: any) => (
              <div key={o.id} className="row" style={{ gridTemplateColumns: "1fr auto auto" }}>
                <div className="cell-main"><span className="t">{o.name}</span><span className="s">{o.stage}, {day(o.created_at)}</span></div>
                <span className="mute small">{cap(o.attribution)}</span>
                <span className="num">{o.amount_cents !== undefined ? money(o.amount_cents) : ""}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </>
  );
}

function AccountPeople({ d }: { d: any }) {
  const enrolled = d.people.filter((p: any) => p.enrollment);
  const others = d.people.filter((p: any) => !p.enrollment);
  const row = (p: any) => {
    const e = p.enrollment ? ENROLL[p.enrollment] : null;
    return (
      <div key={p.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }}>
        <Avatar name={p.full_name} photo={p.photo_url} />
        <div className="cell-main">
          <span className="t">{p.full_name}{p.is_champion ? <span className="mute small"> &middot; past champion</span> : null}</span>
          <span className="s">{p.title}{p.persona_key ? `, ${PERSONA[p.persona_key] || p.persona_key}` : ""}</span>
        </div>
        {e ? <Status kind={e[0]}>{p.enrollment === "stopped" || p.enrollment === "paused" ? stopWord(p.stop_reason || p.pause_reason) || e[1] : e[1]}</Status>
          : p.status !== "active" ? <Status kind="off">{cap(p.status)}</Status> : <span className="mute small">{p.email_status === "valid" ? "Verified email" : ""}</span>}
      </div>
    );
  };
  return (
    <>
      <Section title="Buying committee" count={enrolled.length}>
        {enrolled.length ? <div className="ledger">{enrolled.map(row)}</div> : <Empty title="Nobody contacted yet" />}
        {d.gaps.length ? (
          <div className="ledger">
            {d.gaps.map((g: any) => (
              <div key={g.persona_key} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr)" }}>
                <div className="mono-mark sm" style={{ background: "transparent", boxShadow: "inset 0 0 0 1px var(--line-2)" }}>?</div>
                <div className="cell-main"><span className="t">{g.label}</span><span className="s">{g.reason}</span></div>
              </div>
            ))}
          </div>
        ) : null}
      </Section>
      <Section title="Others at the company" count={others.length}>
        {others.length ? <div className="ledger">{others.map(row)}</div> : <Empty title="No one else on record" />}
      </Section>
    </>
  );
}

export function SignalTimeline({ signals }: { signals: any[] }) {
  if (!signals.length) return <Empty title="No signals yet" />;
  return (
    <ul className="timeline">
      {signals.map((s) => (
        <li key={s.id}>
          <span className="at">{day(s.observed_at)}</span>
          <i className="glyph go dot" aria-hidden="true" />
          <div className="cell-main" style={{ whiteSpace: "normal" }}>
            <span className="t" style={{ whiteSpace: "normal" }}>{s.label}</span>
            <span className="s" style={{ whiteSpace: "normal" }}>{s.evidence.summary}{s.evidence.url ? <> <a href={s.evidence.url} target="_blank" rel="noreferrer noopener" className="mute"><ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a></> : null}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function AccountOutreach({ d }: { d: any }) {
  return (
    <>
      <Section title="Emails" count={d.messages.length}>
        {d.messages.length ? (
          <div className="ledger">
            {d.messages.map((m: any) => (
              <button key={m.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto auto" }} onClick={() => openSheet("message", m.id)}>
                <div className="cell-main"><span className="t">{m.subject || "(no subject)"}</span><span className="s">{m.full_name}, email {m.step_index + 1}</span></div>
                <Status kind={MSG[m.status][0]}>{MSG[m.status][1]}</Status>
                <span className="mute small num" style={{ minWidth: 56 }}>{day(m.sent_at || m.scheduled_for)}</span>
              </button>
            ))}
          </div>
        ) : <Empty title="No emails yet" />}
      </Section>
      <Section title="Replies" count={d.replies.length}>
        {d.replies.length ? (
          <div className="ledger">
            {d.replies.map((r: any) => (
              <button key={r.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto auto" }} onClick={() => openSheet("reply", r.id)}>
                <div className="cell-main"><span className="t">{r.full_name || "Unknown sender"}</span><span className="s">{r.cleaned}</span></div>
                <Status kind={(LABEL[r.label] || LABEL.other)[0]}>{(LABEL[r.label] || LABEL.other)[1]}</Status>
                <span className="mute small num" style={{ minWidth: 56 }}>{day(r.received_at)}</span>
              </button>
            ))}
          </div>
        ) : <Empty title="No replies yet" />}
      </Section>
      {d.meetings.length ? (
        <Section title="Meetings">
          <div className="ledger">
            {d.meetings.map((m: any) => (
              <div key={m.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <div className="cell-main"><span className="t">{m.full_name || "Meeting"}</span><span className="s">{dayTime(m.starts_at)}</span></div>
                <Status kind={m.status === "held" ? "ok" : m.status === "booked" ? "go" : "off"}>{cap(m.status === "no_show" ? "no show" : m.status)}</Status>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------- an email to approve

function sentenceKind(k: string) { return k === "claim" ? "claim" : ""; }

export function MessageSheet({ id }: { id: number }) {
  const { data: m, error, reload } = useData<any>(`/api/messages/${id}`);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState("");
  const [subject, setSubject] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, run] = useBusy();
  const idOf = useMemo(() => {
    const map = new Map<number, number>();
    (m?.facts || []).forEach((f: any, i: number) => map.set(f.id, i + 1));
    return map;
  }, [m]);
  if (error) return <Frame crumb="Email"><Failed error={error} retry={reload} /></Frame>;
  if (!m) return <Frame crumb="Email"><Loading rows={8} /></Frame>;
  const open = m.status === "awaiting_approval" || m.status === "failed_gate";
  const sentences: any[] = m.citations?.sentences || [];
  const footer = m.body.split("\n\n--\n")[1];
  const failures: any[] = m.gate?.failures || [];
  const lastAttempt = (m.attempts || [])[0];
  const approve = () => run(async () => {
    await api(`/api/messages/${id}/approve`, { method: "POST", body: editing ? { subject, body } : {} });
    setEditing(false);
  }, "Approved. It will go out in their send window.");
  const reject = () => run(async () => {
    await api(`/api/messages/${id}/reject`, { method: "POST", body: { reason } });
    closeSheet();
  }, "Rejected.");
  const foot = open ? (
    rejecting ? (
      <>
        <input className="input" style={{ flex: 1 }} placeholder="Why, in a few words" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason for rejecting" autoFocus />
        <button className="btn line" onClick={() => setRejecting(false)}>Cancel</button>
        <button className="btn ink" disabled={busy || reason.trim().length < 3} onClick={reject}>Reject</button>
      </>
    ) : (
      <>
        <button className="btn quiet" onClick={() => setRejecting(true)}>Reject</button>
        {editing ? <button className="btn line" onClick={() => setEditing(false)}>Cancel edit</button>
          : <button className="btn line" onClick={() => { setEditing(true); setBody(m.body); setSubject(m.subject || ""); }}>Edit</button>}
        <button className="btn" disabled={busy} onClick={approve}>{editing ? "Save and approve" : "Approve"}</button>
      </>
    )
  ) : undefined;
  return (
    <Frame crumb={<>Email {m.step_index + 1} to {m.full_name}</>} foot={foot}>
      <div className="who">
        <Avatar name={m.full_name} photo={m.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{m.full_name}</h2>
          <div className="meta clip">{m.title}, <button className="btn quiet sm" style={{ padding: 0, height: "auto" }} onClick={() => openSheet("account", m.account_id)}>{m.company}</button></div>
        </div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={MSG[m.status][0]}>{MSG[m.status][1]}</Status>} label="Status" sm />
        <Fig value={m.play} label="Play" sm />
        <Fig value={m.mailbox || "Not chosen"} label="Sends from" sm />
      </div>
      {failures.length ? (
        <Section title="Why it needs a rewrite">
          <ul className="facts">{failures.map((f: any, i: number) => <li key={i}><Status kind="stop">{""}</Status><span>{f.message}</span></li>)}</ul>
        </Section>
      ) : null}
      {editing ? (
        <div className="section">
          <label className="field"><span>Subject</span><input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
          <label className="field"><span>Email</span><textarea className="input" rows={16} value={body} onChange={(e) => setBody(e.target.value)} /></label>
          <div className="small mute">The opt-out line at the bottom has to stay.</div>
        </div>
      ) : (
        <div className="draft">
          <div className="subject">{m.subject}</div>
          {sentences.length && !m.edited ? (
            <>
              <p>{sentences[0]?.text}</p>
              <p>{sentences.slice(1).map((s: any, i: number) => (
                <span key={i}><span className={sentenceKind(s.kind)}>{s.text}</span>{(s.fact_ids || []).map((f: number) => <sup key={f}>{idOf.get(f) ?? "?"}</sup>)} </span>
              ))}</p>
            </>
          ) : <p style={{ whiteSpace: "pre-wrap" }}>{m.body.split("\n\n--\n")[0]}</p>}
          {footer ? <div className="footer">{"--\n" + footer}</div> : null}
        </div>
      )}
      <Section title="What it rests on" count={m.facts.length}>
        {m.facts.length ? (
          <ul className="facts">
            {m.facts.map((f: any) => (
              <li key={f.id}><span className="id">{idOf.get(f.id)}</span>
                <span>{f.text} <span className="mute small">{f.kind.startsWith("signal:") ? "Signal" : "Their website"}, {day(f.observed_at)}</span>
                  {f.source_url ? <> <a href={f.source_url} target="_blank" rel="noreferrer noopener" className="mute"><ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a></> : null}</span>
              </li>
            ))}
          </ul>
        ) : <Empty title="No facts cited" />}
        <div className="small mute">Highlighted sentences say something about them. Each one is checked against the fact it cites.</div>
      </Section>
      {lastAttempt && m.attempts.length > 1 ? (
        <Section title="Checks">
          <div className="small mute">The first draft failed: {(lastAttempt.failures || []).map((f: any) => f.message).join("; ")}. The desk rewrote it once.</div>
        </Section>
      ) : null}
      <Section title="Why now"><WhyNow why={m.why_now} /></Section>
    </Frame>
  );
}

// ---------------------------------------------------------------- a reply

export function ReplySheet({ id }: { id: number }) {
  const { data: r, error, reload } = useData<any>(`/api/replies/${id}`);
  const [busy, run] = useBusy();
  const [label, setLabel] = useState("");
  if (error) return <Frame crumb="Reply"><Failed error={error} retry={reload} /></Frame>;
  if (!r) return <Frame crumb="Reply"><Loading rows={8} /></Frame>;
  const l = LABEL[r.label] || LABEL.other;
  const ex = r.extracted || {};
  const open = !r.handled_at;
  const act = (body: any, msg: string) => run(() => api(`/api/replies/${id}/handle`, { method: "POST", body }), msg);
  const foot = open ? (
    r.needs_review ? (
      <>
        <select className="select" style={{ width: 220 }} value={label} onChange={(e) => setLabel(e.target.value)} aria-label="What the reply means">
          <option value="">What does it mean?</option>
          {Object.entries(LABEL).map(([k, v]) => <option key={k} value={k}>{v[1]}</option>)}
        </select>
        <button className="btn" disabled={busy || !label} onClick={() => act({ outcome: "labelled", label }, "Labelled. The desk acts on it now.")}>Save</button>
      </>
    ) : (
      <>
        <button className="btn line" disabled={busy} onClick={() => act({ outcome: "answered" }, "Marked answered.")}>I answered</button>
        <button className="btn" disabled={busy} onClick={() => act({ outcome: "meeting_booked" }, "Meeting booked. The rest of the sequence stops.")}>Meeting booked</button>
      </>
    )
  ) : undefined;
  return (
    <Frame crumb={<>Reply from {r.full_name || r.from_addr}</>} foot={foot}>
      <div className="who">
        <Avatar name={r.full_name || r.from_addr} photo={r.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{r.full_name || r.from_addr}</h2>
          <div className="meta clip">{r.title ? `${r.title}, ` : ""}{r.account_id ? <button className="btn quiet sm" style={{ padding: 0, height: "auto" }} onClick={() => openSheet("account", r.account_id)}>{r.company}</button> : "No account matched"}</div>
        </div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={l[0]}>{l[1]}</Status>} label={r.classified_by === "rules" ? "Read by rules" : r.classified_by === "person" ? "Labelled by a person" : `Read by the model, ${pct(r.confidence)} sure`} sm />
        <Fig value={ago(r.received_at)} label="Received" sm />
        {r.hot && open && r.sla_due_at ? <Fig value={ahead(r.sla_due_at)} label="Answer by" sm /> : null}
        {r.handled_at ? <Fig value={cap(r.outcome || "handled")} label="Done" sm /> : null}
      </div>
      {r.needs_review ? <div className="why" style={{ background: "var(--well)" }}><span className="lbl" style={{ color: "var(--ink-2)" }}>Needs a person</span><div>{r.review_reason}. Nothing has been done with it yet.</div></div> : null}
      <div className="quote">{r.cleaned}</div>
      {r.same_person === false ? <div className="small mute">Written by someone other than the person we emailed.</div> : null}
      {ex.referral ? (
        <Section title="Referred to">
          <dl className="kv"><dt>Name</dt><dd>{ex.referral.name}</dd>{ex.referral.title ? <><dt>Role</dt><dd>{ex.referral.title}</dd></> : null}
            <dt>Email</dt><dd>{ex.referral.email || <span className="mute">Not in the reply; the desk will look it up</span>}</dd></dl>
        </Section>
      ) : null}
      {ex.suggested ? (
        <Section title="A reply you could send">
          <div className="quote ours">{ex.suggested}</div>
          <div className="small mute">Send it from your own inbox. The desk does not reply for you.</div>
        </Section>
      ) : null}
      <details>
        <summary className="small mute" style={{ cursor: "pointer" }}>The full email as received</summary>
        <pre className="mono small" style={{ whiteSpace: "pre-wrap", marginTop: 10, color: "var(--ink-2)" }}>{r.raw}</pre>
      </details>
      {r.our_subject ? (
        <Section title="What we sent">
          <div className="quote ours"><b>{r.our_subject}</b>{"\n\n"}{(r.our_body || "").split("\n\n--\n")[0]}</div>
        </Section>
      ) : null}
    </Frame>
  );
}

// ---------------------------------------------------------------- a play

export function PlaySheet({ id }: { id: number }) {
  const { data, error, reload } = useData<any>(`/api/plays`);
  const me = useData<any>("/api/me").data;
  const [busy, run] = useBusy();
  if (error) return <Frame crumb="Play"><Failed error={error} retry={reload} /></Frame>;
  const p = data?.plays.find((x: any) => x.id === id);
  if (!p) return <Frame crumb="Play"><Loading rows={8} /></Frame>;
  const f = p.funnel, lift = p.lift, promo = p.promotion;
  const isManager = me?.user.role === "manager";
  const change = (body: any, msg: string) => run(() => api(`/api/plays/${id}`, { method: "POST", body }), msg);
  const foot = me && me.user.role !== "sdr" ? (
    <>
      {p.status === "live" ? <button className="btn line" disabled={busy} onClick={() => change({ status: "paused", reason: "Paused from the desk" }, "Paused. Nothing new is proposed.")}>Pause</button>
        : <button className="btn line" disabled={busy || !isManager} onClick={() => change({ status: "live", reason: "Resumed from the desk" }, "Live again.")}>Resume</button>}
      {promo.next ? <button className="btn" disabled={busy || !promo.ready || !isManager} title={!isManager ? "A manager approves a promotion" : undefined}
        onClick={() => change({ autonomy: promo.next, reason: "Met every check" }, "Promoted.")}>Move to {STAGE[promo.next]}</button> : null}
    </>
  ) : undefined;
  return (
    <Frame crumb="Play" foot={foot}>
      <div style={{ display: "grid", gap: 6 }}>
        <h2 style={{ fontSize: 20, lineHeight: "26px", fontWeight: 620, letterSpacing: "-0.02em" }}>{p.name}</h2>
        <div className="mute">{p.hypothesis}</div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={p.status === "live" ? "go" : "off"}>{cap(p.status)}</Status>} label="Status" sm />
        <Fig value={STAGE[p.autonomy]} label="Who writes" sm />
        <Fig value={p.median_hours_to_first_touch ? `${Math.round(p.median_hours_to_first_touch)} h` : "None yet"} label="Signal to first email" sm />
        {p.pipeline_cents !== undefined ? <Fig value={money(p.pipeline_cents)} label="Pipeline sourced" sm /> : null}
      </div>
      <Section title="Accounts">
        <div className="funnel">
          <Bar label="Proposed" value={f.proposed} of={f.proposed} />
          <Bar label="Accepted" value={f.accepted} of={f.proposed} hint={pct(f.proposed ? f.accepted / f.proposed : 0)} />
          <Bar label="Emailed" value={f.contacted} of={f.proposed} hint={pct(f.proposed ? f.contacted / f.proposed : 0)} />
          <Bar label="Replied" value={f.replied} of={f.proposed} hint={pct(f.proposed ? f.replied / f.proposed : 0)} />
          <Bar label="Positive reply" value={f.positive} of={f.proposed} hint={pct(f.proposed ? f.positive / f.proposed : 0)} tone="accent" />
          <Bar label="Meeting" value={f.meetings} of={f.proposed} hint={pct(f.proposed ? f.meetings / f.proposed : 0)} tone="accent" />
        </div>
      </Section>
      <Section title="Compared with not contacted"><LiftBlock lift={lift} /></Section>
      <Section title="Trigger">
        <dl className="kv">
          <dt>Signals</dt><dd>{p.trigger.any_of.map(cap).join(", ")}</dd>
          <dt>Fit tiers</dt><dd>{p.trigger.fit_tiers.join(" and ")}</dd>
          <dt>Priority from</dt><dd>{p.trigger.min_priority}</dd>
          <dt>Signal age</dt><dd>Within {p.trigger.within_days} days</dd>
          <dt>Who</dt><dd>{p.personas.map((x: string) => PERSONA[x] || x).join(", ")}, up to {p.max_people}</dd>
          <dt>Comparison group</dt><dd>{p.holdout_pct}% of matched accounts</dd>
        </dl>
      </Section>
      <Section title="Sequence">
        <div className="ledger">
          {p.sequence.map((s: any, i: number) => (
            <div key={i} className="row" style={{ gridTemplateColumns: "56px minmax(0,1fr) auto", minHeight: 36 }}>
              <span className="mute">Day {s.day}</span>
              <span>{STEP[s.channel] || cap(s.channel)}, {cap(s.job).toLowerCase()}</span>
              <span className="mute small">{s.by === "desk" ? "The desk sends" : "SDR task"}</span>
            </div>
          ))}
        </div>
      </Section>
      {promo.next ? (
        <Section title={`Before moving to ${STAGE[promo.next].toLowerCase()}`}>
          <div className="ledger">
            {promo.checks.map((c: any) => (
              <div key={c.label} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto", minHeight: 36 }}>
                <Status kind={c.ok ? "ok" : "none"}>{c.label}</Status><span className="num">{c.value}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </Frame>
  );
}

export const STAGE: Record<string, string> = { research: "SDR writes", draft: "Desk drafts, SDR approves", supervised: "SDR approves first emails", autonomous: "Desk sends tier B" };
const STEP: Record<string, string> = { email: "Email", linkedin_connect: "LinkedIn", linkedin_message: "LinkedIn", call: "Call" };

export function LiftBlock({ lift }: { lift: any }) {
  const t = lift.treated, h = lift.holdout;
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="bars">
        <Bar label="Contacted" value={t.rate || 0} of={Math.max(t.rate || 0, h.rate || 0, 0.01)} shown={pct(t.rate, 1)} hint={`${t.meetings} of ${t.accounts}`} tone="accent" />
        <Bar label="Not contacted" value={h.rate || 0} of={Math.max(t.rate || 0, h.rate || 0, 0.01)} shown={pct(h.rate, 1)} hint={`${h.meetings} of ${h.accounts}`} tone="soft" />
      </div>
      {lift.enough && lift.difference !== null ? (
        <div>Meeting rate is <b>{pct(lift.difference, 1)}</b> points {lift.difference >= 0 ? "higher" : "lower"} when contacted, with 90% confidence between {pct(lift.interval[0], 1)} and {pct(lift.interval[1], 1)}.</div>
      ) : (
        <div className="mute">Not enough accounts yet. Telling a {pct(lift.detectable_lift)} difference apart needs {n0(lift.needed.holdout)} not contacted and {n0(lift.needed.treated)} contacted; there are {h.accounts} and {t.accounts}.</div>
      )}
    </div>
  );
}

export { withParam };
