import { CalendarCheck, EnvelopeSimple, LinkedinLogo, Phone } from "@phosphor-icons/react";
import { Avatar, Logo } from "../marks";
import { Empty, Failed, Fig, Loading, Section, Seg, ahead, cap, dayTime, n0, navigate, usePath, useData, withParam } from "../lib";
import { PLAY_STATE, STEP_NAME, openSheet } from "../sheets";

const STAGES: [string, string, string[]][] = [
  ["researching", "Researching", ["accepted", "researching"]],
  ["approving", "Drafts to approve", ["approving"]],
  ["active", "Reaching out", ["active"]],
  ["engaged", "Replied", ["engaged"]],
  ["meeting", "Meeting", ["meeting"]],
];

/** Everything in motion: every open play past the decision, and each person's sequence in it. */
export function Flight() {
  const [, params] = usePath();
  const me = useData<any>("/api/me").data;
  const isSdr = me?.user.role === "sdr";
  const scope = params.get("scope") || (isSdr ? "mine" : "team");
  const stage = params.get("stage") || "all";
  const { data, error, reload } = useData<any>(me ? `/api/in-flight?mine=${scope === "mine"}` : null);
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>In flight</h1></div><Loading /></div>;
  const n = (states: string[]) => states.reduce((t, s) => t + (data.counts[s] || 0), 0);
  const shown = stage === "all" ? data.plays : data.plays.filter((p: any) => (STAGES.find((x) => x[0] === stage)?.[2] || []).includes(p.state));
  return (
    <div className="page">
      <div className="head"><div><h1>In flight</h1></div></div>
      <div className="figs">
        <Fig value={n0(data.plays.length)} label={scope === "mine" ? "Your accounts in a play" : "Accounts in a play"} />
        <Fig value={n0(n(["active"]))} label="Reaching out" />
        <Fig value={n0(n(["engaged"]))} label="Replied" />
        <Fig value={n0(n(["meeting"]))} label="Meeting" />
      </div>
      <div className="toolbar">
        <Seg label="Stage" value={stage} onChange={(v) => navigate(withParam("stage", v === "all" ? null : v), true)}
          options={[["all", "All"], ...STAGES.filter(([, , st]) => n(st) > 0).map(([k, l, st]) => [k, `${l} ${n(st)}`] as [string, string])]} />
        {!isSdr ? null : (
          <Seg label="Whose" value={scope} onChange={(v) => navigate(withParam("scope", v === "mine" ? null : v), true)}
            options={[["mine", "Mine"], ["team", "Team"]]} />
        )}
      </div>
      {shown.length ? (
        <Section title={stage === "all" ? "By priority" : STAGES.find((x) => x[0] === stage)?.[1] || ""} count={shown.length}>
          <div className="ledger flight">
            <div className="row head" style={{ gridTemplateColumns: F_COLS }}><span /><span>Account</span><span>People and their steps</span><span className="num">Next</span></div>
            {shown.map((p: any) => <FlightRow key={p.id} p={p} team={scope === "team"} />)}
          </div>
        </Section>
      ) : <Empty title={stage === "all" ? "Nothing in a play yet" : "Nothing at this stage"} />}
    </div>
  );
}

const F_COLS = "28px minmax(0,1fr) minmax(0,1.5fr) 150px";

function FlightRow({ p, team }: { p: any; team: boolean }) {
  const st = PLAY_STATE[p.state] || ["off", cap(p.state)];
  return (
    <div className="row" style={{ gridTemplateColumns: F_COLS, alignItems: "start" }}>
      <Logo domain={p.primary_domain} name={p.name} />
      <button className="cell-main link-row" onClick={() => openSheet("account", `${p.account_id}:people`)}>
        <span className="t">{p.name}</span>
        <span className="s">{p.play}, {st[1].toLowerCase()}{team && p.owner ? `, ${p.owner}` : ""}</span>
      </button>
      <div className="flight-people">
        {p.people.length ? p.people.map((e: any) => <PersonSteps key={e.id} e={e} sequence={p.sequence} />)
          : <span className="mute small">{p.state === "researching" || p.state === "accepted" ? "Finding the right people" : "Nobody in sequence"}</span>}
      </div>
      <div className="num flight-next">
        {p.next ? <><span className="t">{STEP_NAME[`${p.next.step.channel}:${p.next.step.job}`] || cap(p.next.step.channel)}</span>
          <span className="s">{ahead(p.next.at) === "overdue" ? "Due now" : dayTime(p.next.at)}</span></>
          : p.state === "meeting" ? <span className="s"><CalendarCheck size={14} style={{ verticalAlign: -2 }} /> Meeting booked</span>
          : p.state === "approving" ? <span className="s">Waiting for approval</span>
          : <span className="s">Nothing scheduled</span>}
      </div>
    </div>
  );
}

const STOPPED = new Set(["stopped", "done"]);

/** One person's sequence as a strip of steps: done, next, still to come, or not happening because they stopped. */
function PersonSteps({ e, sequence }: { e: any; sequence: any[] }) {
  const sent = new Set<number>(e.sent || []);
  const live = e.state === "active" || e.state === "pending" || e.state === "paused";
  return (
    <button className="person-steps" onClick={(ev) => { ev.stopPropagation(); openSheet("person", e.person_id); }} title={e.full_name}>
      <Avatar name={e.full_name} photo={e.photo_url} size={22} />
      <span className="ps-name clip">{e.full_name.split(" ")[0]}</span>
      <span className="steps" aria-label={`${e.full_name}: step ${Math.min(e.step_index + 1, sequence.length)} of ${sequence.length}`}>
        {sequence.map((s: any, i: number) => {
          const done = sent.has(i) || i < e.step_index;
          const next = live && i === e.step_index;
          const off = !live && !done && STOPPED.has(e.state);
          const Ic = s.channel === "email" ? EnvelopeSimple : s.channel === "call" ? Phone : LinkedinLogo;
          return (
            <span key={i} className={`step${done ? " done" : ""}${next ? " next" : ""}${off ? " off" : ""}`}
              title={`${STEP_NAME[`${s.channel}:${s.job}`] || s.channel}, day ${s.day}${done ? ", done" : next ? ", next" : off ? ", not happening" : ""}`}>
              <Ic size={11} weight={done ? "fill" : "regular"} aria-hidden="true" />
            </span>
          );
        })}
      </span>
      {e.state === "paused" ? <span className="mute small">paused</span> : null}
    </button>
  );
}
