import { useState } from "react";
import { CalendarCheck, ChatCircleText, Lightbulb, LinkedinLogo, MagnifyingGlass, PencilSimpleLine, Phone } from "@phosphor-icons/react";
import { api } from "../api";
import { Avatar, Logo } from "../marks";
import { SignalLabel } from "../signalIcons";
import {
  Empty, Failed, Fig, Loading, Section, Seg, Status, ago, ahead, cap, day, dayTime, n0, navigate, useBusy, useData,
  weekday, withParam, usePath,
} from "../lib";
import { LABEL, MSG, PLAY_STATE, openSheet } from "../sheets";

// ---------------------------------------------------------------- Today

export function Today() {
  const { data, error, reload } = useData<any>("/api/today");
  const me = useData<any>("/api/me").data;
  const [busy, run] = useBusy();
  const [skipping, setSkipping] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [leaving, setLeaving] = useState<number | null>(null);
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Today</h1></div><Loading /></div>;
  // A decided row slides away before the list refreshes, so the change is seen, not just noticed.
  const decide = (id: number, accept: boolean) => { setLeaving(id); return new Promise((r) => setTimeout(r, 260)).then(() => run(
    () => api(`/api/account-plays/${id}/decide`, { method: "POST", body: { accept, reason: accept ? null : reason } }),
    accept ? "Accepted. The desk is researching the account and drafting first emails." : "Skipped.",
  )).then(() => { setSkipping(null); setReason(""); setLeaving(null); }); };
  const overdue = data.replies.filter((r: any) => r.sla_due_at && new Date(r.sla_due_at).getTime() < new Date(data.now).getTime()).length;
  return (
    <div className="page rise">
      <div className="head">
        <div><h1>Today</h1><div className="sub">{weekday(data.now)}</div></div>
      </div>
      <div className="figs">
        <Fig value={data.replies.length} label={overdue ? `Replies, ${overdue} overdue` : "Replies to answer"} />
        <Fig value={data.proposals.length} label="Plays to decide" />
        <Fig value={data.approvals.length} label="Emails to approve" onClick={() => navigate("/approvals")} />
        <Fig value={data.tasks.length} label="Calls and LinkedIn" />
        <Fig value={data.meetings.length} label="Meetings this week" />
      </div>

      <Section title="Replies" icon={ChatCircleText}>
        {data.replies.length ? (
          <div className="ledger">
            {data.replies.map((r: any) => {
              const l = LABEL[r.label] || LABEL.other;
              const late = r.sla_due_at && new Date(r.sla_due_at).getTime() < new Date(data.now).getTime();
              return (
                <button key={r.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1.2fr) minmax(0,2fr) 150px 92px" }} onClick={() => openSheet("reply", r.id)}>
                  <Avatar name={r.full_name || r.company} photo={r.photo_url} />
                  <div className="cell-main"><span className="t">{r.full_name || "Unknown sender"}</span><span className="s">{r.company}</span><span className="s only-sm">{r.cleaned}</span></div>
                  <span className="clip mute hide-sm">{r.cleaned}</span>
                  <span className="hide-sm"><Status kind={l[0]}>{l[1]}</Status></span>
                  <span className="num small" style={{ color: late ? "var(--ink)" : "var(--mute)", fontWeight: late ? 600 : 400 }}>
                    {r.sla_due_at ? (late ? `Due ${ago(r.sla_due_at)}` : `Due ${ahead(r.sla_due_at)}`) : ago(r.received_at)}
                  </span>
                </button>
              );
            })}
          </div>
        ) : <Empty title="No replies waiting" />}
      </Section>

      <Section icon={Lightbulb} title={me?.user.role === "sdr" ? "Plays proposed to you" : "Plays proposed to the team"}>
        {data.proposals.length ? (
          <div className="ledger">
            {data.proposals.map((p: any, i: number) => (
              <div key={p.id} className={`row prop-row${leaving === p.id ? " is-leaving" : ""}`} style={{ gridTemplateColumns: "28px minmax(0,1.1fr) minmax(0,2fr) 52px auto", animationDelay: `${i * 60}ms` }}>
                <Logo domain={p.primary_domain} name={p.name} />
                <button className="cell-main" style={{ background: "none", border: 0, padding: 0, textAlign: "left" }} onClick={() => openSheet("account", p.account_id)}>
                  <span className="t prop-play">{p.play}</span><span className="s">at <span className="prop-acct">{p.name}</span>{p.urgent ? ", urgent" : ""}{me?.user.role !== "sdr" && p.owner ? `, ${p.owner}` : ""}</span><span className="s only-sm">{p.why_now.summary}</span>
                </button>
                <div className="cell-main hide-sm"><span className="t" style={{ fontWeight: 450 }}>{p.why_now.summary}</span><span className="s"><SignalLabel type={p.why_now.type} label={ago(p.why_now.observed_at)} /></span></div>
                <span className="num hide-sm"><span className="mute small">Priority </span>{p.priority}</span>
                {skipping === p.id ? (
                  <div className="actions">
                    <input className="input" style={{ width: 200 }} placeholder="Why skip?" value={reason} autoFocus onChange={(e) => setReason(e.target.value)} aria-label="Reason for skipping" />
                    <button className="btn line sm" disabled={busy || reason.trim().length < 3} onClick={() => decide(p.id, false)}>Skip</button>
                    <button className="btn quiet sm" onClick={() => setSkipping(null)}>Cancel</button>
                  </div>
                ) : (
                  <div className="actions">
                    <button className="btn quiet sm" onClick={() => setSkipping(p.id)}>Skip</button>
                    <button className="btn sm" disabled={busy} onClick={() => decide(p.id, true)}>Accept</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : <Empty title="Nothing to decide" />}
      </Section>

      <div className="two">
        <Section title="Emails to approve" icon={PencilSimpleLine}>
          {data.approvals.length ? (
            <div className="ledger">
              {data.approvals.slice(0, 8).map((m: any) => (
                <button key={m.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet("message", m.id)}>
                  <div className="cell-main"><span className="t">{m.full_name}</span><span className="s">{m.company}, Email {m.email_no ?? m.step_index + 1}</span></div>
                  {m.status === "failed_gate" ? <Status kind={MSG[m.status][0]}>{MSG[m.status][1]}</Status> : <span />}
                </button>
              ))}
              {data.approvals.length > 8 ? <button className="row" style={{ gridTemplateColumns: "1fr", color: "var(--accent)" }} onClick={() => navigate("/approvals")}>All {data.approvals.length}</button> : null}
            </div>
          ) : <Empty title="All approved" />}
        </Section>
        <Section title="Calls and LinkedIn" icon={Phone}>
          {data.tasks.length ? (
            <div className="ledger">
              {data.tasks.slice(0, 8).map((t: any) => <TaskRow key={t.id} t={t} />)}
            </div>
          ) : <Empty title="No tasks due" />}
        </Section>
      </div>

      {data.meetings.length ? (
        <Section title="Meetings this week" icon={CalendarCheck}>
          <div className="ledger">
            {data.meetings.map((m: any) => (
              <button key={m.id} className="row" style={{ gridTemplateColumns: "120px minmax(0,1fr) auto" }} onClick={() => openSheet("meeting", m.id)}>
                <span className="mute">{dayTime(m.starts_at)}</span>
                <div className="cell-main"><span className="t">{m.company}</span><span className="s">{m.full_name}</span></div>
                <Status kind={m.status === "held" ? "ok" : "go"}>{cap(m.status)}</Status>
              </button>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}

function TaskRow({ t }: { t: any }) {
  const Ic = t.kind === "call" ? Phone : t.kind.startsWith("linkedin") ? LinkedinLogo : MagnifyingGlass;
  const hint = t.draft_status === "failed_gate" ? "Note needs a rewrite" : t.draft ? "Note drafted" : t.kind === "call" ? t.phone : "";
  return (
    <button className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }} onClick={() => openSheet("task", t.id)}>
      <Avatar name={t.full_name || t.company} photo={t.photo_url} />
      <div className="cell-main"><span className="t">{t.title.replace(/ \(.*\)$/, "")}</span><span className="s">{t.company}{hint ? `, ${hint}` : ""}</span></div>
      <span className="mute"><Ic size={16} aria-hidden="true" /></span>
    </button>
  );
}

// ---------------------------------------------------------------- Accounts

export function Accounts() {
  const [, params] = usePath();
  const view = (params.get("view") || "priority") as "priority" | "in_play" | "rising" | "all";
  const [q, setQ] = useState(params.get("q") || "");
  const page = Math.max(1, Number(params.get("page") || 1));
  const { data, error, reload } = useData<any>(`/api/accounts?view=${view}&page=${page}${params.get("q") ? `&q=${encodeURIComponent(params.get("q")!)}` : ""}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  const first = data ? (page - 1) * data.per_page + 1 : 0;
  const last = data ? Math.min(page * data.per_page, data.total) : 0;
  return (
    <div className="page">
      <div className="head">
        <div><h1>Accounts</h1></div>{data ? <Fig value={n0(data.total)} label="Accounts" sm /> : null}
      </div>
      <div className="toolbar">
        <Seg label="Which accounts" value={view} onChange={(v) => {
            // A new view starts again at page 1.
            const u = new URL(window.location.href);
            u.searchParams.delete("page");
            if (v === "priority") u.searchParams.delete("view"); else u.searchParams.set("view", v);
            navigate(u.pathname + (u.search || ""), true);
          }}
          options={[["priority", "Fit our profile"], ["in_play", "In a play"], ["rising", "Rising this week"], ["all", "All"]]} />
        <form onSubmit={(e) => e.preventDefault()}>
          <input className="input" style={{ width: 240 }} type="search" placeholder="Company or domain" value={q} aria-label="Search accounts"
            onChange={(e) => { const v = e.target.value; setQ(v); window.clearTimeout((window as any).__acctq); (window as any).__acctq = window.setTimeout(() => (() => { const u = new URL(window.location.href); u.searchParams.delete("page"); if (v.trim()) u.searchParams.set("q", v.trim()); else u.searchParams.delete("q"); navigate(u.pathname + (u.search || ""), true); })(), 220); }} />
        </form>
      </div>
      {error ? <Failed error={error} retry={reload} /> : !data ? <Loading rows={12} /> : data.accounts.length === 0 ? <Empty title="No accounts match" /> : (
        <div className="ledger wrap-names">
          <div className="row head" style={{ gridTemplateColumns: COLS }}>
            <span /><span>Company</span><span>Latest signal</span><span className="num">Priority</span><span className="num">This week</span><span>Stage</span><span>Owner</span>
          </div>
          {data.accounts.map((a: any) => {
            const st = a.play_state ? PLAY_STATE[a.play_state] : null;
            return (
              <button key={a.id} className="row" style={{ gridTemplateColumns: COLS }} onClick={() => openSheet("account", a.id)}>
                <Logo domain={a.primary_domain} name={a.name} />
                <div className="cell-main"><span className="t">{a.name}</span><span className="s">{a.industry}, {n0(a.employees)} people, tier {a.fit_tier}</span><span className="s only-sm">{a.reason || "No recent signal"}</span></div>
                <div className="cell-main hide-sm">{a.reason ? <><span className="t" style={{ fontWeight: 450 }}><SignalLabel type={a.reason_type} label={a.reason} /></span><span className="s" style={{ paddingLeft: 30 }}>{day(a.reason_at)}</span></> : <span className="mute">No recent signal</span>}</div>
                <span className="num strong">{a.priority ?? 0}</span>
                <span className="num hide-sm" style={{ color: a.week_change > 0 ? "var(--ink)" : "var(--faint)" }}>{a.week_change > 0 ? `+${a.week_change}` : a.week_change < 0 ? a.week_change : ""}</span>
                <span className="hide-sm">{st ? <Status kind={st[0]}>{st[1]}</Status>
                  : a.last_state === "held_out" && a.hold_until ? <span className="mute">Held back</span>
                  : a.hold_until ? <span className="mute" title="Not proposed again until then: someone asked us to come back later, or a play just ended here.">Not proposed until {day(a.hold_until)}</span>
                  : <span className="faint">Not in a play</span>}</span>
                <span className="clip mute hide-sm">{a.owner || "Unassigned"}</span>
              </button>
            );
          })}
        </div>
      )}
      {data && data.total > data.per_page ? (
        <nav className="pager" aria-label="Pages of accounts">
          <span className="mute small">{n0(first)} to {n0(last)} of {n0(data.total)}</span>
          <span className="pager-buttons">
            <button className="btn line sm" disabled={page <= 1} onClick={() => { navigate(withParam("page", page - 1 <= 1 ? null : String(page - 1)), true); window.scrollTo(0, 0); }}>Previous</button>
            <span className="small">Page {page} of {pages}</span>
            <button className="btn line sm" disabled={page >= pages} onClick={() => { navigate(withParam("page", String(page + 1)), true); window.scrollTo(0, 0); }}>Next</button>
          </span>
        </nav>
      ) : null}
    </div>
  );
}
const COLS = "28px minmax(0,1.4fr) minmax(0,1.6fr) 64px 52px 150px 120px";
