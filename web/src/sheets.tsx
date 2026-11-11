import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowSquareOut, CalendarCheck, EnvelopeSimple, LinkedinLogo, Phone, X } from "@phosphor-icons/react";
import { api } from "./api";
import { Avatar, Logo } from "./marks";
import { SignalIcon, SignalLabel } from "./signalIcons";
import { PlayEditor, PlayPreview } from "./PlayEditor";
import {
  Bar, Empty, Failed, Fig, Loading, Section, Status, ago, ahead, cap, day, dayTime, money, n0, navigate, pct,
  toast, useBusy, useData, withParam, type Glyph,
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
  if (kind === "account") return <AccountSheet key={`account:${id}`} id={Number(id)} />;
  if (kind === "message") return <MessageSheet key={key} id={Number(id)} />;
  if (kind === "person") return <PersonSheet key={key} id={Number(id)} />;
  if (kind === "task") return <TaskSheet key={key} id={Number(id)} />;
  if (kind === "meeting") return <MeetingSheet key={key} id={Number(id)} />;
  if (kind === "reply") return <ReplySheet key={key} id={Number(id)} />;
  if (kind === "play") return <PlaySheet key={key} id={Number(id)} />;
  if (kind === "playedit") return <Frame key={key} crumb={id === "new" ? "New play" : "Edit play"}><PlayEditor id={id === "new" ? null : Number(id)} /></Frame>;
  return null;
}

// ---------------------------------------------------------------- shared vocab

export const PLAY_STATE: Record<string, [Glyph, string]> = {
  proposed: ["wait", "Proposed"], accepted: ["half", "Accepted"], researching: ["half", "Researching"],
  approving: ["wait", "Drafts to approve"], active: ["go", "In sequence"], engaged: ["ok", "Replied"],
  meeting: ["ok", "Meeting"], converted: ["ok", "Opportunity"], lost: ["stop", "Not interested"],
  stopped: ["off", "Ended"], skipped: ["off", "Skipped"], expired: ["off", "Expired"], held_out: ["none", "Held back"],
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
  approval_lapsed: "Approval came too late", rep_in_conversation: "SDR talking to them", colleague_engaged: "Colleague talking to us", person_moved: "Changed jobs", referral: "Referred someone",
  reply_received: "Replied, reading it", account_reply: "Colleague replied", out_of_office: "Out of office",
};
const stopWord = (r: string | null) => {
  if (!r) return "";
  if (STOP[r]) return STOP[r];
  if (r.startsWith("rejected")) return "Email rejected";
  if (r.startsWith("gate:") || r.startsWith("refused")) return "Blocked by a contact rule";
  if (r.startsWith("play_")) return "Play ended";
  return cap(r);
};
const GOOD_STOPS = new Set(["replied_positive", "meeting_booked", "referral"]);

const PERSONA: Record<string, string> = { cfo: "Finance leader", controller: "Controller", revops: "Revenue operations", data: "Data and systems" };

// ---------------------------------------------------------------- person

const TOUCH: Record<string, string> = {
  email_sent: "Email sent", reply: "Replied", meeting_booked: "Meeting booked", linkedin_connect: "Connection request sent",
  linkedin_accepted: "Accepted the connection", linkedin_message: "LinkedIn message sent", linkedin_reply: "Replied on LinkedIn",
  call_connected: "Call, spoke", call_voicemail: "Call, left a voicemail", call_no_answer: "Call, no answer",
  call_wrong_number: "Call, wrong number", they_called: "They called", they_emailed: "They emailed directly",
  i_emailed: "Emailed them directly", sdr_email: "Email written by the SDR",
};

export function PersonSheet({ id }: { id: number }) {
  const { data, error, reload } = useData<any>(`/api/people/${id}`);
  if (error) return <Frame crumb="Person"><Failed error={error} retry={reload} /></Frame>;
  if (!data) return <Frame crumb="Person"><Loading rows={8} /></Frame>;
  const p = data.person;
  // One history across channels, newest first. Replies are not repeated as touches.
  const history = [
    ...data.touches.filter((t: any) => t.kind !== "reply" && t.kind !== "meeting_booked").map((t: any) => ({ at: t.at, kind: "touch", t })),
    ...data.replies.map((r: any) => ({ at: r.received_at, kind: "reply", r })),
    ...data.signals.map((g: any) => ({ at: g.observed_at, kind: "signal", g })),
    ...data.meetings.map((m: any) => ({ at: m.starts_at, kind: "meeting", m })),
  ].sort((x, y) => (x.at < y.at ? 1 : -1));
  return (
    <Frame crumb="Person">
      <div className="who">
        <Avatar name={p.full_name} photo={p.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{p.full_name}</h2>
          <div className="meta clip">{p.title}{p.company ? <> at <button className="link" onClick={() => openSheet("account", p.account_id)}>{p.company}</button></> : null}</div>
        </div>
      </div>
      {data.suppressed.length ? (
        <div className="notice"><Status kind="stop">Do not contact</Status><span className="mute">{data.suppressed.map((x: any) => x.reason).join(", ")}</span></div>
      ) : null}
      <Section title="How to reach them">
        <div className="ledger">
          <Reach label="Email" value={p.email} state={p.email ? (p.email_status === "valid" ? ["ok", "Verified"] : p.email_status === "invalid" ? ["stop", "Bounces"] : ["half", cap(p.email_status)]) : null} />
          <Reach label="Phone" value={p.phone} state={p.phone ? (p.phone_status === "valid" ? ["ok", "Verified"] : ["half", cap(p.phone_status)]) : null} />
          <Reach label="LinkedIn" value={p.linkedin_url ? <a href={p.linkedin_url} target="_blank" rel="noreferrer noopener">Profile <ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a> : null}
            state={data.touches.some((x: any) => x.kind === "linkedin_accepted") ? ["ok", "Connected"] : data.touches.some((x: any) => x.kind === "linkedin_connect") ? ["wait", "Request sent"] : null} />
          {p.status !== "active" ? <Reach label="Status" value={cap(p.status)} /> : null}
        </div>
      </Section>
      {p.linkedin_url ? <LinkedInLog personId={p.id} canAccept={data.touches.some((x: any) => x.kind === "linkedin_connect") && !data.touches.some((x: any) => x.kind === "linkedin_accepted")} onDone={reload} /> : null}
      <Section title="Plays">
        {data.enrollments.length ? (
          <div className="ledger">
            {data.enrollments.map((e: any) => {
              const st = ENROLL[e.state] || ["off", cap(e.state)];
              const word = e.state === "stopped" || e.state === "paused" ? stopWord(e.stop_reason || e.pause_reason) || st[1] : st[1];
              const theirs = e.meeting && e.meeting.person_id === p.id;
              const colleague = e.stop_reason === "meeting_booked" && e.meeting && !theirs;
              const sub = e.state === "active" && e.next_at
                ? `Step ${e.step_index + 1} of ${e.sequence.length}, ${ahead(e.next_at) === "due" ? "due now" : `next ${ahead(e.next_at)}`}`
                : colleague ? `${e.meeting.name || "A colleague"} booked a meeting, so the play stopped for everyone`
                : `Since ${day(e.created_at)}`;
              return (
                <button key={e.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet("play", e.play_id)}>
                  <div className="cell-main"><span className="t">{e.play}</span><span className="s">{sub}</span></div>
                  <Status kind={GOOD_STOPS.has(e.stop_reason) ? "ok" : st[0]}>{colleague ? "Colleague's meeting" : word}</Status>
                </button>
              );
            })}
          </div>
        ) : <Empty title="Not in a play" />}
      </Section>
      <OutsideContact personId={p.id} onDone={reload} />
      <EraseBox personId={p.id} name={p.full_name} />
      <Section title="History">
        {history.length ? (
          <ul className="timeline">
            {history.map((h: any, i: number) => (
              <li key={i}>
                <span className="at">{day(h.at)}</span>
                {h.kind === "signal" ? <SignalIcon type={h.g.type_key} /> : <ChannelIcon channel={h.kind === "meeting" ? "meeting" : h.kind === "reply" ? (h.r.channel || "email") : h.t.channel} />}
                {h.kind === "meeting" ? (
                  <button className="cell-main link-row" onClick={() => openSheet("meeting", h.m.id)}>
                    <span className="t">{MEETING[h.m.status] || cap(h.m.status)}{h.m.source === "inbound" ? ", they asked for it" : ""}</span>
                    <span className="s">{dayTime(h.m.starts_at)}{h.m.play ? `, ${h.m.play}` : ""}</span>
                  </button>
                ) : h.kind === "touch" ? (
                  h.t.message_id ? (
                    <button className="cell-main link-row" onClick={() => openSheet("message", h.t.message_id)}>
                      <span className="t">{TOUCH[h.t.kind] || cap(h.t.kind.replace(/_/g, " "))}</span>
                      <span className="s">{h.t.subject ? `${h.t.subject}, email ${h.t.step_index + 1}` : ""}</span>
                    </button>
                  ) : <div className="cell-main"><span className="t">{TOUCH[h.t.kind] || cap(h.t.kind.replace(/_/g, " "))}</span><span className="s">{h.t.source === "person" ? "Logged by the SDR" : ""}</span></div>
                ) : h.kind === "reply" ? (
                  <button className="cell-main link-row" onClick={() => openSheet("reply", h.r.id)}>
                    <span className="t">Replied, {(LABEL[h.r.label] || LABEL.other)[1].toLowerCase()}</span>
                    <span className="s" style={{ whiteSpace: "normal" }}>{h.r.cleaned}</span>
                  </button>
                ) : (
                  <div className="cell-main"><span className="t">{h.g.label}</span><span className="s" style={{ whiteSpace: "normal" }}>{h.g.evidence.summary}</span></div>
                )}
              </li>
            ))}
          </ul>
        ) : <Empty title="Nothing yet" />}
      </Section>
    </Frame>
  );
}

// ---------------------------------------------------------------- task (LinkedIn and calls, done by the SDR)

export function TaskSheet({ id }: { id: number }) {
  const { data: t, error, reload } = useData<any>(`/api/tasks/${id}`);
  const [text, setText] = useState<string | null>(null);
  const [busy, run] = useBusy();
  if (error) return <Frame crumb="Task"><Failed error={error} retry={reload} /></Frame>;
  if (!t) return <Frame crumb="Task"><Loading rows={6} /></Frame>;
  const linkedin = t.kind.startsWith("linkedin");
  const body = text ?? t.draft ?? "";
  const over = t.max_chars && body.length > t.max_chars;
  const failures: any[] = t.draft_status === "failed_gate" && text === null ? (t.gate?.failures || []) : [];
  const open = t.status === "open";
  const done = (outcome: string) => run(async () => {
    await api(`/api/tasks/${id}/done`, { method: "POST", body: { outcome, text: linkedin && outcome === "sent" ? body : null } });
    closeSheet();
  }, t.outcomes[outcome] ? `${t.outcomes[outcome]}.` : "Skipped.");
  const copy = () => { navigator.clipboard?.writeText(body).then(() => toast("Copied."), () => toast("Select the text and copy it.")); };
  return (
    <Frame crumb={linkedin ? "LinkedIn" : t.kind === "call" ? "Call" : "Task"}
      foot={open ? (
        <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button className="btn quiet sm" disabled={busy} onClick={() => done("skipped")}>Skip</button>
          {Object.entries(t.outcomes as Record<string, string>).map(([k, l], i) => (
            <button key={k} className={i === 0 ? "btn sm" : "btn line sm"} disabled={busy || (k === "sent" && (!body || !!over))} onClick={() => done(k)}>{l}</button>
          ))}
        </div>
      ) : null}>
      <div className="who">
        <Avatar name={t.full_name} photo={t.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip"><button className="link-row" onClick={() => openSheet("person", t.person_id)}>{t.full_name}</button></h2>
          <div className="meta clip">{t.person_title}{t.company ? <> at <button className="link" onClick={() => openSheet("account", t.account_id)}>{t.company}</button></> : null}{t.play ? `, ${t.play}` : ""}</div>
        </div>
      </div>
      {!open ? <div className="notice"><Status kind={t.status === "done" ? "ok" : "off"}>{t.note || cap(t.status)}</Status></div> : null}
      {linkedin ? (
        <Section title={t.kind === "linkedin_connect" ? "Connection note" : "Message"}
          right={t.linkedin_url ? <a className="btn quiet sm" href={t.linkedin_url} target="_blank" rel="noreferrer noopener">Open profile <ArrowSquareOut size={12} /></a> : null}>
          {t.draft !== null ? (
            <>
              <textarea className="input" rows={t.kind === "linkedin_connect" ? 4 : 6} value={body} disabled={!open}
                onChange={(e) => setText(e.target.value)} aria-label="Note to send" />
              <div className="actions" style={{ justifyContent: "space-between", marginTop: 8 }}>
                <span className={over ? "small" : "mute small"} style={over ? { color: "var(--stop)" } : undefined}>
                  {t.max_chars ? `${body.length} of ${t.max_chars} characters` : `${body.length} characters`}{text !== null ? ", edited: checked again when you send" : ""}
                </span>
                <button className="btn quiet sm" onClick={copy}>Copy</button>
              </div>
              {failures.length ? (
                <div className="ledger" style={{ marginTop: 12 }}>
                  {failures.map((f: any, i: number) => <div key={i} className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}><Status kind="stop">{f.message}</Status></div>)}
                </div>
              ) : null}
            </>
          ) : <Empty title="No note drafted" />}
        </Section>
      ) : null}
      {t.kind === "call" ? (
        <Section title="Number">
          <div className="ledger"><Reach label="Phone" value={t.phone} state={t.phone ? (t.phone_status === "valid" ? ["ok", "Verified"] : ["half", cap(t.phone_status)]) : null} /></div>
        </Section>
      ) : null}
      {t.sources?.length ? (
        <Section title="What it rests on">
          <div className="ledger">
            {t.sources.map((f: any) => (
              <div key={f.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <span style={{ whiteSpace: "normal" }}>{f.text}</span>
                {f.url ? <a className="mute" href={f.url} target="_blank" rel="noreferrer noopener" aria-label="Source"><ArrowSquareOut size={14} /></a> : <span />}
              </div>
            ))}
          </div>
        </Section>
      ) : null}
      {t.kind === "call" && open ? <p className="mute small">If you spoke with them, the desk stops its own steps for them: you are in the conversation now.</p> : null}
    </Frame>
  );
}

/** What happened on LinkedIn, recorded by the SDR: an accepted request, or their message pasted in (it becomes a
 *  reply, so their emails stop first). */
function LinkedInLog({ personId, canAccept, onDone }: { personId: number; canAccept: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, run] = useBusy();
  return (
    <Section title="LinkedIn" right={
      <div className="actions">
        {canAccept ? <button className="btn line sm" disabled={busy} onClick={() => run(async () => { await api(`/api/people/${personId}/linkedin`, { method: "POST", body: { event: "accepted" } }); onDone(); }, "Recorded.")}>They accepted</button> : null}
        <button className="btn line sm" onClick={() => setOpen(!open)}>{open ? "Cancel" : "They wrote back"}</button>
      </div>}>
      {open ? (
        <>
          <textarea className="input" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste their message" aria-label="Their LinkedIn message" />
          <div className="actions" style={{ justifyContent: "flex-end", marginTop: 8 }}>
            <button className="btn sm" disabled={busy || !text.trim()} onClick={() => run(async () => {
              const r = await api<any>(`/api/people/${personId}/linkedin`, { method: "POST", body: { event: "reply", text } });
              setOpen(false); setText(""); onDone();
              if (r.reply_id) openSheet("reply", r.reply_id);
            }, "Saved as a reply. Their emails are paused.")}>Save as a reply</button>
          </div>
        </>
      ) : <p className="mute small" style={{ margin: 0 }}>An accepted request is recorded and pauses nothing. A message from them is a reply: their emails stop first.</p>}
    </Section>
  );
}

/** Who gets what next in the current play, person by person: the account calendar the desk keeps. */
function Calendar({ rows }: { rows: any[] }) {
  const byPerson = new Map<string, any[]>();
  for (const r of rows) byPerson.set(r.full_name, [...(byPerson.get(r.full_name) || []), r]);
  return (
    <div className="section">
      <h2 style={{ fontSize: 13.5 }}>Calendar</h2>
      <div className="ledger">
        {[...byPerson.entries()].map(([name, steps]) => {
          const e = steps[0];
          const sent = steps.filter((x) => x.status === "sent").length;
          const next = e.state === "active" && e.next_at ? (ahead(e.next_at) === "due" ? "due now" : ahead(e.next_at)) : null;
          return (
            <div key={name} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }}>
              <Avatar name={name} photo={e.photo_url} />
              <div className="cell-main"><span className="t">{name}</span><span className="s">{sent ? `${sent} sent` : "Nothing sent yet"}{next ? `, step ${e.step_index + 1} ${next}` : ""}</span></div>
              <Status kind={(ENROLL[e.state] || ["off"])[0]}>{(ENROLL[e.state] || ["off", cap(e.state)])[1]}</Status>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LogMeeting({ accountId, people, onDone }: { accountId: number; people: any[]; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState("");
  const [when, setWhen] = useState("");
  const [busy, run] = useBusy();
  if (!open) return <button className="btn quiet sm" onClick={() => setOpen(true)}>Log a meeting</button>;
  return (
    <div className="actions" style={{ flexWrap: "wrap", width: "100%" }}>
      <select className="select" style={{ width: 200 }} value={who} onChange={(e) => setWho(e.target.value)} aria-label="With whom">
        <option value="">With whom</option>
        {people.filter((p: any) => p.status === "active").map((p: any) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
      </select>
      <input className="input" type="datetime-local" style={{ width: 210 }} value={when} onChange={(e) => setWhen(e.target.value)} aria-label="When" />
      <button className="btn quiet sm" onClick={() => setOpen(false)}>Cancel</button>
      <button className="btn sm" disabled={busy || !when} onClick={() => run(async () => {
        await api(`/api/accounts/${accountId}/meetings`, { method: "POST", body: { person_id: who ? Number(who) : null, starts_at: new Date(when).toISOString() } });
        setOpen(false); onDone();
      }, "Meeting logged. The play's sequences stop.")}>Log it</button>
    </div>
  );
}

function ColleaguesChoice({ replyId }: { replyId: number }) {
  const [busy, run] = useBusy();
  const [done, setDone] = useState<string | null>(null);
  const act = (action: string) => run(async () => {
    const r = await api<any>(`/api/replies/${replyId}/colleagues`, { method: "POST", body: { action } });
    setDone(r.colleagues ? (action === "stop" ? `Stopped ${r.colleagues}.` : `Resumed ${r.colleagues}.`) : "Nobody else was waiting.");
  });
  return (
    <Section title="Their colleagues">
      {done ? <div className="small mute">{done}</div> : (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          <span className="small mute" style={{ flex: 1, minWidth: 200 }}>Paused while you talk. They resume in 3 business days unless you decide now.</span>
          <button className="btn quiet sm" disabled={busy} onClick={() => act("stop")}>Stop them</button>
          <button className="btn line sm" disabled={busy} onClick={() => act("resume_now")}>Resume now</button>
        </div>
      )}
    </Section>
  );
}

/** Put the account on hold: a partner is talking to them, legal asked, the timing is wrong. Nothing sends until then. */
function HoldBox({ accountId, onDone }: { accountId: number; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [busy, run] = useBusy();
  if (!open) return <button className="btn quiet sm" onClick={() => setOpen(true)}>Hold this account</button>;
  return (
    <Section title="Hold this account">
      <div className="form-row">
        <label className="field"><span>Until</span><input className="input" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        <label className="field" style={{ flex: 2 }}><span>Why</span><input className="input" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="A partner is talking to them" /></label>
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn quiet sm" onClick={() => setOpen(false)}>Cancel</button>
        <button className="btn sm" disabled={busy || !until || reason.trim().length < 3} onClick={() => run(async () => {
          await api(`/api/accounts/${accountId}/hold`, { method: "POST", body: { until: new Date(until + "T12:00:00").toISOString(), reason } });
          setOpen(false); onDone();
        }, "On hold. Nothing sends until then.")}>Hold</button>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- meeting

const ATTR: Record<string, string> = { sourced: "Sourced by outbound", influenced: "Influenced by outbound", none: "Not from outbound" };

export function MeetingSheet({ id }: { id: number }) {
  const { data: m, error, reload } = useData<any>(`/api/meetings/${id}`);
  const [notes, setNotes] = useState("");
  const [learn, setLearn] = useState(true);
  const [busy, run] = useBusy();
  if (error) return <Frame crumb="Meeting"><Failed error={error} retry={reload} /></Frame>;
  if (!m) return <Frame crumb="Meeting"><Loading rows={6} /></Frame>;
  const save = (status: string) => run(async () => {
    await api(`/api/meetings/${id}/status`, { method: "POST", body: { status, notes: notes.trim() || null, learn } });
    setNotes("");
  }, status === "held" ? "Saved." : status === "no_show" ? "Saved. A task to rebook is on Today." : "Cancelled.");
  const open = m.status === "booked";
  return (
    <Frame crumb="Meeting" foot={open ? (
      <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
        <button className="btn quiet sm" disabled={busy} onClick={() => save("cancelled")}>Cancelled</button>
        <button className="btn line sm" disabled={busy} onClick={() => save("no_show")}>They did not show</button>
        <button className="btn sm" disabled={busy} onClick={() => save("held")}>It happened</button>
      </div>
    ) : null}>
      <div className="who">
        <Avatar name={m.full_name || m.company} photo={m.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{m.person_id ? <button className="link-row" onClick={() => openSheet("person", m.person_id)}>{m.full_name}</button> : m.company}</h2>
          <div className="meta clip">{m.person_title ? `${m.person_title} at ` : ""}<button className="link" onClick={() => openSheet("account", m.account_id)}>{m.company}</button>{m.owner ? `, with ${m.owner}` : ""}</div>
        </div>
      </div>
      <div className="figs">
        <Fig value={dayTime(m.starts_at)} label="When" sm />
        <Fig value={<Status kind={m.status === "held" ? "ok" : m.status === "booked" ? "go" : "off"}>{MEETING[m.status] || cap(m.status)}</Status>} label="Status" sm />
        <Fig value={m.source === "inbound" ? "They asked" : m.play ? <button className="fig-link" onClick={() => openSheet("play", m.play_id)}>{m.play}</button> : "Booked by hand"} label="Came from" sm />
      </div>
      <Section title="Call notes">
        {m.notes.length ? (
          <div className="ledger">
            {m.notes.map((n: any) => (
              <div key={n.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
                <div className="cell-main"><span style={{ whiteSpace: "pre-wrap" }}>{n.text}</span><span className="s">{n.by ? `${n.by}, ` : ""}{day(n.created_at)}</span></div>
              </div>
            ))}
          </div>
        ) : null}
        {m.status !== "cancelled" ? (
          <>
            <textarea className="input" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What they said: why they would buy, what worries them, tools they use" aria-label="Call notes" />
            <div className="actions" style={{ justifyContent: "space-between", marginTop: 8 }}>
              <label className="choice"><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} />Learn from these notes</label>
              {!open ? <button className="btn line sm" disabled={busy || !notes.trim()} onClick={() => save(m.status)}>Add notes</button> : null}
            </div>
          </>
        ) : null}
      </Section>
      {m.learnings.length ? (
        <Section title="What the desk learned">
          <div className="ledger">
            {m.learnings.map((l: any, i: number) => (
              <div key={i} className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
                <div className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}>{l.text}</span><span className="s" style={{ whiteSpace: "normal" }}>&ldquo;{l.quote}&rdquo;</span></div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
      <Section title="Deals after it">
        {m.deals.length ? (
          <div className="ledger">
            {m.deals.map((d: any) => (
              <div key={d.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <div className="cell-main"><span className="t">{d.name}</span><span className="s">{d.stage}, {ATTR[d.attribution]}{d.amount_cents != null ? `, ${money(d.amount_cents)}` : ""}</span></div>
                <Status kind={d.won ? "ok" : d.closed_at ? "off" : "go"}>{d.won ? "Won" : d.closed_at ? "Lost" : "Open"}</Status>
              </div>
            ))}
          </div>
        ) : <Empty title="No deal in the CRM yet" />}
      </Section>
    </Frame>
  );
}

const MEETING: Record<string, string> = { booked: "Meeting booked", held: "Meeting held", no_show: "Meeting, they did not show", cancelled: "Meeting cancelled" };

/** Contact that happened outside the desk. Any of it puts the SDR in the conversation: the desk stops its own steps. */
function OutsideContact({ personId, onDone }: { personId: number; onDone: () => void }) {
  const [busy, run] = useBusy();
  const log = (kind: string) => run(async () => { await api(`/api/people/${personId}/activity`, { method: "POST", body: { kind } }); onDone(); },
    "Logged. The desk stops its own steps for them.");
  return (
    <Section title="Talked outside the desk" right={<span className="mute small">The desk stops its own steps for them</span>}>
      <div className="actions" style={{ flexWrap: "wrap" }}>
        <button className="btn line sm" disabled={busy} onClick={() => log("they_called")}>They called me</button>
        <button className="btn line sm" disabled={busy} onClick={() => log("they_emailed")}>They emailed me directly</button>
        <button className="btn line sm" disabled={busy} onClick={() => log("i_emailed")}>I emailed them myself</button>
      </div>
    </Section>
  );
}

/** Erase on request (GDPR Article 17): GTM only, with a second click that says exactly what happens. */
function EraseBox({ personId, name }: { personId: number; name: string }) {
  const me = useData<any>("/api/me").data;
  const [sure, setSure] = useState(false);
  const [busy, run] = useBusy();
  if (me?.user.role !== "gtm") return null;
  return sure ? (
    <div className="notice">
      <span style={{ flex: 1 }}>This deletes {name}, their emails, replies and notes, and keeps only a fingerprint so they are never added again. It cannot be undone.</span>
      <button className="btn quiet sm" onClick={() => setSure(false)}>Cancel</button>
      <button className="btn ink sm" disabled={busy} onClick={() => run(async () => { await api(`/api/people/${personId}/erase`, { method: "POST" }); closeSheet(); }, "Erased.")}>Erase {name}</button>
    </div>
  ) : <div className="actions" style={{ justifyContent: "flex-end" }}><button className="btn quiet sm" onClick={() => setSure(true)}>Erase on request</button></div>;
}

function Reach({ label, value, state }: { label: string; value: ReactNode; state?: [Glyph, string] | null }) {
  return (
    <div className="row" style={{ gridTemplateColumns: "96px minmax(0,1fr) auto" }}>
      <span className="mute">{label}</span>
      <span className="clip">{value || <span className="faint">Not found</span>}</span>
      {state ? <Status kind={state[0]}>{state[1]}</Status> : <span />}
    </div>
  );
}

function ChannelIcon({ channel }: { channel: string }) {
  const Ic = channel === "linkedin" ? LinkedinLogo : channel === "call" ? Phone : channel === "meeting" ? CalendarCheck : EnvelopeSimple;
  return <span className="sig-icon"><Ic size={15} aria-hidden="true" /></span>;
}

// ---------------------------------------------------------------- account

export function AccountSheet({ id }: { id: number }) {
  const { data, error, reload } = useData<any>(`/api/accounts/${id}`);
  // The open tab lives in the URL, so Back from an email opened here returns to this tab.
  const tab = (new URLSearchParams(window.location.search).get("sheet") || "").split(":")[2] || "overview";
  const setTab = (t: string) => {
    const u = new URL(window.location.href);
    u.searchParams.set("sheet", `account:${id}:${t}`);
    navigate(u.pathname + "?" + u.searchParams.toString(), true);
  };
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
        <Fig value={a.owner || cur?.owner || "Unassigned"} label="Owner" sm />
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([k, l, n]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}{n !== undefined ? <span className="n">{n}</span> : null}</button>)}
      </div>
      {tab === "overview" && <AccountOverview d={data} />}
      {tab === "people" && <AccountPeople d={data} />}
      {tab === "signals" && <SignalTimeline signals={data.signals} />}
      {tab === "outreach" && <AccountOutreach d={data} />}
      {cur ? null : data.holds.length ? <Section title={`Rests until ${day(data.holds[0].until)}`}><div className="small mute">{cap(data.holds[0].reason)}</div></Section> : null}
      {tab === "overview" ? <div className="actions" style={{ marginTop: 8 }}><LogMeeting accountId={id} people={data.people} onDone={reload} /><HoldBox accountId={id} onDone={reload} /></div> : null}
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

// One bar per kind of signal: two pricing visits are one reason, pulling harder.
function grouped(contribs: any[]): { label: string; type: string; value: number }[] {
  const m = new Map<string, { label: string; type: string; value: number }>();
  contribs.forEach((c) => {
    const g = m.get(c.type) || { label: c.label, type: c.type, value: 0 };
    g.value += c.value;
    m.set(c.type, g);
  });
  return [...m.values()].sort((a, b) => b.value - a.value);
}

function AccountOverview({ d }: { d: any }) {
  const cur = d.current;
  const max = Math.max(1, ...grouped(d.contributions).map((c) => c.value));
  const fit = (d.account.fit_breakdown?.factors || []) as any[];
  return (
    <>
      {cur ? (
        <Section title="In play" right={<Status kind={PLAY_STATE[cur.state][0]}>{PLAY_STATE[cur.state][1]}</Status>}>
          <div className="small mute">{cur.play}, proposed {ago(cur.proposed_at)}{cur.owner ? `, owned by ${cur.owner}` : ""}</div>
          <WhyNow why={cur.why_now} />
          {d.calendar?.length ? <Calendar rows={d.calendar} /> : null}
          {cur.brief?.findings?.length ? (
            <div className="section">
              <h2 style={{ fontSize: 13.5 }}>Brief</h2>
              <ul className="facts">
                {cur.brief.findings.map((f: any, i: number) => (
                  <li key={i}><span className="id">{i + 1}</span><span>{f.text}</span></li>
                ))}
              </ul>
            </div>
          ) : null}
        </Section>
      ) : d.plays[0]?.state === "held_out" ? (
        <Section title="Held back"><div className="mute">Matched {d.plays[0].play} on {day(d.plays[0].proposed_at)}. Not contacted, on purpose.</div></Section>
      ) : null}
      <Section title="What moves the score">
        {d.contributions.length ? (
          <div className="bars">
            {grouped(d.contributions).slice(0, 7).map((c: any) => <Bar key={c.type} label={<SignalLabel type={c.type} label={c.label} />} value={c.value} of={max} shown={c.value.toFixed(1)} />)}
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
      <button key={p.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }} onClick={() => openSheet("person", p.id)}>
        <Avatar name={p.full_name} photo={p.photo_url} />
        <div className="cell-main">
          <span className="t">{p.full_name}{p.is_champion ? <span className="mute small"> &middot; past champion</span> : null}</span>
          <span className="s">{p.title}{p.persona_key && !(p.title || "").toLowerCase().includes((PERSONA[p.persona_key] || "").toLowerCase()) ? `, ${PERSONA[p.persona_key] || p.persona_key}` : ""}</span>
        </div>
        {e ? <Status kind={GOOD_STOPS.has(p.stop_reason) ? "ok" : e[0]}>{p.enrollment === "stopped" || p.enrollment === "paused" ? stopWord(p.stop_reason || p.pause_reason) || e[1] : e[1]}</Status>
          : p.status !== "active" ? <Status kind="off">{cap(p.status)}</Status> : <span className="mute small">{p.email_status === "valid" ? "Verified email" : ""}</span>}
      </button>
    );
  };
  return (
    <>
      <Section title="Buying committee">
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
      <Section title="Others at the company">
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
          <SignalIcon type={s.type_key} />
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
      <Section title="Emails">
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
      <Section title="Replies">
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
              <button key={m.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet("meeting", m.id)}>
                <div className="cell-main"><span className="t">{m.full_name || "Meeting"}</span><span className="s">{dayTime(m.starts_at)}</span></div>
                <Status kind={m.status === "held" ? "ok" : m.status === "booked" ? "go" : "off"}>{cap(m.status === "no_show" ? "no show" : m.status)}</Status>
              </button>
            ))}
          </div>
        </Section>
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------- an email to approve

function sentenceKind(k: string) { return k === "claim" ? "claim" : ""; }

// After a decision, the next email waiting for this person opens; with none left, the panel closes.
async function nextEmail(done: number) {
  const t = await api<any>("/api/today");
  const next = (t.approvals || []).find((m: any) => m.id !== done);
  const u = new URL(window.location.href);
  if (next) {
    u.searchParams.set("sheet", `message:${next.id}`);
    u.searchParams.delete("from");
    navigate(u.pathname + "?" + u.searchParams.toString(), true);
  } else {
    closeSheet();
  }
}

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
    await nextEmail(id);
  }, "Approved. It goes out in their send window.");
  const reject = () => run(async () => {
    await api(`/api/messages/${id}/reject`, { method: "POST", body: { reason } });
    await nextEmail(id);
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
  ) : m.status === "send_unknown" ? (
    <>
      <span className="mute small" style={{ flex: 1 }}>The mail provider never said. Check the mailbox's sent folder.</span>
      <button className="btn line" disabled={busy} onClick={() => run(() => api(`/api/messages/${id}/outcome`, { method: "POST", body: { sent: false } }), "Recorded. It goes out again in their window.")}>It is not there</button>
      <button className="btn" disabled={busy} onClick={() => run(() => api(`/api/messages/${id}/outcome`, { method: "POST", body: { sent: true } }), "Recorded as sent.")}>It went out</button>
    </>
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
      <Section title="What it rests on">
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
      </Section>
      {lastAttempt && m.attempts.length > 1 && m.gate?.passed ? (
        <div className="small mute">First draft: {(lastAttempt.failures || []).map((f: any) => f.message.toLowerCase()).join("; ")}. Rewritten once.</div>
      ) : null}
      <WhyNow why={m.why_now} />
    </Frame>
  );
}

// ---------------------------------------------------------------- a reply

export function ReplySheet({ id }: { id: number }) {
  const { data: r, error, reload } = useData<any>(`/api/replies/${id}`);
  const [busy, run] = useBusy();
  const [label, setLabel] = useState("");
  const [booking, setBooking] = useState(false);
  const [when, setWhen] = useState("");
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
        {booking ? (
          <>
            <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="When the meeting is" style={{ width: 220 }} />
            <button className="btn quiet" onClick={() => setBooking(false)}>Cancel</button>
            <button className="btn" disabled={busy || !when} onClick={() => act({ outcome: "meeting_booked", meeting_at: new Date(when).toISOString() }, "Meeting booked. The rest of the sequence stops.")}>Book it</button>
          </>
        ) : (
          <>
            <button className="btn line" disabled={busy} onClick={() => act({ outcome: "answered" }, "Marked answered.")}>I answered</button>
            <button className="btn" disabled={busy} onClick={() => setBooking(true)}>Meeting booked</button>
          </>
        )}
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
        <Fig value={<Status kind={l[0]}>{l[1]}</Status>} label="What it says" sm />
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
            <dt>Email</dt><dd>{ex.referral.email || <span className="mute">Not in the reply; the desk looks it up and enrolls them if it can</span>}</dd></dl>
        </Section>
      ) : null}
      {r.hot && r.account_id ? <ColleaguesChoice replyId={id} /> : null}
      {ex.suggested && open ? (
        <Section title="A reply you could send" right={<button className="btn quiet sm" onClick={() => { navigator.clipboard?.writeText(ex.suggested); toast("Copied. Paste it into your own inbox."); }}>Copy</button>}>
          <div className="quote ours">{ex.suggested}</div>
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
  const signalNames: Record<string, string> = Object.fromEntries(((useData<any>("/api/settings").data?.signal_types) || [])
    .map((t: any) => [t.key, t.label]));
  const me = useData<any>("/api/me").data;
  const [busy, run] = useBusy();
  const [limits, setLimits] = useState<Record<string, number> | null>(null);
  if (error) return <Frame crumb="Play"><Failed error={error} retry={reload} /></Frame>;
  const p = data?.plays.find((x: any) => x.id === id);
  if (!p) return <Frame crumb="Play"><Loading rows={8} /></Frame>;
  const f = p.funnel, lift = p.lift, promo = p.promotion;
  const isManager = me?.user.role === "manager";
  const change = (body: any, msg: string) => run(() => api(`/api/plays/${id}`, { method: "POST", body }), msg);
  const isAuthor = me?.user.id === p.created_by;
  const foot = me && me.user.role !== "sdr" ? (
    <>
      {me.user.role === "gtm" ? <button className="btn line" onClick={() => openSheet("playedit", id)}>Edit</button> : null}
      {p.status === "live" ? <button className="btn line" disabled={busy} onClick={() => change({ status: "paused", reason: "Paused from the desk" }, "Paused. Nothing new is proposed.")}>Pause</button>
        : p.status === "draft" ? (isManager && !isAuthor ? <button className="btn" disabled={busy || !limits} onClick={() => change({ status: "live", reason: "Launched after the cost card", monthly_cap: limits }, "Launched, with its monthly cap.")}>Launch</button>
          : <span className="mute small">{isAuthor ? "A manager launches it" : "Waiting for a manager"}</span>)
        : <button className="btn line" disabled={busy || !isManager} onClick={() => change({ status: "live", reason: "Resumed from the desk" }, "Live again.")}>Resume</button>}
      {promo.next && p.status !== "draft" ? <button className="btn" disabled={busy || !promo.ready || !isManager} title={!isManager ? "A manager approves a promotion" : undefined}
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
        {p.status === "draft" ? null : <>
          <Fig value={p.median_hours_to_first_touch ? `${Math.round(p.median_hours_to_first_touch)} h` : "None yet"} label="Signal to first email" sm />
          {p.pipeline_cents !== undefined ? <Fig value={money(p.pipeline_cents)} label="Pipeline sourced" sm /> : null}</>}
      </div>
      {p.status === "draft" ? null : <Section title="Accounts">
        <div className="funnel">
          <Bar label="Proposed" value={f.proposed} of={f.proposed} />
          <Bar label="Accepted" value={f.accepted} of={f.proposed} hint={pct(f.proposed ? f.accepted / f.proposed : 0)} />
          <Bar label="Emailed" value={f.contacted} of={f.proposed} hint={pct(f.proposed ? f.contacted / f.proposed : 0)} />
          <Bar label="Replied" value={f.replied} of={f.proposed} hint={pct(f.proposed ? f.replied / f.proposed : 0)} />
          <Bar label="Positive reply" value={f.positive} of={f.proposed} hint={pct(f.proposed ? f.positive / f.proposed : 0)} tone="accent" />
          <Bar label="Meeting" value={f.meetings} of={f.proposed} hint={pct(f.proposed ? f.meetings / f.proposed : 0)} tone="accent" />
        </div>
      </Section>}
      {p.status === "draft" ? null : <><Section title="Meetings: contacted against held back"><LiftBlock lift={lift} /></Section>
      <PlayAccounts id={id} /></>}
      <Section title="Trigger">
        <dl className="kv">
          <dt>Signals</dt><dd style={{ display: "grid", gap: 6 }}>{p.trigger.any_of.map((k: string) => <SignalLabel key={k} type={k} label={signalNames[k] || cap(k)} />)}</dd>
          <dt>Fit tiers</dt><dd>{p.trigger.fit_tiers.join(" and ")}</dd>
          <dt>Priority from</dt><dd>{p.trigger.min_priority}</dd>
          <dt>Signal age</dt><dd>Within {p.trigger.within_days} days</dd>
          <dt>Who</dt><dd>{p.personas.map((x: string) => PERSONA[x] || x).join(", ")}, up to {p.max_people}</dd>
          <dt>Held back</dt><dd>{p.holdout_pct}% of matched accounts</dd>
        </dl>
      </Section>
      <Section title="Sequence">
        <div className="ledger">
          {p.sequence.map((s: any, i: number) => (
            <div key={i} className="row" style={{ gridTemplateColumns: "56px minmax(0,1fr) auto", minHeight: 36 }}>
              <span className="mute">Day {s.day}</span>
              <span>{STEP[s.channel] || cap(s.channel)}{s.job !== s.channel ? `, ${cap(s.job).toLowerCase()}` : ""}</span>
              <span className="mute small">{s.by === "desk" ? "The desk sends" : "SDR task"}</span>
            </div>
          ))}
        </div>
      </Section>
      {p.status === "draft" ? <DraftPreview p={p} onCost={(c) => { if (!limits && c) setLimits(defaultCap(c)); }} /> : null}
      {p.status === "draft" && isManager && !isAuthor && limits ? <CapForm limits={limits} setLimits={setLimits} /> : null}
      {p.status !== "draft" && p.cap_use?.length ? <CapUse rows={p.cap_use} /> : null}
      {promo.next && p.status !== "draft" ? (
        <Section title={`Before: ${STAGE[promo.next]}`}>
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

function DraftPreview({ p, onCost }: { p: any; onCost?: (c: any) => void }) {
  const [pv, setPv] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const body = { name: p.name, hypothesis: p.hypothesis, angle: p.angle, personas: p.personas, max_people: p.max_people,
      holdout_pct: p.holdout_pct, urgent: p.urgent, latency_hours: p.latency_hours, sequence: p.sequence, trigger: p.trigger };
    api<any>("/api/play-preview", { method: "POST", body }).then((r) => { setPv(r); onCost?.(r.cost); }).catch((e) => setErr(e.message));
  }, [p.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return <PlayPreview pv={pv} error={err} />;
}

const CAP_NAMES: Record<string, [string, string]> = {
  people_search: ["People search", "credits"], email_finder: ["Email finder", "credits"],
  email_verifier: ["Email verification", "credits"], phone_finder: ["Phone finder", "credits"], anthropic_cents: ["AI", "cents"],
};

/** The cost card's worst case a month, rounded up, as the starting cap. The manager can lower or raise it. */
function defaultCap(c: any): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(c.per_month.credits as Record<string, number>)) if (v > 0) out[k] = Math.ceil(v);
  out.anthropic_cents = Math.max(100, Math.ceil(c.per_month.ai_dollars * 100));
  return out;
}

function CapForm({ limits, setLimits }: { limits: Record<string, number>; setLimits: (c: Record<string, number>) => void }) {
  return (
    <Section title="Monthly cap" right={<span className="mute small">Starts at the worst case above. At the cap the play takes no new accounts until next month.</span>}>
      <div className="ledger">
        {Object.entries(limits).map(([k, v]) => (
          <div key={k} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 120px 70px" }}>
            <span>{CAP_NAMES[k]?.[0] || k}</span>
            <input className="input num" inputMode="numeric" value={v} aria-label={`${CAP_NAMES[k]?.[0] || k} cap`}
              onChange={(e) => setLimits({ ...limits, [k]: Math.max(0, Number(e.target.value.replace(/\D/g, "")) || 0) })} />
            <span className="mute small">{CAP_NAMES[k]?.[1]}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

function CapUse({ rows }: { rows: any[] }) {
  return (
    <Section title="This month against its cap">
      <div className="ledger">
        {rows.map((r: any) => (
          <div key={r.key} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(140px,1.4fr)" }}>
            <span>{CAP_NAMES[r.key]?.[0] || r.key}</span>
            <Bar label="" value={r.used} of={Math.max(r.cap, 1)} shown={`${n0(r.used)} of ${n0(r.cap)}`} hint={CAP_NAMES[r.key]?.[1]} tone={r.used >= r.cap ? "accent" : undefined} />
          </div>
        ))}
      </div>
    </Section>
  );
}

function PlayAccounts({ id }: { id: number }) {
  const { data } = useData<any>(`/api/plays/${id}/accounts`);
  if (!data?.accounts?.length) return null;
  return (
    <Section title="Accounts">
      <div className="ledger">
        {data.accounts.slice(0, 40).map((a: any) => {
          const st = PLAY_STATE[a.state];
          return (
            <button key={a.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }} onClick={() => openSheet("account", a.account_id)}>
              <Logo domain={a.primary_domain} name={a.name} />
              <div className="cell-main"><span className="t">{a.name}</span><span className="s">{a.owner || "Unassigned"}, {day(a.proposed_at)}</span></div>
              <Status kind={st[0]}>{st[1]}</Status>
            </button>
          );
        })}
      </div>
    </Section>
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
        <div className="figs">
          <Fig value={`${lift.difference >= 0 ? "+" : ""}${pct(lift.difference, 1)}`} label="Difference" sm />
          <Fig value={`${pct(lift.interval[0], 1)} to ${pct(lift.interval[1], 1)}`} label="Likely range" sm />
        </div>
      ) : (
        <div className="figs">
          <Fig value="Too few to compare" label="Yet" sm />
          <Fig value={n0(lift.still_needed.holdout)} label="More held back needed" sm />
        </div>
      )}
    </div>
  );
}

export { withParam };
