import { CalendarCheck, ChatCircleText, EnvelopeSimple, LinkedinLogo, PencilSimpleLine, Phone } from "@phosphor-icons/react";
import { useState } from "react";
import { Avatar, Logo } from "../marks";
import { Empty, Failed, Loading, Section, Seg, Status, ahead, cap, dayTime, late, navigate, usePath, useData, withParam } from "../lib";
import { GOOD_STOPS, STEP_NAME, openSheet, stopWord } from "../sheets";

const STAGES: [string, string, string[]][] = [
  ["researching", "Researching", ["accepted", "researching"]],
  ["approving", "Drafts to approve", ["approving"]],
  ["active", "Reaching out", ["active"]],
  ["engaged", "Replied", ["engaged"]],
  ["meeting", "Meeting", ["meeting"]],
];

/** A step's name, the same everywhere: an email by its number (as Approvals names it), anything else by what it is. */
export function stepLabel(step: any, index: number): string {
  return step.channel === "email" ? `Email ${index + 1}` : STEP_NAME[`${step.channel}:${step.job}`] || cap(step.channel);
}

/** Everything in motion: every open play past the decision, and each person's sequence in it. */
export function Flight() {
  const [, params] = usePath();
  const me = useData<any>("/api/me").data;
  const isSdr = me?.user.role === "sdr";
  const scope = params.get("scope") || (isSdr ? "mine" : "team");
  const { data, error, reload } = useData<any>(me ? `/api/in-flight?mine=${scope === "mine"}` : null);
  const [q, setQ] = useState(params.get("q") || "");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>In flight</h1></div><Loading /></div>;
  const n = (states: string[]) => states.reduce((t, s) => t + (data.counts[s] || 0), 0);
  const asked = params.get("stage") || "all";
  const stage = asked !== "all" && n(STAGES.find((x) => x[0] === asked)?.[2] || []) === 0 ? "all" : asked;
  const team = scope === "team";
  const play = params.get("play") || "";
  const sdr = team ? params.get("sdr") || "" : "";
  const when = params.get("when") || "";
  const needle = (params.get("q") || "").trim().toLowerCase();
  const plays = [...new Set<string>(data.plays.map((p: any) => p.play))].sort();
  const sdrs = [...new Set<string>(data.plays.map((p: any) => p.owner || "Unassigned"))].sort();
  const endOfDay = new Date(me?.now || Date.now()); endOfDay.setHours(23, 59, 59, 999);
  const matches = (p: any) => (!play || p.play === play) && (!sdr || (p.owner || "Unassigned") === sdr)
    && (!needle || p.name.toLowerCase().includes(needle) || (p.primary_domain || "").includes(needle)
      || p.people.some((e: any) => e.full_name.toLowerCase().includes(needle)))
    && (!when || (when === "waiting" ? (p.state === "engaged" && p.reply_id) || p.state === "approving" || !!p.draft_id
      : when === "due" ? p.next && (ahead(p.next.at) === "overdue" || new Date(p.next.at) <= endOfDay)
      : when === "calls" ? p.next && p.next.step.channel !== "email" : true));
  const filtered = data.plays.filter(matches);
  const waiting = (p: any) => (p.state === "engaged" && p.reply_id) || !!p.draft_id;
  const ordered = [...filtered].sort((a: any, b: any) => Number(!!waiting(b)) - Number(!!waiting(a)));
  const shown = stage === "all" ? ordered : ordered.filter((p: any) => (STAGES.find((x) => x[0] === stage)?.[2] || []).includes(p.state));
  const set = (k: string, v: string) => navigate(withParam(k, v || null), true);
  const narrowed = play || sdr || when || needle;
  const cols = team ? F_COLS_TEAM : F_COLS;
  return (
    <div className="page">
      <div className="head"><div><h1>In flight</h1><p className="sub">{data.plays.length} {data.plays.length === 1 ? "account" : "accounts"} in a play{scope === "mine" ? ", yours" : ""}</p></div></div>
      <div className="toolbar">
        <Seg label="Stage" value={stage} onChange={(v) => navigate(withParam("stage", v === "all" ? null : v), true)}
          options={[["all", "All"], ...STAGES.filter(([, , st]) => n(st) > 0).map(([k, l, st]) => [k, `${l} ${n(st)}`] as [string, string])]} />
        {!isSdr ? null : (
          <Seg label="Whose" value={scope} onChange={(v) => navigate(withParam("scope", v === "mine" ? null : v), true)}
            options={[["mine", "Mine"], ["team", "Team"]]} />
        )}
      </div>
      <div className="toolbar filters">
        <form onSubmit={(e) => e.preventDefault()}>
          <input className="input" style={{ width: 220 }} type="search" placeholder="Company or person" value={q} aria-label="Search in flight"
            onChange={(e) => { const v = e.target.value; setQ(v); window.clearTimeout((window as any).__flightq); (window as any).__flightq = window.setTimeout(() => set("q", v.trim()), 220); }} />
        </form>
        <select className="select" style={{ width: 200 }} value={play} onChange={(e) => set("play", e.target.value)} aria-label="Play">
          <option value="">Every play</option>{plays.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        {team ? (
          <select className="select" style={{ width: 160 }} value={sdr} onChange={(e) => set("sdr", e.target.value)} aria-label="SDR">
            <option value="">Every SDR</option>{sdrs.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        ) : null}
        <select className="select" style={{ width: 190 }} value={when} onChange={(e) => set("when", e.target.value)} aria-label="Next step">
          <option value="">Any next step</option>
          <option value="due">Due today</option>
          <option value="calls">Next is a call or LinkedIn</option>
          <option value="waiting">Waiting on the team</option>
        </select>
        {narrowed ? <button className="btn line sm clear" onClick={() => { setQ(""); const u = new URL(window.location.href); ["q", "play", "sdr", "when"].forEach((k) => u.searchParams.delete(k));
          navigate(u.pathname + (u.search || ""), true); }}>Clear</button> : null}
      </div>
      {shown.length ? (
        <Section title={stage === "all" ? "Waiting on the team first, then by next step" : STAGES.find((x) => x[0] === stage)?.[1] || ""} count={shown.length}
          right={<span className="step-key" aria-label="How to read the steps">
            <span><i className="step sent" />Sent</span><span><i className="step next" />Next</span>
            <span><i className="step to-come" />To come</span><span><i className="step skipped" />Skipped or not happening</span></span>}>
          <div className="ledger flight">
            <div className="row head" style={{ gridTemplateColumns: cols }}>
              <span /><span>Account</span><span>People and their steps</span>{team ? <span className="hide-sm">SDR</span> : null}<span>Next</span>
            </div>
            {shown.map((p: any) => <FlightRow key={p.id} p={p} team={team} cols={cols} mine={scope === "mine"} />)}
          </div>
        </Section>
      ) : <Empty title={narrowed ? "Nothing in flight matches" : "Nothing in a play yet"} />}
    </div>
  );
}

const F_COLS = "28px minmax(0,1fr) minmax(0,1.6fr) 170px";
const F_COLS_TEAM = "28px minmax(0,1fr) minmax(0,1.6fr) 120px 170px";

function FlightRow({ p, team, cols, mine }: { p: any; team: boolean; cols: string; mine: boolean }) {
  return (
    <div className="row" style={{ gridTemplateColumns: cols, alignItems: "start" }}>
      <Logo domain={p.primary_domain} name={p.name} />
      <button className="cell-main link-row" onClick={() => openSheet("account", `${p.account_id}:people`)}>
        <span className="t">{p.name}</span>
        <span className="s">{p.play}</span>
      </button>
      <div className="flight-people">
        {p.people.length ? p.people.map((e: any) => <PersonSteps key={e.id} e={e} sequence={p.sequence} meetingPerson={p.meeting?.person_id} />)
          : <span className="mute small">{p.state === "researching" || p.state === "accepted" ? "Finding the right people" : "Nobody in sequence"}</span>}
      </div>
      {team ? <span className="s mute hide-sm flight-owner">{p.owner || "Unassigned"}</span> : null}
      <div className="flight-next"><Next p={p} mine={mine} /></div>
    </div>
  );
}

/** What happens next on this account, and who it is for. What waits on a person opens it. */
function Next({ p, mine }: { p: any; mine: boolean }) {
  if (p.meeting && (p.state === "meeting" || p.meeting.status !== "booked")) {
    const word = { booked: "Meeting", held: "Meeting held", no_show: "No show", cancelled: "Meeting cancelled" }[p.meeting.status as string] || "Meeting";
    return <button className="link-row cell-main" onClick={() => openSheet("meeting", p.meeting.id)}>
      <span className="t"><CalendarCheck size={14} style={{ verticalAlign: -2 }} aria-hidden="true" /> {word}</span>
      <span className="s">{dayTime(p.meeting.starts_at)}</span></button>;
  }
  if (p.state === "engaged" && p.reply_id) {
    return <button className="link-row cell-main" onClick={() => openSheet("reply", p.reply_id)}>
      <span className="t"><ChatCircleText size={14} style={{ verticalAlign: -2 }} aria-hidden="true" /> Answer the reply</span>
      <span className="s">{mine ? "Waiting on you" : "Waiting on the SDR"}</span></button>;
  }
  if (p.draft_id) {
    return <button className="link-row cell-main" onClick={() => openSheet("message", p.draft_id)}>
      <span className="t"><PencilSimpleLine size={14} style={{ verticalAlign: -2 }} aria-hidden="true" /> Approve Email {(p.draft_step ?? 0) + 1}</span>
      <span className="s">Nothing sends until then</span></button>;
  }
  if (p.next) {
    const you = mine && p.next.step.by === "sdr";
    return <div className="cell-main">
      <span className="t">{stepLabel(p.next.step, p.next.index)} · {p.next.person}{you ? <span className="tag">You</span> : null}</span>
      <span className="s">{ahead(p.next.at) === "overdue" ? late(p.next.at) : dayTime(p.next.at)}</span></div>;
  }
  if (p.state === "engaged") return <div className="cell-main"><span className="t">In conversation</span><span className="s">The SDR has it from here</span></div>;
  return <span className="s mute">Nothing scheduled</span>;
}

const STOPPED = new Set(["stopped", "done"]);

/** One person's sequence as a strip of steps: sent, skipped, next, still to come, or not happening because they stopped. */
function PersonSteps({ e, sequence, meetingPerson }: { e: any; sequence: any[]; meetingPerson?: number | null }) {
  const sent = new Set<number>(e.sent || []);
  const live = e.state === "active" || e.state === "pending";
  const why = e.state === "paused" || e.state === "stopped" ? stopWord(e.stop_reason || e.pause_reason) : "";
  const stateOf = (i: number) => sent.has(i) ? "sent" : i < e.step_index ? "skipped"
    : live && i === e.step_index ? "next" : STOPPED.has(e.state) ? "not happening" : e.state === "paused" ? "on hold" : "to come";
  const where = `${sent.size} of ${sequence.length} sent`;
  return (
    <button className="person-steps" onClick={(ev) => { ev.stopPropagation(); openSheet("person", e.person_id); }}
      aria-label={`${e.full_name}: ${where}${why ? `, ${why.toLowerCase()}` : ""}. Open their page.`}>
      <Avatar name={e.full_name} photo={e.photo_url} size={22} />
      <span className="ps-name clip"><span className="hide-sm">{e.full_name}</span><span className="only-sm">{e.first_name}</span></span>
      <span className="steps" aria-hidden="true">
        {sequence.map((s: any, i: number) => {
          const st = stateOf(i);
          const Ic = s.channel === "email" ? EnvelopeSimple : s.channel === "call" ? Phone : LinkedinLogo;
          return (
            <span key={i} className={`step ${st.replace(" ", "-")}`} title={`${stepLabel(s, i)}, day ${s.day}: ${st}`}>
              <Ic size={12} weight={st === "sent" ? "fill" : "regular"} />
            </span>
          );
        })}
      </span>
      {why ? <span className="ps-why"><Status kind={GOOD_STOPS.has(e.stop_reason) ? "ok" : e.state === "paused" ? "hold" : "off"}>
        {e.stop_reason === "meeting_booked" && meetingPerson && meetingPerson !== e.person_id ? "Colleague's meeting" : why}</Status></span> : null}
    </button>
  );
}
