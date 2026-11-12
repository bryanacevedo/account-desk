import { useEffect, useState } from "react";
import { api } from "../api";
import { Avatar } from "../marks";
import { SIGNAL_NAME, SignalIcon, SignalLabel } from "../signalIcons";
import { ArrowSquareOut, Lightbulb } from "@phosphor-icons/react";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Seg, Status, ago, cap, n0, navigate, pct, usePath, useData,
  safeUrl, withParam, useBusy,
} from "../lib";
import { LABEL, STAGE, openSheet } from "../sheets";

// ---------------------------------------------------------------- Approvals

export function Approvals() {
  const { data, error, reload } = useData<any>("/api/today");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Approvals</h1></div><Loading /></div>;
  const failed = data.approvals.filter((m: any) => m.status === "failed_gate");
  const ready = data.approvals.filter((m: any) => m.status === "awaiting_approval");
  const list = (rows: any[]) => (
    <div className="ledger">
      <div className="row head" style={{ gridTemplateColumns: A_COLS }}><span /><span>To</span><span>Subject</span><span>Play</span><span className="num">Drafted</span></div>
      {rows.map((m: any) => (
        <button key={m.id} className="row" style={{ gridTemplateColumns: A_COLS }} onClick={() => openSheet("message", m.id)}>
          <Avatar name={m.full_name} photo={m.photo_url} />
          <div className="cell-main"><span className="t">{m.full_name}</span><span className="s">{m.title}, {m.company}</span><span className="s only-sm">{m.subject}</span></div>
          <div className="cell-main hide-sm"><span className="t" style={{ fontWeight: 450 }}>{m.subject}</span><span className="s">Email {m.email_no ?? m.step_index + 1}</span></div>
          <span className="clip mute hide-sm">{m.play}</span>
          <span className="num mute small">{ago(m.created_at)}</span>
        </button>
      ))}
    </div>
  );
  return (
    <div className="page">
      <div className="head"><div><h1>Approvals</h1></div></div>
      <Section title="Ready to approve">{ready.length ? list(ready) : <Empty title="Nothing waiting" />}</Section>
      {failed.length ? <Section title="Needs a rewrite">{list(failed)}</Section> : null}
    </div>
  );
}
const A_COLS = "28px minmax(0,1.2fr) minmax(0,1.6fr) minmax(0,1fr) 76px";

// ---------------------------------------------------------------- Replies

export function Replies() {
  const [, params] = usePath();
  const meRole = useData<any>("/api/me").data?.user.role;
  const view = (params.get("view") || (meRole && meRole !== "sdr" ? "all" : "mine")) as "mine" | "all" | "hot" | "needs_person";
  const { data, error, reload } = useData<any>(`/api/replies?view=${view}`);
  return (
    <div className="page">
      <div className="head"><div><h1>Replies</h1></div></div>
      <Seg label="Which replies" value={view} onChange={(v) => navigate(withParam("view", v), true)}
        options={[["mine", "Mine"], ["all", "Everyone"], ["hot", "Positive"], ["needs_person", "Needs a person"]]} />
      {error ? <Failed error={error} retry={reload} /> : !data ? <Loading rows={10} /> : !data.replies.length ? <Empty title="No replies here" /> : (
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: R_COLS }}><span /><span>From</span><span>What they said</span><span>Read as</span><span className="num">Received</span></div>
          {data.replies.map((r: any) => {
            const l = LABEL[r.label] || LABEL.other;
            return (
              <button key={r.id} className="row" style={{ gridTemplateColumns: R_COLS }} onClick={() => openSheet("reply", r.id)}>
                <Avatar name={r.full_name || r.company || "?"} photo={r.photo_url} />
                <div className="cell-main"><span className="t">{r.full_name || "Unknown sender"}</span><span className="s">{r.company || "No account matched"}</span><span className="s only-sm">{r.cleaned}</span></div>
                <span className="clip mute hide-sm">{r.cleaned}</span>
                <span className="hide-sm">{r.needs_review && !r.handled_at ? <Status kind="wait">Needs a person</Status> : <Status kind={l[0]}>{l[1]}</Status>}</span>
                <span className="num mute small hide-sm">{ago(r.received_at)}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
const R_COLS = "28px minmax(0,1.1fr) minmax(0,2fr) 160px 80px";

// ---------------------------------------------------------------- Signals

export function Signals() {
  const [, params] = usePath();
  const tab = params.get("tab") || "feed";
  const { data, error, reload } = useData<any>("/api/signals");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Signals</h1></div><Loading /></div>;
  const week = data.sources.reduce((s: number, x: any) => s + Number(x.week), 0);
  const unmatched = data.feed.filter((s: any) => s.status === "unmatched");
  const silent = data.sources.filter((s: any) => s.enabled && s.adapter !== "webhook" && (!s.last_run || Date.now() - new Date(s.last_run).getTime() > 1e15)).length;
  return (
    <div className="page">
      <div className="head"><div><h1>Signals</h1></div></div>
      <div className="figs">
        <Fig value={n0(week)} label="Signals in the last 7 days" />
        <Fig value={data.sources.filter((s: any) => s.enabled).length} label="Sources" />
        {silent ? <Fig value={silent} label="Sources silent" /> : null}
      </div>
      <Seg label="View" value={tab} onChange={(v) => navigate(withParam("tab", v === "feed" ? null : v), true)}
        options={[["feed", "Latest"], ["types", "Which signals work"], ["sources", "Sources"], ["unmatched", unmatched.length ? `Not matched ${unmatched.length}` : "Not matched"]]} />
      {tab === "feed" && <Feed rows={data.feed.filter((s: any) => s.status === "matched")} />}
      {tab === "unmatched" && <Unmatched rows={unmatched} />}
      {tab === "types" && <Types rows={data.types} />}
      {tab === "sources" && (
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: S_COLS }}><span>Source</span><span>Checked</span><span className="num">Last run</span><span className="num">Fetched</span><span className="num">Matched</span><span className="num">7 days</span></div>
          {data.sources.map((s: any) => (
            <div key={s.key} className="row" style={{ gridTemplateColumns: S_COLS }}>
              <div className="cell-main"><span className="t">{s.label}</span><span className="s">{s.paid ? `Paid: ${s.provider.charAt(0).toLowerCase()}${s.provider.slice(1)}` : s.provider}</span></div>
              <span className="mute nowrap">{s.adapter === "webhook" ? "As it arrives" : s.cadence_minutes >= 1440 ? "Daily" : s.cadence_minutes >= 60 ? `Every ${s.cadence_minutes / 60} h` : `Every ${s.cadence_minutes} min`}</span>
              <span className="num">{s.adapter === "webhook" ? "" : s.error ? <Status kind="stop">Failed</Status> : ago(s.last_run)}</span>
              <span className="num" data-label="Fetched">{s.adapter === "webhook" ? "" : s.fetched ?? ""}</span><span className="num" data-label="Matched">{s.adapter === "webhook" ? "" : s.matched ?? ""}</span><span className="num strong" data-label="7 days">{s.week}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
const S_COLS = "minmax(0,2fr) 70px 110px 80px 80px 70px";

function Feed({ rows }: { rows: any[] }) {
  if (!rows.length) return <Empty title="Nothing here" />;
  return (
    <div className="ledger">
      {rows.map((s: any) => (
        <div key={s.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) minmax(0,1.6fr) 84px 36px" }}>
          <SignalIcon type={s.type_key} />
          {s.account_id
            ? <button className="cell-main" style={{ background: "none", border: 0, padding: 0, textAlign: "left" }} onClick={() => openSheet("account", s.account_id)}><span className="t">{s.name}</span><span className="s">{s.label}</span></button>
            : <div className="cell-main"><span className="t">{s.raw_domain || s.raw_company || "Unknown company"}</span><span className="s">{s.label}</span></div>}
          <span className="clip hide-sm">{s.evidence.summary}</span>
          <span className="num mute small hide-sm">{ago(s.ingested_at)}</span>
          {safeUrl(s.evidence.url) ? <a className="iconbtn" href={safeUrl(s.evidence.url)} target="_blank" rel="noreferrer noopener" aria-label="Open the source"><ArrowSquareOut size={15} /></a> : <span />}
        </div>
      ))}
    </div>
  );
}

/** Link a signal to an account the desk has, found by name or domain. */
function LinkTo({ signalId, hint, onClose }: { signalId: number; hint: string; onClose: () => void }) {
  const open = true;
  const [q, setQ] = useState(hint || "");
  const [hits, setHits] = useState<any[]>([]);
  const [busy, run] = useBusy();
  useEffect(() => {
    if (!open || q.trim().length < 2) { setHits([]); return; }
    const t = window.setTimeout(() => api<any>(`/api/accounts?view=all&q=${encodeURIComponent(q.trim())}`).then((r) => setHits(r.accounts.slice(0, 5))).catch(() => setHits([])), 250);
    return () => window.clearTimeout(t);
  }, [q, open]);
  return (
    <span className="link-pop" style={{ gridColumn: "1 / -1" }}>
      <input className="input" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Account name or domain" aria-label="Find the account" />
      {hits.map((a) => (
        <button key={a.id} className="btn quiet sm" disabled={busy} onClick={() => run(() => api(`/api/signals/${signalId}/resolve`, { method: "POST", body: { action: "link", account_id: a.id } }), `Linked to ${a.name}.`)}>{a.name}</button>
      ))}
      <button className="btn quiet sm" onClick={onClose}>Cancel</button>
    </span>
  );
}

/** Signals about companies the desk does not know: add the company as an account, or set it aside. */
function Unmatched({ rows }: { rows: any[] }) {
  const [busy, run] = useBusy();
  const [linking, setLinking] = useState<number | null>(null);
  if (!rows.length) return <Empty title="Every signal matched an account" />;
  const act = (id: number, action: string) => run(() => api(`/api/signals/${id}/resolve`, { method: "POST", body: { action } }),
    action === "create" ? "Added as an account. It is scored now." : "Set aside.");
  return (
    <div className="ledger">
      {rows.map((s: any) => (
        <div key={s.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) minmax(0,1.4fr) auto" }}>
          <SignalIcon type={s.type_key} />
          <div className="cell-main"><span className="t">{s.raw_domain || s.raw_company || "Unknown company"}</span><span className="s">{s.label}{s.status_reason && s.status_reason !== "no account with this domain or name" ? `, ${s.status_reason}` : ""}</span></div>
          <span className="clip hide-sm">{s.evidence.summary}</span>
          <span className="actions">
            <button className="btn quiet sm" disabled={busy} onClick={() => act(s.id, "ignore")}>Set aside</button>
            <button className="btn quiet sm" onClick={() => setLinking(linking === s.id ? null : s.id)}>Link</button>
            {s.raw_domain ? <button className="btn line sm" disabled={busy} onClick={() => act(s.id, "create")}>Add account</button> : null}
          </span>
          {linking === s.id ? <LinkTo signalId={s.id} hint={s.raw_company || (s.raw_domain || "").split(".")[0]} onClose={() => setLinking(null)} /> : null}
        </div>
      ))}
    </div>
  );
}

function Types({ rows }: { rows: any[] }) {
  const max = Math.max(0.0001, ...rows.map((r) => r.meeting_rate || 0));
  return (
    <>
            <div className="ledger">
        <div className="row head" style={{ gridTemplateColumns: T_COLS }}><span>Signal</span><span className="num">Weight</span><span className="num">Seen</span><span className="num">Plays started</span><span className="num">Held back</span><span>Meetings within 60 days, against held back</span></div>
        {rows.map((r) => (
          <div key={r.key} className="row" style={{ gridTemplateColumns: T_COLS }} title={r.because}>
            <div className="cell-main"><span className="t"><SignalLabel type={r.key} label={r.label} /></span></div>
            <span className="num">{Number(r.weight) > 0 ? `+${Number(r.weight)}` : Number(r.weight)}</span>
            <span className="num">{r.seen}</span>
            <span className="num" data-label="Plays started">{r.treated}</span><span className="num" data-label="Held back">{r.holdout}</span>
            <div>{!r.starts_plays ? <span className="faint" title="No live play starts on this signal. It raises an account's priority, but its own effect is not measured.">Not measured: no play starts on it</span>
              : !r.treated ? <span className="faint">No plays yet</span>
              : !r.lift?.enough ? <span title={`${pct(r.meeting_rate)} with a play met, against ${pct(r.lift?.holdout?.rate)} held back. ${r.lift?.still_needed?.holdout ? `${r.lift.still_needed.holdout} more held-back accounts` : `${r.lift?.still_needed?.treated} more accounts with a play`} are needed to tell.${r.lift?.out_of_reach ? ` That is more than the ${r.lift.room} accounts in this desk never offered one, so at this size it cannot be told.` : ""}`}>
                  <Status kind="wait">Too few to tell</Status></span>
              : <Bar label="" value={r.meeting_rate || 0} of={max} shown={pct(r.meeting_rate)}
                  hint={`vs ${pct(r.lift.holdout.rate)} held back, ${r.lift.difference >= 0 ? "+" : ""}${pct(r.lift.difference)} (${pct(r.lift.interval[0])} to ${pct(r.lift.interval[1])})`} />}</div>
          </div>
        ))}
      </div>
    </>
  );
}
const T_COLS = "minmax(200px,1.8fr) 60px 56px 96px 80px minmax(160px,1.1fr)";

// ---------------------------------------------------------------- Plays

const STAGES = ["research", "draft", "supervised", "autonomous"];

/** A play as one quiet row: what starts it, its name and the bet it makes, how far it has earned its way, what it produced.
 *  The one accent on the page is the last stage each play has earned. */
function PlayRow({ p, i }: { p: any; i: number }) {
  const f = p.funnel, stage = Math.max(0, STAGES.indexOf(p.autonomy));
  const meta = p.status === "live" ? null : p.status === "draft" ? "Draft, waiting for a manager" : cap(p.status);
  return (
    <button className={`prow${p.status !== "live" ? " is-off" : ""}`} onClick={() => openSheet("play", p.id)}>
      <span className="prow-sigs">{(p.trigger?.any_of || []).slice(0, 3).map((t: string) => (
        <span key={t} title={SIGNAL_NAME[t] || t}><SignalIcon type={t} size={16} /><span className="sr-only">{SIGNAL_NAME[t] || t}, </span></span>
      ))}</span>
      <span className="prow-main">
        <span className="prow-name">{p.name}{meta ? <span className="prow-meta">{meta}</span> : null}</span>
        <span className="prow-hyp">{p.hypothesis}</span>
        <span className="prow-stage">
          <span className="prow-stage-t">{STAGE[p.autonomy]}</span>
          <span className="prow-meter" aria-hidden="true">{STAGES.map((x, k) => (
            <i key={x} className={k < stage ? "on" : k === stage ? "on is-now" : ""} style={{ animationDelay: `${i * 60 + k * 70}ms` }} />
          ))}</span>
          <span className="prow-of">{stage + 1} of 4</span>
        </span>
      </span>
      <span className="prow-n"><span className="sr-only">Accounts </span>{n0(f.proposed)}</span>
      <span className={`prow-n is-hero${f.meetings ? "" : " is-zero"}`}><span className="sr-only">Meetings </span>{n0(f.meetings)}</span>
    </button>
  );
}

export function Plays() {
  const { data, error, reload } = useData<any>("/api/plays");
  const me = useData<any>("/api/me").data;
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Plays</h1></div><Loading /></div>;
  const live = data.plays.filter((p: any) => p.status === "live").length;
  return (
    <div className="page">
      <div className="head"><div><h1>Plays</h1><p className="sub">{live} live</p></div>
        {me?.user.role === "gtm" ? <button className="btn" onClick={() => openSheet("playedit", "new")}>New play</button> : null}</div>
      {me && me.user.role !== "sdr" ? <Suggested /> : null}
      <div className="plist">
        <div className="prow is-head" aria-hidden="true"><span className="prow-sigs" /><span>Play, and who writes</span><span className="prow-n">Accounts</span><span className="prow-n">Meetings</span></div>
        {data.plays.map((p: any, i: number) => <PlayRow key={p.id} p={p} i={i} />)}
      </div>
    </div>
  );
}

/** Plays the desk suggests from what buyers said on calls. Manager and GTM only: the quotes behind them are private. */
function Suggested() {
  const { data } = useData<any>("/api/play-suggestions");
  if (!data) return null;
  const rows = data.suggestions;
  return (
    <Section title="Suggested from calls" icon={Lightbulb} count={rows.length}>
      {rows.length ? (
        <div className="ledger sugg wrap-names">
          <div className="row head" style={{ gridTemplateColumns: SUG_COLS }}><span>What buyers said</span><span>Signal</span><span className="num">On this signal</span><span className="num">Other accounts</span></div>
          {rows.map((x: any) => {
            const e = x.evidence;
            return (
              <button key={x.id} className="row" style={{ gridTemplateColumns: SUG_COLS }} onClick={() => openSheet("suggestion", x.id)}>
                <div className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}>{x.theme}</span>
                  <span className="s">From {e.sdrs} SDRs</span></div>
                <span data-label="Signal"><SignalLabel type={x.segment} label={x.segment_label} /></span>
                <span className="num" data-label="On this signal"><span className="strong">{e.accounts} of {e.segment_accounts}</span></span>
                <span className="num mute" data-label="Other accounts">{e.elsewhere} of {e.elsewhere_accounts}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty title="Nothing suggested from calls right now">
          <span className="mute"> The bar is in Settings.</span>
        </Empty>
      )}
    </Section>
  );
}
const SUG_COLS = "minmax(0,1.6fr) minmax(0,1.2fr) 120px 120px";

export { cap };
