import { useState } from "react";
import { EnvelopeSimple, LinkedinLogo, Phone } from "@phosphor-icons/react";
import { api } from "../api";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Status, ago, cap, day, money, n0, pct, useBusy, useData,
} from "../lib";
import { LABEL, LiftBlock, openSheet } from "../sheets";
import { SignalLabel } from "../signalIcons";

// ---------------------------------------------------------------- Deliverability

export function Deliverability() {
  const { data, error, reload } = useData<any>("/api/deliverability");
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
                <div className="cell-main"><span className="t">{d.domain}</span><span className="s">DMARC {d.dmarc_policy}{d.blocklisted ? ", on a blocklist" : ""}</span></div>
                <Status kind={auth ? "ok" : "stop"}>{auth ? "SPF, DKIM, DMARC aligned" : "Incomplete"}</Status>
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
          <div className="row head" style={{ gridTemplateColumns: M_COLS }}><span>Mailbox</span><span>Status</span><span className="num">Today</span><span className="num">Sent, 14 days</span><span className="num">Bounced</span></div>
          {data.mailboxes.map((m: any) => (
            <div key={m.id} className="row" style={{ gridTemplateColumns: M_COLS }}>
              <div className="cell-main"><span className="t">{m.address}</span><span className="s">{m.owner}, {cap(m.provider)}</span></div>
              <Status kind={m.blocked ? (m.status === "paused" ? "stop" : "wait") : "ok"}>{m.blocked || "Sending"}</Status>
              <span className="num">{m.today} <span className="faint">of {m.cap}</span></span>
              <span className="num">{m.sent}</span>
              <span className="num">{m.sent ? pct(m.bounced / m.sent, 1) : ""}</span>
            </div>
          ))}
        </div>
      </Section>
      <Section title="Where mail lands" right={<span className="mute small">Seed tests, weekly. Under {pct(data.placement.placement_hold_below, 0)} holds a mailbox at 10 a day, under {pct(data.placement.placement_pause_below, 0)} pauses it.</span>}>
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: P_COLS }}><span>Mailbox</span><span>Gmail</span><span>Outlook</span><span className="num hide-sm">Tested</span></div>
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
                <Status kind={w.paused ? "stop" : w.sends >= 20 ? "ok" : "half"}>{w.paused ? "Paused" : w.sends >= 20 ? "Past the first batch" : "Watching"}</Status>
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
  if (rate < t.placement_pause_below) return <span title={title}><Status kind="stop">{pct(rate, 0)} inbox</Status></span>;
  if (rate < t.placement_hold_below) return <span title={title}><Status kind="hold">{pct(rate, 0)} inbox</Status></span>;
  return <span title={title}><Status kind="ok">{pct(rate, 0)} inbox</Status></span>;
}

const C_COLS = "minmax(0,1fr) 120px minmax(0,1.3fr) 170px";
const P_COLS = "minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr) 110px";
const D_COLS = "minmax(0,1.4fr) minmax(0,1.4fr) 64px 90px 90px";
const M_COLS = "minmax(0,1.6fr) minmax(0,1.4fr) 90px 90px 80px";

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
      <div className="split">
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
        <div>
          <Section title="Meetings: contacted against held back"><LiftBlock lift={data.lift} /></Section>
          <Section title="Deals: contacted against held back"><LiftBlock lift={data.deal_lift} /></Section>
          <p className="mute small">Any meeting within 60 days or deal within 90, however it started, counted the same way in both groups. Held-back accounts still get inbound requests and deals sales opens on its own.</p>
        </div>
      </div>
      <Section title="By channel" right={<span className="mute small">Last 90 days. Someone reached on two channels counts in both.</span>}>
        {data.channels.length ? (
          <div className="ledger">
            <div className="row head" style={{ gridTemplateColumns: C_COLS }}><span>Channel</span><span className="num">People reached</span><span className="num">Answered there</span><span className="num hide-sm">Meetings within 30 days</span></div>
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
                          <div className="said-meta">{names(l.companies)}{l.plays?.length ? `, ${l.plays.join(" and ").toLowerCase()}` : ""}</div>
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
                <span>{cap(s.vendor)}</span>
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
            {data.budgets.map((b: any) => <Bar key={b.vendor} label={cap(b.vendor)} value={Number(b.used)} of={Number(b.cap)} shown={n0(b.used)} hint={`of ${n0(b.cap)} ${b.vendor === "anthropic" ? "cents" : "credits"}`} />)}
          </div>
        </Section>
        <Section title="Background work">
          {data.jobs.length ? (
            <div className="ledger">{data.jobs.map((j: any) => (
              <div key={j.kind + j.status} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 100px 60px" }}>
                <span>{cap(j.kind)}</span><Status kind={j.status === "dead" ? "stop" : j.status === "queued" ? "half" : "go"}>{cap(j.status)}</Status><span className="num">{j.n}</span>
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
          <div className="row head" style={{ gridTemplateColumns: W_COLS }}><span>Signal</span><span className="num">Weight</span><span className="num">Fades by half in, days</span><span>On</span></div>
          {data.signal_types.map((t: any) => <WeightRow key={t.key} t={t} canEdit={canEdit} />)}
        </div>
      </Section>
      <div className="two">
        <Section title="Limits">
          <dl className="kv">
            <dt>People per account</dt><dd>{s.account_max_active} at once, {s.account_max_active_wide} for tier A</dd>
            <dt>Rest after an email</dt><dd>{s.person_cooldown_days} days before another play</dd>
            <dt>After any reply</dt><dd>Account waits {s.account_reply_pause_hours} hours for an answer</dd>
            <dt>Email checked within</dt><dd>{s.verify_max_age_days} days of sending</dd>
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
          <div className="small mute">Legal rules per country are a starting point. Counsel to confirm.</div>
        </Section>
      </div>
      <Section title="Ideal customer profile">
        <div className="ledger">
          {data.icp.rules.factors.map((f: any) => (
            <div key={f.key} className="row" style={{ gridTemplateColumns: "140px minmax(0,1fr) 60px", minHeight: 36 }}>
              <span className="strong">{cap(f.key)}</span>
              <span className="mute clip">{Array.isArray(f.value) ? (f.op === "between" ? `${f.value[0]} to ${f.value[1]}` : f.value.join(", ")) : String(f.value)}</span>
              <span className="num">{f.weight}</span>
            </div>
          ))}
        </div>
        <div className="small mute">Tier A from {data.icp.rules.tiers.A}, tier B from {data.icp.rules.tiers.B}. Published {day(data.icp.published_at)}.</div>
      </Section>
      <Section title="Do not contact">
        {data.suppressions.length ? (
          <div className="ledger">
            {data.suppressions.slice(0, 20).map((x: any) => (
              <div key={x.id} className="row" style={{ gridTemplateColumns: "100px minmax(0,1fr) minmax(0,1fr) 90px", minHeight: 36 }}>
                <span className="mute">{cap(x.kind === "email_hash" ? "erased" : x.kind)}</span>
                <span className="clip">{x.kind === "email_hash" ? "Address kept only as a fingerprint" : x.value}</span>
                <span className="mute clip">{x.reason}</span>
                <span className="num mute small">{day(x.created_at)}</span>
              </div>
            ))}
          </div>
        ) : <Empty title="Nobody yet" />}
      </Section>
    </div>
  );
}
const W_COLS = "minmax(0,1.6fr) 90px 120px 60px";

function WeightRow({ t, canEdit }: { t: any; canEdit: boolean }) {
  const [w, setW] = useState(String(Number(t.weight)));
  const [h, setH] = useState(String(Number(t.half_life_days)));
  const [busy, run] = useBusy();
  const dirty = w !== String(Number(t.weight)) || h !== String(Number(t.half_life_days));
  const save = (enabled = t.enabled) => run(() => api(`/api/signal-types/${t.key}`, { method: "POST", body: { weight: Number(w), half_life_days: Number(h), enabled } }), "Saved. Scores update shortly.");
  return (
    <div className="row" style={{ gridTemplateColumns: W_COLS }}>
      <div className="cell-main"><span className="t"><SignalLabel type={t.key} label={t.label} /></span><span className="s" style={{ paddingLeft: 30 }}>{t.because}</span></div>
      {canEdit ? <input className="input num" style={{ width: 80, justifySelf: "end" }} value={w} onChange={(e) => setW(e.target.value)} onBlur={() => dirty && save()} aria-label={`Weight for ${t.label}`} inputMode="decimal" /> : <span className="num">{Number(t.weight)}</span>}
      {canEdit ? <input className="input num" style={{ width: 80, justifySelf: "end" }} value={h} onChange={(e) => setH(e.target.value)} onBlur={() => dirty && save()} aria-label={`Half-life for ${t.label}`} inputMode="decimal" /> : <span className="num">{Number(t.half_life_days)}</span>}
      <input type="checkbox" checked={t.enabled} disabled={!canEdit || busy} onChange={(e) => save(e.target.checked)} aria-label={`${t.label} on`} style={{ width: 18, height: 18, accentColor: "var(--accent)" }} />
    </div>
  );
}

export { openSheet };
