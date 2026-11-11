import { Avatar } from "../marks";
import { SignalIcon, SignalLabel } from "../signalIcons";
import { ArrowSquareOut } from "@phosphor-icons/react";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Seg, Status, ago, cap, n0, navigate, pct, usePath, useData,
  withParam,
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
          <div className="cell-main hide-sm"><span className="t" style={{ fontWeight: 450 }}>{m.subject}</span><span className="s">Email {m.step_index + 1}</span></div>
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
  const view = (params.get("view") || "mine") as "mine" | "all" | "hot" | "needs_person";
  const { data, error, reload } = useData<any>(`/api/replies?view=${view}`);
  return (
    <div className="page">
      <div className="head"><div><h1>Replies</h1></div></div>
      <Seg label="Which replies" value={view} onChange={(v) => navigate(withParam("view", v === "mine" ? null : v), true)}
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
  const silent = data.sources.filter((s: any) => s.enabled && s.key !== "webhook" && (!s.last_run || Date.now() - new Date(s.last_run).getTime() > 1e15)).length;
  return (
    <div className="page">
      <div className="head"><div><h1>Signals</h1></div></div>
      <div className="figs">
        <Fig value={n0(week)} label="Signals in the last 7 days" />
        <Fig value={data.sources.filter((s: any) => s.enabled).length} label="Sources" />
        {silent ? <Fig value={silent} label="Sources silent" /> : null}
      </div>
      <Seg label="View" value={tab} onChange={(v) => navigate(withParam("tab", v === "feed" ? null : v), true)}
        options={[["feed", "Latest"], ["types", "Which signals work"], ["sources", "Sources"], ["unmatched", "Not matched"]]} />
      {tab === "feed" && <Feed rows={data.feed.filter((s: any) => s.status === "matched")} />}
      {tab === "unmatched" && <Feed rows={unmatched} />}
      {tab === "types" && <Types rows={data.types} />}
      {tab === "sources" && (
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: S_COLS }}><span>Source</span><span>Every</span><span className="num">Last run</span><span className="num">Fetched</span><span className="num">Matched</span><span className="num">7 days</span></div>
          {data.sources.map((s: any) => (
            <div key={s.key} className="row" style={{ gridTemplateColumns: S_COLS }}>
              <div className="cell-main"><span className="t">{s.label}</span><span className="s">{s.paid ? `Paid: ${s.provider.charAt(0).toLowerCase()}${s.provider.slice(1)}` : s.provider}</span></div>
              <span className="mute">{s.cadence_minutes >= 1440 ? "daily" : s.cadence_minutes >= 60 ? `every ${s.cadence_minutes / 60} hours` : `every ${s.cadence_minutes} minutes`}</span>
              <span className="num">{s.key === "webhook" ? "Pushed to us" : s.error ? <Status kind="stop">Failed</Status> : ago(s.last_run)}</span>
              <span className="num">{s.fetched ?? ""}</span><span className="num">{s.matched ?? ""}</span><span className="num strong">{s.week}</span>
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
          {s.evidence.url ? <a className="iconbtn" href={s.evidence.url} target="_blank" rel="noreferrer noopener" aria-label="Open the source"><ArrowSquareOut size={15} /></a> : <span />}
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
        <div className="row head" style={{ gridTemplateColumns: T_COLS }}><span>Signal</span><span className="num">Weight</span><span className="num">Seen</span><span className="num">Plays started</span><span className="num">Held back</span><span>Meetings within 60 days</span></div>
        {rows.map((r) => (
          <div key={r.key} className="row" style={{ gridTemplateColumns: T_COLS }} title={r.because}>
            <div className="cell-main"><span className="t"><SignalLabel type={r.key} label={r.label} /></span><span className="s" style={{ paddingLeft: 30 }}>{r.because}</span></div>
            <span className="num">{Number(r.weight) > 0 ? `+${Number(r.weight)}` : Number(r.weight)}</span>
            <span className="num">{r.seen}</span>
            <span className="num">{r.treated}</span><span className="num">{r.holdout}</span>
            <div>{r.treated ? <Bar label="" value={r.meeting_rate || 0} of={max} shown={pct(r.meeting_rate)} hint={`${r.treated_meetings} of ${r.treated}`} /> : <span className="faint">No plays yet</span>}</div>
          </div>
        ))}
      </div>
    </>
  );
}
const T_COLS = "minmax(0,1.6fr) 60px 56px 96px 80px minmax(160px,1.2fr)";

// ---------------------------------------------------------------- Plays

export function Plays() {
  const { data, error, reload } = useData<any>("/api/plays");
  const me = useData<any>("/api/me").data;
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Plays</h1></div><Loading /></div>;
  return (
    <div className="page">
      <div className="head"><div><h1>Plays</h1></div>
        {me?.user.role === "gtm" ? <button className="btn" onClick={() => openSheet("playedit", "new")}>New play</button> : null}</div>
      <div className="ledger">
        <div className="row head" style={{ gridTemplateColumns: P_COLS }}><span>Play</span><span>Who writes</span><span className="num">Accounts</span><span className="num">Positive</span><span className="num">Meetings</span><span className="num">Signal to first email</span></div>
        {data.plays.map((p: any) => {
          const f = p.funnel;
          return (
            <button key={p.id} className="row" style={{ gridTemplateColumns: P_COLS }} onClick={() => openSheet("play", p.id)}>
              <div className="cell-main"><span className="t">{p.name}</span><span className="s">{p.status === "live" ? (p.urgent ? "Live, decide within a day" : "Live") : p.status === "draft" ? "Draft, waiting for a manager" : cap(p.status)}</span></div>
              <span className="mute clip hide-sm">{STAGE[p.autonomy]}</span>
              <span className="num">{f.proposed}</span>
              <span className="num">{f.positive}</span>
              <span className="num strong">{f.meetings}</span>
              <span className="num mute hide-sm">{p.median_hours_to_first_touch ? `${Math.round(p.median_hours_to_first_touch)} h` : ""}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
const P_COLS = "minmax(0,1.6fr) minmax(0,1.2fr) 80px 72px 80px 150px";

export { cap };
