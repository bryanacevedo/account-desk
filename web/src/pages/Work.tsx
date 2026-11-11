import { useState } from "react";
import { LinkedinLogo, Phone, MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../api";
import { Avatar, Logo } from "../marks";
import {
  Empty, Failed, Fig, Loading, Section, Seg, Status, ago, ahead, cap, day, dayTime, navigate, useBusy, useData,
  weekday, withParam, usePath,
} from "../lib";
import { LABEL, MSG, PLAY_STATE, openSheet } from "../sheets";

// ---------------------------------------------------------------- Today

export function Today() {
  const { data, error, reload } = useData<any>("/api/today");
  const [busy, run] = useBusy();
  const [skipping, setSkipping] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Today</h1></div><Loading /></div>;
  const decide = (id: number, accept: boolean) => run(
    () => api(`/api/account-plays/${id}/decide`, { method: "POST", body: { accept, reason: accept ? null : reason } }),
    accept ? "Accepted. The desk is researching the account and drafting first emails." : "Skipped.",
  ).then(() => { setSkipping(null); setReason(""); });
  const overdue = data.replies.filter((r: any) => r.sla_due_at && new Date(r.sla_due_at).getTime() < new Date(data.now).getTime()).length;
  return (
    <div className="page rise">
      <div className="head">
        <div><h1>Today</h1><div className="sub">{weekday(data.now)}</div></div>
      </div>
      <div className="figs">
        <Fig value={data.replies.length} label={overdue ? `Replies, ${overdue} past due` : "Replies to answer"} />
        <Fig value={data.proposals.length} label="Accounts to decide" />
        <Fig value={data.approvals.length} label="Emails to approve" onClick={() => navigate("/approvals")} />
        <Fig value={data.tasks.length} label="Calls and LinkedIn" />
        <Fig value={data.meetings.length} label="Meetings this week" />
      </div>

      <Section title="Replies" count={data.replies.length}>
        {data.replies.length ? (
          <div className="ledger">
            {data.replies.map((r: any) => {
              const l = LABEL[r.label] || LABEL.other;
              const late = r.sla_due_at && new Date(r.sla_due_at).getTime() < new Date(data.now).getTime();
              return (
                <button key={r.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1.2fr) minmax(0,2fr) 150px 92px" }} onClick={() => openSheet("reply", r.id)}>
                  <Avatar name={r.full_name || r.company} photo={r.photo_url} />
                  <div className="cell-main"><span className="t">{r.full_name || "Unknown sender"}</span><span className="s">{r.company}</span></div>
                  <span className="clip mute hide-sm">{r.cleaned}</span>
                  <span className="hide-sm"><Status kind={l[0]}>{l[1]}</Status></span>
                  <span className="num small" style={{ color: late ? "var(--ink)" : "var(--mute)", fontWeight: late ? 600 : 400 }}>
                    {r.sla_due_at ? (late ? `Due ${ago(r.sla_due_at)}` : `Due ${ahead(r.sla_due_at)}`) : ago(r.received_at)}
                  </span>
                </button>
              );
            })}
          </div>
        ) : <Empty title="No replies waiting">Hot replies land here with the time you have to answer.</Empty>}
      </Section>

      <Section title="Accounts proposed to you" count={data.proposals.length}>
        {data.proposals.length ? (
          <div className="ledger">
            {data.proposals.map((p: any) => (
              <div key={p.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1.1fr) minmax(0,2fr) 52px auto" }}>
                <Logo domain={p.primary_domain} name={p.name} />
                <button className="cell-main" style={{ background: "none", border: 0, padding: 0, textAlign: "left" }} onClick={() => openSheet("account", p.account_id)}>
                  <span className="t">{p.name}</span><span className="s">{p.play}{p.urgent ? ", answer today" : ""}</span>
                </button>
                <div className="cell-main hide-sm"><span className="t" style={{ fontWeight: 450 }}>{p.why_now.summary}</span><span className="s">{p.why_now.label}, {ago(p.why_now.observed_at)}</span></div>
                <span className="num hide-sm" title="Priority">{p.priority}</span>
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
        ) : <Empty title="Nothing to decide">The desk proposes an account when a signal fits a play.</Empty>}
      </Section>

      <div className="two">
        <Section title="Emails to approve" count={data.approvals.length}>
          {data.approvals.length ? (
            <div className="ledger">
              {data.approvals.slice(0, 8).map((m: any) => (
                <button key={m.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet("message", m.id)}>
                  <div className="cell-main"><span className="t">{m.full_name}</span><span className="s">{m.company}, email {m.step_index + 1}</span></div>
                  <Status kind={MSG[m.status][0]}>{MSG[m.status][1]}</Status>
                </button>
              ))}
              {data.approvals.length > 8 ? <button className="row" style={{ gridTemplateColumns: "1fr", color: "var(--accent)" }} onClick={() => navigate("/approvals")}>All {data.approvals.length}</button> : null}
            </div>
          ) : <Empty title="All approved" />}
        </Section>
        <Section title="Calls and LinkedIn" count={data.tasks.length}>
          {data.tasks.length ? (
            <div className="ledger">
              {data.tasks.slice(0, 8).map((t: any) => <TaskRow key={t.id} t={t} />)}
            </div>
          ) : <Empty title="No tasks due" />}
        </Section>
      </div>

      {data.meetings.length ? (
        <Section title="Meetings this week" count={data.meetings.length}>
          <div className="ledger">
            {data.meetings.map((m: any) => (
              <button key={m.id} className="row" style={{ gridTemplateColumns: "120px minmax(0,1fr) auto" }} onClick={() => openSheet("account", m.account_id)}>
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
  const [busy, run] = useBusy();
  const icon = t.kind === "call" ? <Phone size={16} /> : t.kind.startsWith("linkedin") ? <LinkedinLogo size={16} /> : <MagnifyingGlass size={16} />;
  return (
    <div className="row" style={{ gridTemplateColumns: "20px minmax(0,1fr) auto" }}>
      <span className="mute">{icon}</span>
      <button className="cell-main" style={{ background: "none", border: 0, padding: 0, textAlign: "left" }} onClick={() => t.account_id && openSheet("account", t.account_id)}>
        <span className="t">{t.title}</span><span className="s">{t.company}{t.note ? `, ${t.note}` : ""}</span>
      </button>
      <div className="actions">
        {t.kind.startsWith("linkedin") && t.linkedin_url ? <a className="btn quiet sm" href={t.linkedin_url} target="_blank" rel="noreferrer noopener">Profile</a> : null}
        <button className="btn line sm" disabled={busy} onClick={() => run(() => api(`/api/tasks/${t.id}/done`, { method: "POST" }), "Done.")}>Done</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Accounts

export function Accounts() {
  const [, params] = usePath();
  const view = (params.get("view") || "priority") as "priority" | "in_play" | "rising" | "all";
  const [q, setQ] = useState(params.get("q") || "");
  const { data, error, reload } = useData<any>(`/api/accounts?view=${view}${params.get("q") ? `&q=${encodeURIComponent(params.get("q")!)}` : ""}`);
  return (
    <div className="page">
      <div className="head">
        <div><h1>Accounts</h1><div className="sub">Ranked by priority: how well they fit, and how strongly they are showing it now.</div></div>
      </div>
      <div className="toolbar">
        <Seg label="Which accounts" value={view} onChange={(v) => navigate(withParam("view", v === "priority" ? null : v), true)}
          options={[["priority", "Fit our profile"], ["in_play", "In a play"], ["rising", "Rising this week"], ["all", "All"]]} />
        <form onSubmit={(e) => { e.preventDefault(); navigate(withParam("q", q.trim() || null), true); }}>
          <input className="input" style={{ width: 240 }} type="search" placeholder="Company or domain" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search accounts" />
        </form>
      </div>
      {error ? <Failed error={error} retry={reload} /> : !data ? <Loading rows={12} /> : data.accounts.length === 0 ? <Empty title="No accounts match" /> : (
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: COLS }}>
            <span /><span>Company</span><span>Why now</span><span className="num">Priority</span><span className="num">Week</span><span>Stage</span><span>Owner</span>
          </div>
          {data.accounts.map((a: any) => {
            const st = a.play_state ? PLAY_STATE[a.play_state] : null;
            return (
              <button key={a.id} className="row" style={{ gridTemplateColumns: COLS }} onClick={() => openSheet("account", a.id)}>
                <Logo domain={a.primary_domain} name={a.name} />
                <div className="cell-main"><span className="t">{a.name}</span><span className="s">{a.industry}, {a.employees} people, tier {a.fit_tier}</span></div>
                <div className="cell-main hide-sm">{a.reason ? <><span className="t" style={{ fontWeight: 450 }}>{a.reason}</span><span className="s">{day(a.reason_at)}</span></> : <span className="mute">No recent signal</span>}</div>
                <span className="num strong">{a.priority ?? 0}</span>
                <span className="num hide-sm" style={{ color: a.week_change > 0 ? "var(--ink)" : "var(--faint)" }}>{a.week_change > 0 ? `+${a.week_change}` : a.week_change < 0 ? a.week_change : ""}</span>
                <span className="hide-sm">{st ? <Status kind={st[0]}>{st[1]}</Status>
                  : a.last_state === "held_out" && a.hold_until ? <Status kind="none">Comparison group</Status>
                  : a.hold_until ? <span className="mute">Rests until {day(a.hold_until)}</span>
                  : <span className="faint">Not in a play</span>}</span>
                <span className="clip mute hide-sm">{a.owner || "Unassigned"}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
const COLS = "28px minmax(0,1.4fr) minmax(0,1.6fr) 64px 52px 150px 120px";
