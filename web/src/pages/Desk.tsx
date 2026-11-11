import { useState } from "react";
import { EnvelopeSimple, LinkedinLogo, Phone } from "@phosphor-icons/react";
import { api } from "../api";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Status, VENDOR_NAME, ago, cap, day, money, n0, pct, useBusy, useData,
} from "../lib";
import { Comparison, LABEL, openSheet } from "../sheets";
import { SignalLabel } from "../signalIcons";

// ---------------------------------------------------------------- Deliverability

export function Deliverability() {
  const { data, error, reload } = useData<any>("/api/deliverability");
  const me = useData<any>("/api/me").data;
  const isManager = me?.user.role === "manager";
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Inboxes</h1></div><Loading /></div>;
  const healthy = data.mailboxes.filter((m: any) => !m.blocked).length;
  const scheduled = data.forecast.reduce((s: number, d: any) => s + Number(d.scheduled), 0);
  const paused = data.watch.filter((w: any) => w.paused);
  return (
    <div className="page">
      <div className="head"><div><h1>Inboxes</h1></div></div>
      <div className="figs">
        <Fig value={healthy} unit={`of ${data.mailboxes.length}`} label="Mailboxes able to send" />
        <Fig value={data.capacity} label="Emails a day, at today's limits" />
        <Fig value={scheduled} label="Scheduled, next 14 days" />
        {paused.length ? <Fig value={paused.length} label="Play steps paused" /> : null}
      </div>
      <Section title="Domains">
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: D_COLS }}><span>Domain</span><span>Authentication</span><span className="num">Age</span><span className="num">Spam rate</span><span className="num">Mailboxes</span></div>
          {data.domains.map((d: any) => {
            const auth = d.spf && d.dkim && d.dmarc && d.dmarc_aligned;
            return (
              <div key={d.domain} className="row" style={{ gridTemplateColumns: D_COLS }}>
                <div className="cell-main"><span className="t">{d.domain}</span><span className="s">{d.dmarc_policy ? `DMARC ${d.dmarc_policy}` : "No DMARC policy"}{d.blocklisted ? ", on a blocklist" : ""}{d.checked_at ? `, DNS read ${ago(d.checked_at)}` : ", DNS not read yet"}</span></div>
                <Status kind={auth ? "ok" : "stop"}>{auth ? "SPF, DKIM, DMARC aligned" : `${[!d.spf && "SPF", !d.dkim && "DKIM", !d.dmarc && "DMARC", d.dmarc && !d.dmarc_aligned && "alignment"].filter(Boolean).join(", ")} failing`}</Status>
                <span className="num">{d.age_days} days</span>
                <span className="num">{d.spam_rate === null ? <span className="mute">Not reported yet</span> : pct(d.spam_rate, 2)}</span>
                <span className="num">{d.mailboxes}</span>
              </div>
            );
          })}
        </div>
      </Section>
      <Section title="Mailboxes">
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: isManager ? M_COLS_ADMIN : M_COLS }}><span>Mailbox</span><span>Status</span><span className="num">Today</span><span className="num">Sent, 14 days</span><span className="num">Bounced</span>{isManager ? <span /> : null}</div>
          {data.mailboxes.map((m: any) => (
            <div key={m.id} className="row" style={{ gridTemplateColumns: isManager ? M_COLS_ADMIN : M_COLS }}>
              <div className="cell-main"><span className="t">{m.address}</span><span className="s">{m.owner}, {cap(m.provider)}</span></div>
              <Status kind={m.blocked ? (m.status === "paused" ? "stop" : "wait") : "ok"}>{m.blocked || "Sending"}</Status>
              <span className="num">{m.today} <span className="faint">of {m.cap}</span></span>
              <span className="num">{m.sent}</span>
              <span className="num">{m.sent ? pct(m.bounced / m.sent, 1) : ""}</span>
              {isManager ? <MailboxActions m={m} onDone={reload} /> : null}
            </div>
          ))}
        </div>
        {isManager ? <AddSending domains={data.domains} onDone={reload} /> : null}
      </Section>
      <Section title="Where mail lands">
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: P_COLS }}><span>Mailbox</span><span>Gmail inbox</span><span>Outlook inbox</span><span className="num hide-sm">Tested</span></div>
          {data.mailboxes.map((m: any) => (
            <div key={m.id} className="row" style={{ gridTemplateColumns: P_COLS }}>
              <div className="cell-main"><span className="t">{m.address}</span><span className="s only-sm">{m.placement_at ? `Tested ${ago(m.placement_at)}` : "Not tested yet"}</span></div>
              {["gmail", "outlook"].map((p) => <Inbox key={p} r={m.placement[p]} t={data.placement} />)}
              <span className="num mute small hide-sm">{m.placement_at ? ago(m.placement_at) : "Not yet"}</span>
            </div>
          ))}
        </div>
      </Section>
      {data.watch.length ? (
        <Section title="First 20 sends of each email step">
          <div className="ledger">
            {data.watch.slice(0, 16).map((w: any) => (
              <div key={w.template_key} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 90px 90px 160px" }}>
                <span className="clip">{w.play}, email {w.step}</span>
                <span className="num">{Math.min(w.sends, 20)} <span className="faint">of 20</span></span>
                <span className="num">{w.hard_bounces} bounced</span>
                {w.paused ? <ResumeStep w={w} /> : <Status kind={w.sends >= 20 ? "ok" : "half"}>{w.sends >= 20 ? "Past the first batch" : "Watching"}</Status>}
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
/** One provider's seed result: the inbox share, flagged only when it holds or pauses the mailbox. */
function Inbox({ r, t }: { r: any; t: { placement_hold_below: number; placement_pause_below: number } }) {
  if (!r) return <span className="mute">Not tested</span>;
  const rate = r.inbox / r.seeds;
  const title = `${r.inbox} inbox, ${r.spam} spam, ${r.missing} missing, of ${r.seeds} seed inboxes`;
  if (rate < t.placement_pause_below) return <span title={title}><Status kind="stop">{pct(rate, 0)}</Status></span>;
  if (rate < t.placement_hold_below) return <span title={title}><Status kind="hold">{pct(rate, 0)}</Status></span>;
  return <span title={title}><Status kind="ok">{pct(rate, 0)}</Status></span>;
}

const C_COLS = "minmax(0,1fr) 120px minmax(0,1.3fr) 170px";
const P_COLS = "minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr) 110px";
const D_COLS = "minmax(0,1.4fr) minmax(0,1.4fr) 64px 90px 90px";
const M_COLS = "minmax(0,1.6fr) minmax(0,1.4fr) 90px 90px 80px";
const M_COLS_ADMIN = "minmax(0,1.6fr) minmax(0,1.4fr) 90px 90px 80px 96px";

/** Pause, resume or retire a mailbox. Resuming one the desk paused is a person's call after checking why. */
function MailboxActions({ m, onDone }: { m: any; onDone: () => void }) {
  const [busy, run] = useBusy();
  const set = (status: string, reason: string | null, msg: string) => run(async () => {
    await api(`/api/mailboxes/${m.id}`, { method: "PATCH", body: { status, reason } }); onDone();
  }, msg);
  if (m.status === "retired") return <span className="mute small">Retired</span>;
  return (
    <span className="actions" style={{ justifyContent: "flex-end" }}>
      {m.status === "paused"
        ? <button className="btn line sm" disabled={busy} title={m.pause_reason || undefined} onClick={() => set("active", null, "Resumed.")}>Resume</button>
        : <button className="btn quiet sm" disabled={busy} onClick={() => set("paused", "Paused by a manager", "Paused.")}>Pause</button>}
    </span>
  );
}

/** A new sending domain (unauthenticated until the DNS check reads it) or a new mailbox for an SDR. */
function AddSending({ domains, onDone }: { domains: any[]; onDone: () => void }) {
  const team = useData<any>("/api/admin").data;
  const [open, setOpen] = useState<"" | "domain" | "mailbox">("");
  const [f, setF] = useState<any>({ domain: "", registered: "", address: "", user_id: "", provider: "google", warmup_started: "" });
  const [busy, run] = useBusy();
  if (!open) return (
    <div className="actions" style={{ marginTop: 10 }}>
      <button className="btn quiet sm" onClick={() => setOpen("domain")}>Add a domain</button>
      <button className="btn quiet sm" onClick={() => setOpen("mailbox")}>Add a mailbox</button>
    </div>
  );
  const done = () => { setOpen(""); onDone(); };
  return open === "domain" ? (
    <div className="actions" style={{ flexWrap: "wrap", marginTop: 10 }}>
      <input className="input" style={{ width: 220 }} placeholder="getyourcompany.com" value={f.domain} onChange={(e) => setF({ ...f, domain: e.target.value })} aria-label="Domain" />
      <label className="field"><span>Registered</span><input className="input" type="date" value={f.registered} onChange={(e) => setF({ ...f, registered: e.target.value })} /></label>
      <button className="btn quiet sm" onClick={() => setOpen("")}>Cancel</button>
      <button className="btn sm" disabled={busy || !f.domain || !f.registered} onClick={() => run(async () => {
        await api("/api/sending-domains", { method: "POST", body: { domain: f.domain, registered: f.registered } }); done();
      }, "Added. Nothing sends from it until its DNS records check out.")}>Add domain</button>
    </div>
  ) : (
    <div className="actions" style={{ flexWrap: "wrap", marginTop: 10 }}>
      <input className="input" style={{ width: 220 }} placeholder={`name@${domains[0]?.domain || "yourdomain.com"}`} value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} aria-label="Address" />
      <select className="select" style={{ width: 160 }} value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} aria-label="Whose">
        <option value="">Whose mailbox</option>
        {(team?.users || []).filter((x: any) => x.active && x.role === "sdr").map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
      <select className="select" style={{ width: 130 }} value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })} aria-label="Provider">
        <option value="google">Google</option><option value="microsoft">Microsoft</option>
      </select>
      <label className="field"><span>Warm-up began</span><input className="input" type="date" value={f.warmup_started} onChange={(e) => setF({ ...f, warmup_started: e.target.value })} /></label>
      <button className="btn quiet sm" onClick={() => setOpen("")}>Cancel</button>
      <button className="btn sm" disabled={busy || !f.address || !f.user_id || !f.warmup_started} onClick={() => run(async () => {
        await api("/api/mailboxes", { method: "POST", body: { address: f.address, user_id: Number(f.user_id), provider: f.provider, warmup_started: f.warmup_started } }); done();
      }, "Added. A seed test runs now.")}>Add mailbox</button>
    </div>
  );
}

// ---------------------------------------------------------------- Results

export function Results() {
  const { data, error, reload } = useData<any>("/api/results");
  const me = useData<any>("/api/me").data;
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Results</h1></div><Loading /></div>;
  const f = data.funnel;
  const of = Math.max(1, f.proposed);
  const labels = data.labels.filter((l: any) => l.label !== "bounce");
  const lmax = Math.max(1, ...labels.map((l: any) => l.n));
  return (
    <div className="page">
      <div className="head"><div><h1>Results</h1></div></div>
      <div className="figs">
        <Fig value={data.opportunities.sourced} label="Opportunities sourced" />
        {me?.money ? <Fig value={money(data.opportunities.sourced_cents)} label="Pipeline sourced" /> : null}
        <Fig value={data.sla.median_hours ? `${data.sla.median_hours.toFixed(1)} h` : "None yet"} label="Median time to answer a hot reply" />
        {me?.money && data.cost_per_meeting_cents ? <Fig value={money(data.cost_per_meeting_cents)} label="Data and AI spend per meeting, this month" /> : null}
      </div>
      <div>
        <Section title="From signal to meeting">
          <div className="funnel">
            <Bar label="Offered to an SDR" value={f.proposed} of={of} />
            <Bar label="Accepted" value={f.accepted} of={of} hint={pct(f.accepted / of)} />
            <Bar label="Contacted" value={f.contacted} of={of} hint={pct(f.contacted / of)} />
            <Bar label="Replied" value={f.replied} of={of} hint={pct(f.replied / of)} />
            <Bar label="Positive reply" value={f.positive} of={of} hint={pct(f.positive / of)} tone="accent" />
            <Bar label="Meeting from outbound" value={f.meetings} of={of} hint={pct(f.meetings / of)} tone="accent" />
          </div>
        </Section>
      </div>
      <Section title="Contacted against held back">
        <Comparison rows={[["Meeting within 60 days", data.lift], ["Deal within 90 days", data.deal_lift]]} />
      </Section>
      <Section title="By channel, last 90 days">
        {data.channels.length ? (
          <div className="ledger">
            <div className="row head" style={{ gridTemplateColumns: C_COLS }}><span>Channel</span><span className="num">People reached</span><span className="num">Responded</span><span className="num hide-sm">Meeting within 60 days</span></div>
            {data.channels.map((c: any) => {
              const answered = c.channel === "linkedin" ? c.accepted : c.channel === "call" ? c.spoke : c.replied;
              const word = c.channel === "linkedin" ? "accepted" : c.channel === "call" ? "spoke" : "replied";
              return (
                <div key={c.channel} className="row" style={{ gridTemplateColumns: C_COLS }}>
                  <span className="sig-label"><span className="sig-icon">{c.channel === "linkedin" ? <LinkedinLogo size={15} /> : c.channel === "call" ? <Phone size={15} /> : <EnvelopeSimple size={15} />}</span>{c.channel === "linkedin" ? "LinkedIn" : c.channel === "call" ? "Calls" : "Email"}</span>
                  <span className="num">{n0(c.reached)}</span>
                  <span className="num">{pct(answered / c.reached, 0)} <span className="mute small">{word}{c.channel === "linkedin" && c.replied ? `, ${pct(c.replied / c.reached, 0)} replied` : ""}</span></span>
                  <span className="num hide-sm">{n0(c.meetings)} <span className="mute small">{pct(c.meetings / c.reached, 1)}</span></span>
                </div>
              );
            })}
          </div>
        ) : <Empty title="Nobody reached yet" />}
      </Section>
      <Section title="Which signals turn into meetings">
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: "minmax(0,1.4fr) 110px minmax(160px,1.6fr)" }}><span>Signal</span><span className="num">Plays started</span><span>Meetings within 60 days</span></div>
          {data.signals.filter((s: any) => s.treated > 0).sort((a: any, b: any) => (b.meeting_rate || 0) - (a.meeting_rate || 0)).map((s: any) => (
            <div key={s.key} className="row" style={{ gridTemplateColumns: "minmax(0,1.4fr) 110px minmax(160px,1.6fr)" }}>
              <span className="clip"><SignalLabel type={s.key} label={s.label} /></span>
              <span className="num">{s.treated}</span>
              <Bar label="" value={s.meeting_rate || 0} of={Math.max(0.0001, ...data.signals.map((x: any) => x.meeting_rate || 0))} shown={pct(s.meeting_rate)} hint={`${s.treated_meetings} of ${s.treated}`} />
            </div>
          ))}
        </div>
      </Section>
      <Section title="What replies said">
        <div className="bars" style={{ maxWidth: 720 }}>
          {labels.map((l: any) => <Bar key={l.label} label={(LABEL[l.label] || LABEL.other)[1]} value={l.n} of={lmax} />)}
        </div>
      </Section>
      <Section title="What buyers said on calls" count={new Set(data.learnings.map((l: any) => l.kind + l.text)).size}>
        {data.learnings.length ? (
          <div className="three">
            {([["reason_to_buy", "Why they'd buy"], ["objection", "What's holding them back"], ["competitor", "Other tools they named"]] as const).map(([kind, title]) => {
              const rows = data.learnings.filter((l: any) => l.kind === kind);
              return (
                <div key={kind} className="callcol">
                  <h3>{title}</h3>
                  {rows.length ? (
                    <ul className="scrolly">
                      {rows.map((l: any) => (
                        <li key={l.text} className="said">
                          <div className="said-top">
                            <span className="said-text">{kind === "competitor" ? l.text : <><span className="qmark" aria-hidden="true">&ldquo;</span>{l.text}</>}</span>
                            <span className="num said-n">{l.calls} {l.calls === 1 ? "call" : "calls"}</span>
                          </div>
                          {kind === "competitor" ? <div className="said-quote"><span className="qmark" aria-hidden="true">&ldquo;</span>{l.quote}</div> : null}
                          <div className="said-meta">{names(l.companies)}</div>
                        </li>
                      ))}
                    </ul>
                  ) : <Empty title="Nothing yet" />}
                </div>
              );
            })}
          </div>
        ) : <Empty title="No call notes yet">After a meeting, the SDR adds their notes and marks what is worth learning from.</Empty>}
      </Section>
      {me?.money && data.spend ? (
        <Section title="Spend this month">
          <div className="ledger">
            {data.spend.map((s: any) => (
              <div key={s.vendor + s.unit} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 160px 100px" }}>
                <span>{VENDOR_NAME[s.vendor] || cap(s.vendor)}</span>
                <span className="num">{n0(s.qty)} {s.unit}</span>
                <span className="num strong">{money(s.cost_cents)}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}

function names(list: string[]): string {
  if (!list?.length) return "";
  if (list.length <= 2) return list.join(" and ");
  return `${list.slice(0, 2).join(", ")} and ${list.length - 2} more`;
}

// ---------------------------------------------------------------- Ops (health)

export function Ops() {
  const { data, error, reload } = useData<any>("/api/ops");
  const [busy, run] = useBusy();
  const [reason, setReason] = useState("");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Health</h1></div><Loading /></div>;
  const failing = data.monitors.filter((m: any) => !m.ok);
  return (
    <div className="page">
      <div className="head">
        <div><h1>Health</h1></div>
        <div className="actions">
          <input className="input" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" style={{ width: 180 }} />
          <button className={data.kill_switch ? "btn" : "btn ink"} disabled={busy || reason.trim().length < 3}
            onClick={() => run(() => api("/api/kill-switch", { method: "POST", body: { on: !data.kill_switch, reason } }), data.kill_switch ? "Sending is back on." : "All sending stopped.").then(() => setReason(""))}>
            {data.kill_switch ? "Turn sending back on" : "Stop all sending"}
          </button>
        </div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={data.kill_switch ? "stop" : "ok"}>{data.kill_switch ? "Stopped" : "On"}</Status>} label="Sending" sm />
        <Fig value={failing.length} unit={`of ${data.monitors.length}`} label="Checks finding problems" />
        <Fig value={data.alerts.filter((a: any) => !a.delivered_at).length} label="Alerts not delivered" />
        <Fig value={<Status kind={data.checks_stale ? "stop" : "ok"}>{data.checks_ran_at ? ago(data.checks_ran_at) : "Never"}</Status>} label={data.checks_stale ? "Checks stopped running" : "Checks last ran"} sm />
      </div>
      <Section title="Checks">
        <div className="ledger">
          {data.monitors.map((m: any) => (
            <div key={m.monitor} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 120px 100px" }}>
              <Status kind={m.error ? "wait" : m.ok ? "ok" : "stop"}>{m.title}</Status>
              <span className="num">{m.error ? "Did not run" : m.monitor === "monitors_ran" ? (m.ok ? "All ran" : `${m.found} failed`) : m.ok ? "None found" : `${m.found} found`}</span>
              <span className="num mute small">{ago(m.at)}</span>
            </div>
          ))}
        </div>
      </Section>
      <div className="two">
        <Section title="Spend against monthly caps">
          <div className="bars">
            {data.budgets.map((b: any) => <Bar key={b.vendor} label={VENDOR_NAME[b.vendor] || cap(b.vendor)} value={Number(b.used)} of={Number(b.cap)}
              shown={b.vendor === "anthropic" ? `$${n0(Number(b.used) / 100)}` : n0(b.used)} hint={b.vendor === "anthropic" ? `of $${n0(Number(b.cap) / 100)}` : `of ${n0(b.cap)} credits`} />)}
          </div>
        </Section>
        <Section title="Background work">
          {data.jobs.length ? (
            <div className="ledger">{data.jobs.map((j: any) => (
              <div key={j.kind + j.status} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 100px 60px" }}>
                <span>{JOB[j.kind] || cap(j.kind.replace(/_/g, " "))}</span><Status kind={j.status === "dead" ? "stop" : j.status === "queued" ? "half" : "go"}>{JOB_STATUS[j.status] || cap(j.status)}</Status><span className="num">{j.n}</span>
              </div>))}
            </div>
          ) : <Empty title="Nothing waiting" />}
        </Section>
      </div>
      <Section title="Alerts">
        <div className="ledger">
          {data.alerts.map((a: any) => (
            <div key={a.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 150px 120px 80px" }}>
              <div className="cell-main"><span className="t">{a.title}</span><span className="s">{a.body}</span></div>
              <span className="mute small clip">{a.channel}</span>
              <Status kind={a.delivered_at ? "ok" : "wait"}>{a.delivered_at ? "Delivered" : "Not delivered"}</Status>
              <span className="num mute small">{ago(a.at)}</span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------- Settings

function ResumeStep({ w }: { w: any }) {
  const [busy, run] = useBusy();
  return (
    <span className="actions" style={{ justifyContent: "flex-end" }}>
      <Status kind="stop">Paused</Status>
      <button className="btn line sm" disabled={busy} onClick={() => run(() => api(`/api/watch/${encodeURIComponent(w.template_key)}/resume`, { method: "POST" }), "Resumed. The next 20 sends are watched again.")}>Resume</button>
    </span>
  );
}

function AddSuppression({ onDone }: { onDone: () => void }) {
  const [kind, setKind] = useState("email");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [busy, run] = useBusy();
  return (
    <div className="actions" style={{ flexWrap: "wrap", marginBottom: 12 }}>
      <select className="select" style={{ width: 120 }} value={kind} onChange={(e) => setKind(e.target.value)} aria-label="What to block">
        <option value="email">Email</option><option value="domain">Domain</option><option value="phone">Phone</option>
      </select>
      <input className="input" style={{ flex: 1, minWidth: 180 }} value={value} onChange={(e) => setValue(e.target.value)} placeholder={kind === "domain" ? "company.com" : kind === "phone" ? "+1 555 0100" : "name@company.com"} aria-label="Value" />
      <input className="input" style={{ flex: 1, minWidth: 180 }} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why" aria-label="Why" />
      <button className="btn sm" disabled={busy || !value.trim() || reason.trim().length < 3} onClick={() => run(async () => {
        await api("/api/suppressions", { method: "POST", body: { kind, value, reason } });
        setValue(""); setReason(""); onDone();
      }, "Added. Their sequences stop now.")}>Add</button>
    </div>
  );
}

function LiftButton({ id, onDone }: { id: number; onDone: () => void }) {
  const [busy, run] = useBusy();
  return <button className="btn quiet sm" disabled={busy} onClick={() => run(async () => { await api(`/api/suppressions/${id}`, { method: "DELETE" }); onDone(); }, "Lifted.")}>Lift</button>;
}

const ROLE: Record<string, string> = { sdr: "SDR", manager: "Manager", gtm: "GTM engineering" };

/** The team: who is on the desk and in what role. Someone who leaves hands their accounts and work to a successor. */
function Team() {
  const { data, reload } = useData<any>("/api/admin");
  const [busy, run] = useBusy();
  const [leaving, setLeaving] = useState<number | null>(null);
  const [successor, setSuccessor] = useState("");
  const [nu, setNu] = useState({ name: "", email: "", role: "sdr" });
  if (!data) return null;
  const sdrs = data.users.filter((x: any) => x.active && x.role === "sdr");
  return (
    <Section title="Team">
      <div className="ledger">
        {data.users.map((x: any) => (
          <div key={x.id} className="row" style={{ gridTemplateColumns: "minmax(0,1.4fr) 170px minmax(0,1fr)", minHeight: 44, opacity: x.active ? 1 : 0.55 }}>
            <div className="cell-main"><span className="t">{x.name}</span><span className="s">{x.email}{x.accounts ? `, ${n0(x.accounts)} accounts` : ""}{x.mailboxes ? `, ${x.mailboxes} mailboxes` : ""}</span></div>
            {x.active ? (
              <select className="select" value={x.role} disabled={busy} aria-label={`${x.name}'s role`}
                onChange={(e) => run(async () => { await api(`/api/users/${x.id}`, { method: "PATCH", body: { role: e.target.value } }); reload(); }, "Role changed.")}>
                {Object.entries(ROLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            ) : <span className="mute">Left the desk</span>}
            {!x.active ? <span /> : leaving === x.id ? (
              <span className="actions" style={{ flexWrap: "wrap" }}>
                <select className="select" style={{ width: 170 }} value={successor} onChange={(e) => setSuccessor(e.target.value)} aria-label="Hand their work to">
                  <option value="">Hand their work to</option>
                  {sdrs.filter((s: any) => s.id !== x.id).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <button className="btn quiet sm" onClick={() => setLeaving(null)}>Cancel</button>
                <button className="btn ink sm" disabled={busy} onClick={() => run(async () => {
                  await api(`/api/users/${x.id}`, { method: "PATCH", body: { deactivate: true, successor: successor ? Number(successor) : null } });
                  setLeaving(null); reload();
                }, "Done. Their sign-in stopped and their work moved.")}>Remove</button>
              </span>
            ) : <span className="actions" style={{ justifyContent: "flex-end" }}><button className="btn quiet sm" onClick={() => { setLeaving(x.id); setSuccessor(""); }}>Remove from the desk</button></span>}
          </div>
        ))}
      </div>
      <div className="actions" style={{ flexWrap: "wrap", marginTop: 12 }}>
        <input className="input" style={{ flex: 1, minWidth: 150 }} placeholder="Name" value={nu.name} onChange={(e) => setNu({ ...nu, name: e.target.value })} aria-label="Name" />
        <input className="input" style={{ flex: 1, minWidth: 190 }} placeholder="Work email" value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} aria-label="Work email" />
        <select className="select" style={{ width: 170 }} value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })} aria-label="Role">
          {Object.entries(ROLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <button className="btn sm" disabled={busy || nu.name.trim().length < 2 || !nu.email.includes("@")} onClick={() => run(async () => {
          await api("/api/users", { method: "POST", body: nu }); setNu({ name: "", email: "", role: "sdr" }); reload();
        }, "Added. They sign in with that email.")}>Add</button>
      </div>
    </Section>
  );
}

/** The ideal customer profile. GTM edits weights, values and tier lines; publishing makes a new version and
 *  rescores every account. A field the desk does not know about an account is left out of its score. */
function IcpSection({ icp, canEdit, onDone }: { icp: any; canEdit: boolean; onDone: () => void }) {
  const [draft, setDraft] = useState<any>(null);
  const [note, setNote] = useState("");
  const [busy, run] = useBusy();
  const r = draft || icp.rules;
  const setFactor = (i: number, patch: any) => setDraft({ ...r, factors: r.factors.map((f: any, j: number) => (j === i ? { ...f, ...patch } : f)) });
  const show = (f: any) => (f.op === "between" ? `${f.value[0]} to ${f.value[1]}` : f.value.join(", "));
  const parse = (f: any, text: string) => (f.op === "between" ? text.split(/\s*(?:to|-|,)\s*/).map((x) => Number(x) || 0).slice(0, 2)
    : text.split(",").map((x) => x.trim()).filter(Boolean));
  return (
    <Section title="Ideal customer profile" right={canEdit && !draft ? <button className="btn quiet sm" onClick={() => setDraft(JSON.parse(JSON.stringify(icp.rules)))}>Edit</button> : null}>
      <div className="ledger">
        {r.factors.map((f: any, i: number) => (
          <div key={f.key} className="row" style={{ gridTemplateColumns: "140px minmax(0,1fr) 72px", minHeight: 36 }}>
            <span className="strong">{cap(f.key)}</span>
            {draft ? <input className="input" defaultValue={show(f)} aria-label={`${f.key} values`} onBlur={(e) => setFactor(i, { value: parse(f, e.target.value) })} />
              : <span className="mute clip">{show(f)}</span>}
            {draft ? <input className="input num" inputMode="numeric" value={f.weight} aria-label={`${f.key} weight`} onChange={(e) => setFactor(i, { weight: Math.min(100, Number(e.target.value) || 0) })} />
              : <span className="num">{f.weight}</span>}
          </div>
        ))}
      </div>
      {draft ? (
        <>
          <div className="form-row">
            <label className="field"><span>Tier A from</span><input className="input num" inputMode="numeric" value={r.tiers.A} onChange={(e) => setDraft({ ...r, tiers: { ...r.tiers, A: Number(e.target.value) || 0 } })} /></label>
            <label className="field"><span>Tier B from</span><input className="input num" inputMode="numeric" value={r.tiers.B} onChange={(e) => setDraft({ ...r, tiers: { ...r.tiers, B: Number(e.target.value) || 0 } })} /></label>
            <label className="field" style={{ flex: 2 }}><span>What changed and why</span><input className="input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} /></label>
          </div>
          <div className="actions" style={{ justifyContent: "flex-end" }}>
            <button className="btn quiet sm" onClick={() => { setDraft(null); setNote(""); }}>Cancel</button>
            <button className="btn sm" disabled={busy || note.trim().length < 3} onClick={() => run(async () => {
              await api("/api/icp", { method: "PUT", body: { ...r, note } });
              setDraft(null); setNote(""); onDone();
            }, "Published. Every account is rescored now.")}>Publish</button>
          </div>
        </>
      ) : <div className="small mute">Tier A from {r.tiers.A}, tier B from {r.tiers.B}. Published {day(icp.published_at)}.</div>}
    </Section>
  );
}

/** Accounts and people from a CSV. Rows the desk refuses come back with the reason, row by row. */
function ImportBox() {
  const [kind, setKind] = useState<"accounts" | "people">("accounts");
  const [result, setResult] = useState<any>(null);
  const [busy, run] = useBusy();
  const pick = (file: File | undefined) => {
    if (!file) return;
    run(async () => {
      const csv = await file.text();
      setResult(await api<any>(`/api/import/${kind}`, { method: "POST", body: { csv } }));
    });
  };
  return (
    <Section title="Bring your data" right={<span className="mute small">CSV. Accounts first, then people.</span>}>
      <div className="actions" style={{ flexWrap: "wrap" }}>
        <select className="select" style={{ width: 160 }} value={kind} onChange={(e) => setKind(e.target.value as any)} aria-label="What to import">
          <option value="accounts">Accounts</option><option value="people">People</option>
        </select>
        <label className="btn line sm" style={{ cursor: "pointer" }}>
          Choose a file<input type="file" accept=".csv,text/csv" className="sr-only" disabled={busy} onChange={(e) => pick(e.target.files?.[0])} />
        </label>
        <a className="btn quiet sm" download={`${kind}-template.csv`}
          href={`data:text/csv;charset=utf-8,${encodeURIComponent(kind === "accounts"
            ? "name,domain,industry,employees,country,revenue_band,tech,lifecycle,owner_email,crm_id,parent_domain\n"
            : "full_name,company_domain,title,email,linkedin_url,phone,country,timezone\n")}`}>Template</a>
      </div>
      {result ? (
        <div className="ledger" style={{ marginTop: 12 }}>
          <div className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}><Status kind="ok">{n0(result.imported)} imported</Status></div>
          {result.refused.slice(0, 20).map((r: any) => (
            <div key={r.row} className="row" style={{ gridTemplateColumns: "80px minmax(0,1fr)" }}><span className="mute">Row {r.row}</span><Status kind="stop">{r.why}</Status></div>
          ))}
          {result.refused.length > 20 ? <div className="row mute small">and {result.refused.length - 20} more refused</div> : null}
        </div>
      ) : null}
    </Section>
  );
}

export function Settings() {
  const { data, error, reload } = useData<any>("/api/settings");
  const me = useData<any>("/api/me").data;
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Settings</h1></div><Loading /></div>;
  const s = data.settings;
  const canEdit = me?.user.role === "gtm";
  return (
    <div className="page">
      <div className="head"><div><h1>Settings</h1></div></div>
      <Section title="Signals and their weight">
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: W_COLS }}><span>Signal</span><span className="num">Weight</span><span className="num">Counts half after, days</span><span>On</span></div>
          {data.signal_types.map((t: any) => <WeightRow key={t.key} t={t} canEdit={canEdit} />)}
        </div>
      </Section>
      <div className="two">
        <Section title="Limits">
          <dl className="kv">
            <dt>People per account</dt><dd>{s.account_max_active} at once, {s.account_max_active_wide} for tier A</dd>
            <dt>Rest after an email</dt><dd>{s.person_cooldown_days} days before another play</dd>
            <dt>After any reply</dt><dd>Account waits {s.account_reply_pause_hours} hours for an answer</dd>
            <dt>Re-check an email older than</dt><dd>{s.verify_max_age_days} days</dd>
            <dt>Send hours</dt><dd>{s.send_window.map((w: string[]) => w.join(" to ")).join(", ")}, their time</dd>
            <dt>Per mailbox</dt><dd>Up to {s.mailbox_max_daily} a day, ramped</dd>
            <dt>Hot reply answer</dt><dd>Within {s.sla_business_hours} business hours</dd>
            <dt>Proposal open for</dt><dd>{s.proposal_ttl_days} business days, {s.urgent_proposal_ttl_days} for urgent plays</dd>
          </dl>
        </Section>
        <Section title="Countries">
          <div className="ledger">
            {data.regions.map((r: any) => (
              <div key={r.country} className="row" style={{ gridTemplateColumns: "48px minmax(0,1fr)", minHeight: 36 }}>
                <span className="strong">{r.country}</span>
                <span className="mute">{r.rule === "allowed" ? "Email allowed" : r.rule === "basis_required" ? "Needs a recorded legitimate interest" : r.rule === "consent_required" ? "Needs consent before a cold email" : "Not emailed"}</span>
              </div>
            ))}
          </div>
          <div className="small mute">A starting point. Counsel to confirm.</div>
        </Section>
      </div>
      {me?.user.role === "manager" ? <Team /> : null}
      <IcpSection icp={data.icp} canEdit={canEdit} onDone={reload} />
      {me && me.user.role !== "sdr" ? <ImportBox /> : null}
      <Section title="Do not contact">
        <AddSuppression onDone={reload} />
        {data.suppressions.length ? (
          <div className="ledger">
            {data.suppressions.slice(0, 20).map((x: any) => (
              <div key={x.id} className="row" style={{ gridTemplateColumns: "100px minmax(0,1fr) minmax(0,1fr) 90px 70px", minHeight: 36 }}>
                <span className="mute">{cap(x.kind === "email_hash" ? "erased" : x.kind)}</span>
                <span className="clip">{x.kind === "email_hash" ? "Address kept only as a fingerprint" : x.value}</span>
                <span className="mute clip">{x.reason}</span>
                <span className="num mute small">{day(x.created_at)}</span>
                {me?.user.role === "manager" && String(x.source).startsWith("person:") ? <LiftButton id={x.id} onDone={reload} /> : <span />}
              </div>
            ))}
          </div>
        ) : <Empty title="Nobody yet" />}
      </Section>
    </div>
  );
}
const JOB: Record<string, string> = {
  send_due: "Sending scheduled emails", send_provider: "Handing emails to the mail provider", due_steps: "Moving sequences to their next step",
  draft_step: "Drafting emails", research: "Researching accounts", rescore: "Rescoring an account", rescore_all: "Nightly rescoring",
  rescore_batch: "Rescoring a batch of accounts", classify_reply: "Reading replies", resume: "Resuming after an out-of-office",
  resume_after_positive: "Resuming colleagues after a positive reply", sla_check: "Checking reply answer times",
  crm_push: "Writing to the CRM", crm_sync: "Reading the CRM", mailbox_health: "Checking mailbox health",
  telemetry: "Reading spam rates", placement_tests: "Testing where mail lands", dns_check: "Checking DNS records",
  monitors: "Running the checks", ingest_source: "Collecting signals", deliver_alert: "Sending alerts to Slack",
  expire_proposals: "Expiring old proposals", close_stale_plays: "Closing plays that ran their course",
  autonomy_watch: "Watching autonomy", watch_reset: "Resetting first-batch watches", sweep_sending: "Settling stuck sends",
  reverify: "Re-checking an email", enroll_referral: "Enrolling a referred person", replace_person: "Finding a replacement",
};
const JOB_STATUS: Record<string, string> = { queued: "Waiting", running: "Running", failed: "Will retry", dead: "Gave up" };

const W_COLS = "minmax(0,1.6fr) 90px 120px 60px";

function WeightRow({ t, canEdit }: { t: any; canEdit: boolean }) {
  const [w, setW] = useState(String(Number(t.weight)));
  const [h, setH] = useState(String(Number(t.half_life_days)));
  const [busy, run] = useBusy();
  const dirty = w !== String(Number(t.weight)) || h !== String(Number(t.half_life_days));
  const save = (enabled = t.enabled) => run(() => api(`/api/signal-types/${t.key}`, { method: "POST", body: { weight: Number(w), half_life_days: Number(h), enabled } }), "Saved. Scores update shortly.");
  return (
    <div className="row" style={{ gridTemplateColumns: W_COLS }}>
      <div className="cell-main" title={t.because}><span className="t"><SignalLabel type={t.key} label={t.label} /></span></div>
      {canEdit ? <input className="input num" style={{ width: 80, justifySelf: "end" }} value={w} onChange={(e) => setW(e.target.value)} onBlur={() => dirty && save()} aria-label={`Weight for ${t.label}`} inputMode="decimal" /> : <span className="num" data-label="Weight">{Number(t.weight)}</span>}
      {canEdit ? <input className="input num" style={{ width: 80, justifySelf: "end" }} value={h} onChange={(e) => setH(e.target.value)} onBlur={() => dirty && save()} aria-label={`Half-life for ${t.label}`} inputMode="decimal" /> : <span className="num" data-label="Counts half after">{Number(t.half_life_days)}</span>}
      <input type="checkbox" checked={t.enabled} disabled={!canEdit || busy} onChange={(e) => save(e.target.checked)} aria-label={`${t.label} on`} style={{ width: 18, height: 18, accentColor: "var(--accent)" }} />
    </div>
  );
}

export { openSheet };
