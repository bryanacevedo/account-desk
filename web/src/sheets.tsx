import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowSquareOut, Buildings, CalendarCheck, ChatCircleText, CheckSquare, EnvelopeSimple, Lightbulb, LinkedinLogo, ListChecks, Phone, UserCircle, X } from "@phosphor-icons/react";
import { api } from "./api";
import { Avatar, Logo } from "./marks";
import { SignalIcon, SignalLabel } from "./signalIcons";
import { PlayEditor, PlayPreview } from "./PlayEditor";
import { ElsewhereAccount, ElsewherePerson, keptBy, useIntegration } from "./elsewhere";
import {
  Bar, Empty, Seg, Failed, Fig, Loading, Section, Status, ago, ahead, cap, day, dayTime, late, money, n0, navigate, pct,
  safeUrl, toast, useBusy, useData, useNowIso, withParam, type Glyph,
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

/** Each kind of panel has its own mark: an icon and a quiet tint, so a glance tells an account from a reply. */
const KIND: Record<string, { label: string; icon: typeof X; tone: string }> = {
  account: { label: "Account", icon: Buildings, tone: "account" },
  person: { label: "Person", icon: UserCircle, tone: "person" },
  email: { label: "Email", icon: EnvelopeSimple, tone: "email" },
  reply: { label: "Reply", icon: ChatCircleText, tone: "reply" },
  call: { label: "Call", icon: Phone, tone: "call" },
  linkedin: { label: "LinkedIn", icon: LinkedinLogo, tone: "linkedin" },
  task: { label: "Task", icon: CheckSquare, tone: "task" },
  meeting: { label: "Meeting", icon: CalendarCheck, tone: "meeting" },
  play: { label: "Play", icon: ListChecks, tone: "play" },
  suggestion: { label: "Suggested play", icon: Lightbulb, tone: "suggestion" },
};
const kindOf = (crumb: ReactNode): string => {
  const w = typeof crumb === "string" ? crumb.toLowerCase() : "";
  if (w.includes("play")) return "play";
  return Object.keys(KIND).find((k) => w.startsWith(k)) || "task";
};

function Frame({ crumb, children, foot, kind }: { crumb: ReactNode; children: ReactNode; foot?: ReactNode; kind?: string }) {
  const k = KIND[kind || kindOf(crumb)];
  const KIcon = k.icon;
  const detail = typeof crumb === "string" && crumb.toLowerCase() === k.label.toLowerCase() ? null : crumb;
  const from = new URLSearchParams(window.location.search).get("from");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeSheet(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus?.({ focusVisible: false } as FocusOptions); };
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
      <aside className={`sheet kind-${k.tone}`} role="dialog" aria-modal="true" aria-label={k.label} tabIndex={-1} ref={ref}>
        <div className="sheet-top">
          {from ? <button className="iconbtn" onClick={back} aria-label="Back"><ArrowLeft size={18} /></button> : null}
          <div className="sheet-kind"><span className="kind-mark" aria-hidden="true"><KIcon size={15} weight="bold" /></span>{k.label}</div>
          <div className="crumb clip">{detail}</div>
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
  if (kind === "suggestion") return <SuggestionSheet key={key} id={Number(id)} />;
  if (kind === "playedit") {
    const from = id === "new" && params.get("suggestion") ? Number(params.get("suggestion")) : null;
    return <Frame key={key + (from ?? "")} crumb={id === "new" ? (from ? "New play, from a suggestion" : "New play") : "Edit play"}>
      <PlayEditor id={id === "new" ? null : Number(id)} fromSuggestion={from} /></Frame>;
  }
  return null;
}

// ---------------------------------------------------------------- shared vocab

export const PLAY_STATE: Record<string, [Glyph, string]> = {
  proposed: ["wait", "Proposed"], accepted: ["half", "Accepted"], researching: ["half", "Researching"],
  approving: ["wait", "Drafts to approve"], active: ["go", "Reaching out"], engaged: ["ok", "Replied"],
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
  not_interested: "Not interested", not_now: "Not now", wrong_person: "Wrong person", left_company: "Left the company",
  approval_lapsed: "Approval came too late", rep_in_conversation: "SDR talking to them", colleague_engaged: "Colleague talking to us", person_moved: "Changed jobs", referral: "Referred someone",
  reply_received: "Replied, reading it", account_reply: "Colleague replied", out_of_office: "Out of office",
};
export const stopWord = (r: string | null) => {
  if (!r) return "";
  if (STOP[r]) return STOP[r];
  if (r.startsWith("rejected")) return "Draft rejected";
  if (r.startsWith("gate:") || r.startsWith("refused")) return "Blocked by a contact rule";
  if (r.startsWith("play_")) return "Play ended";
  return cap(r);
};
export const GOOD_STOPS = new Set(["replied_positive", "meeting_booked", "referral"]);

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
  const tool = useData<any>("/api/me").data?.linkedin_tool;
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
      <div className="figs">
        <Fig value={n0(data.touches.filter((x: any) => x.direction === "out").length)} label="Reached out" sm />
        <Fig value={n0(data.replies.length)} label="Replies" sm />
        <Fig value={data.touches.length ? ago(data.touches[0].at) : "Never"} label="Last contact" sm />
      </div>
      {data.suppressed.length ? (
        <div className="notice"><Status kind="stop">Do not contact</Status><span className="mute">{data.suppressed.map((x: any) => x.reason).join(", ")}</span></div>
      ) : null}
      <Section title="How to reach them">
        <div className="ledger">
          <Reach label="Email" value={p.email ? <span title={p.email_found_by ? `Found by ${cap(p.email_found_by)}${p.email_confidence ? `, ${Math.round(p.email_confidence * 100)}% sure` : ""}` : undefined}>{p.email}</span> : null}
            state={p.email ? (p.email_status === "valid" ? ["ok", "Verified"] : p.email_status === "invalid" ? ["stop", "Bounced"]
              : p.email_status === "catch_all" ? ["hold", "Cannot be confirmed"] : ["half", cap(p.email_status)]) : null} />
          <Reach label="Phone" value={p.phone ? <>{p.phone}{p.phone_type && p.phone_type !== "unknown" ? <span className="mute">, {p.phone_type}</span> : null}</> : null}
            state={p.phone ? (p.phone_dnc ? ["stop", "Do not call"] : p.phone_status === "valid" ? ["ok", "Verified"] : ["half", cap(p.phone_status)]) : null} />
          <Reach label="LinkedIn" value={safeUrl(p.linkedin_url) ? <a href={safeUrl(p.linkedin_url)} target="_blank" rel="noreferrer noopener">Profile <ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a> : null}
            state={data.touches.some((x: any) => x.kind === "linkedin_accepted") ? ["ok", "Connected"] : data.touches.some((x: any) => x.kind === "linkedin_connect") ? ["wait", "Request sent"] : null} />
          {p.status !== "active" ? <Reach label="Status" value={cap(p.status)} /> : null}
          {p.role_started_at ? <Reach label="In role" value={`Since ${day(p.role_started_at)}`} /> : null}
          {p.departments?.length ? <Reach label="Team" value={p.departments.map((x: string) => cap(x)).join(", ")} /> : null}
          {p.city ? <Reach label="Based in" value={`${p.city}${p.timezone ? `, ${p.timezone.split("/").pop()?.replace(/_/g, " ")} time` : ""}`} /> : null}
          {p.linkedin_url ? <LinkedInLog personId={p.id} canAccept={!tool && data.touches.some((x: any) => x.kind === "linkedin_connect") && !data.touches.some((x: any) => x.kind === "linkedin_accepted")} onDone={reload} /> : null}
        </div>
      </Section>
      {data.waiting.length ? (
        <Section title="Waiting">
          <div className="ledger">
            {data.waiting.map((w: any) => (
              <button key={w.kind + w.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet(w.kind === "task" ? "task" : "message", w.id)}>
                <span className="cell-main"><span className="t">{w.label.replace(/ \(.*\)$/, "")}</span></span>
                <span className="mute small num">{ago(w.at)}</span>
              </button>
            ))}
          </div>
        </Section>
      ) : null}
      <Section title="Plays">
        {data.enrollments.length ? (
          <div className="ledger">
            {data.enrollments.map((e: any) => {
              const st = ENROLL[e.state] || ["off", cap(e.state)];
              const word = e.state === "stopped" || e.state === "paused" ? stopWord(e.stop_reason || e.pause_reason) || st[1] : st[1];
              const theirs = e.meeting && e.meeting.person_id === p.id;
              const colleague = e.stop_reason === "meeting_booked" && e.meeting && !theirs;
              const sub = e.state === "active" && e.next_at
                ? `Step ${e.step_index + 1} of ${e.sequence.length}, ${ahead(e.next_at) === "overdue" ? late(e.next_at).toLowerCase() : `next ${ahead(e.next_at)}`}`
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
                      <span className="s">{h.t.subject ? `${h.t.subject}, Email ${h.t.email_no ?? h.t.step_index + 1}` : ""}</span>
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
      <ElsewherePerson p={p} />
      <EraseBox personId={p.id} name={p.full_name} />
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
          right={safeUrl(t.linkedin_url) ? <a className="btn quiet sm" href={safeUrl(t.linkedin_url)} target="_blank" rel="noreferrer noopener">Open profile <ArrowSquareOut size={12} /></a> : null}>
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
        <>
          <Section title="Phone">
            <div className="ledger"><Reach label={t.phone_type && t.phone_type !== "unknown" ? cap(t.phone_type) : "Number"}
              value={t.phone && !t.phone_dnc ? <a className="tap" href={`tel:${t.phone.replace(/[^+\d]/g, "")}`}>{t.phone}</a> : t.phone}
              state={t.phone ? (t.phone_dnc ? ["stop", "Do not call"] : t.phone_status === "valid" ? ["ok", "Verified"] : ["half", cap(t.phone_status)]) : null} /></div>
            {t.note ? <div className="small mute">{t.note}</div> : null}
            {t.call_hours ? <div className="small mute">{t.dnc_register ? `Screened against ${t.dnc_register}. ` : ""}Calling hours: {t.call_hours} their time, weekdays.</div> : null}
          </Section>
          {t.why ? (
            <Section title="Why now">
              <div className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}>{t.why.summary}</span>
                <span className="s">{t.why.label}, {day(t.why.observed_at)}</span></div>
            </Section>
          ) : null}
          <Section title="So far">
            {t.so_far.length ? (
              <div className="ledger">
                {t.so_far.map((m: any) => (
                  <div key={m.step_index} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                    <span className="cell-main"><span className="t">{m.channel === "email" ? `Email ${m.email_no ?? m.step_index + 1}` : cap(m.channel)}</span>
                      {m.subject ? <span className="s clip">{m.subject}</span> : null}</span>
                    <span className="mute small num">{day(m.sent_at)}</span>
                  </div>
                ))}
              </div>
            ) : <span className="small mute">Nothing sent to them yet. This call is the first touch.</span>}
          </Section>
        </>
      ) : null}
      {t.sources?.length ? (
        <Section title="Facts cited">
          <div className="ledger">
            {t.sources.map((f: any) => (
              <div key={f.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <span style={{ whiteSpace: "normal" }}>{f.text}</span>
                {safeUrl(f.url) ? <a className="mute" href={safeUrl(f.url)} target="_blank" rel="noreferrer noopener" aria-label="Source"><ArrowSquareOut size={14} /></a> : <span />}
              </div>
            ))}
          </div>
        </Section>
      ) : null}
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
    <div className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
      {open ? (
        <div style={{ display: "grid", gap: 8 }}>
          <textarea className="input" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste their LinkedIn message" aria-label="Their LinkedIn message" />
          <div className="actions" style={{ justifyContent: "flex-end" }}>
            <button className="btn quiet sm" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn sm" disabled={busy || !text.trim()} onClick={() => run(async () => {
              const r = await api<any>(`/api/people/${personId}/linkedin`, { method: "POST", body: { event: "reply", text } });
              setOpen(false); setText(""); onDone();
              if (r.reply_id) openSheet("reply", r.reply_id);
            }, "Saved as a reply. Their emails are paused.")}>Save as a reply</button>
          </div>
        </div>
      ) : (
        <div className="actions" style={{ justifyContent: "flex-end" }}>
          {canAccept ? <button className="btn line sm" disabled={busy} onClick={() => run(async () => { await api(`/api/people/${personId}/linkedin`, { method: "POST", body: { event: "accepted" } }); onDone(); }, "Recorded.")}>They accepted on LinkedIn</button> : null}
          <button className="btn line sm" onClick={() => setOpen(true)}>They wrote on LinkedIn</button>
        </div>
      )}
    </div>
  );
}

function Calendar({ rows }: { rows: any[] }) {
  const byPerson = new Map<string, any[]>();
  for (const r of rows) byPerson.set(r.full_name, [...(byPerson.get(r.full_name) || []), r]);
  return (
    <div className="section">
      <h2 style={{ fontSize: 13.5 }}>People in this play</h2>
      <div className="ledger">
        {[...byPerson.entries()].map(([name, steps]) => {
          const e = steps[0];
          const sent = steps.filter((x) => x.status === "sent").length;
          const next = e.state === "active" && e.next_at ? (ahead(e.next_at) === "overdue" ? late(e.next_at).toLowerCase() : ahead(e.next_at)) : null;
          return (
            <button key={name} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }} onClick={() => openSheet("person", e.person_id)}>
              <Avatar name={name} photo={e.photo_url} />
              <div className="cell-main"><span className="t">{name}</span><span className="s">{sent ? `${sent} sent` : "Nothing sent yet"}{next ? `, ${e.sequence?.[e.step_index] ? stepLabel(e.sequence[e.step_index], e.step_index, e.sequence) : `Email ${e.step_index + 1}`} ${next}` : ""}</span></div>
              <Status kind={GOOD_STOPS.has(e.stop_reason) ? "ok" : (ENROLL[e.state] || ["off"])[0]}>{(e.state === "stopped" || e.state === "paused") ? stopWord(e.stop_reason || e.pause_reason) || ENROLL[e.state][1] : (ENROLL[e.state] || ["off", cap(e.state)])[1]}</Status>
            </button>
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
    <Section title="Log a meeting">
      <div className="form-row">
        <label className="field"><span>With</span>
          <select className="select" value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Someone at the company</option>
            {people.filter((p: any) => p.status === "active").map((p: any) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select></label>
        <label className="field"><span>When</span><input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></label>
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
      <button className="btn quiet sm" onClick={() => setOpen(false)}>Cancel</button>
      <button className="btn sm" disabled={busy || !when} onClick={() => run(async () => {
        await api(`/api/accounts/${accountId}/meetings`, { method: "POST", body: { person_id: who ? Number(who) : null, starts_at: new Date(when).toISOString() } });
        setOpen(false); onDone();
      }, "Meeting logged. The play's sequences stop.")}>Log it</button>
      </div>
    </Section>
  );
}

function ColleaguesChoice({ replyId, count }: { replyId: number; count: number }) {
  const [busy, run] = useBusy();
  const [done, setDone] = useState<string | null>(null);
  const act = (action: string) => run(async () => {
    const r = await api<any>(`/api/replies/${replyId}/colleagues`, { method: "POST", body: { action } });
    const who = `${r.colleagues} colleague${r.colleagues === 1 ? "" : "s"}`;
    setDone(r.colleagues ? (action === "stop" ? `Stopped ${who}.` : `Resumed ${who}.`) : "Nobody else was waiting.");
  });
  return (
    <Section title="Their colleagues">
      {done ? <div className="small mute">{done}</div> : (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          <span className="small mute" style={{ flex: 1, minWidth: 200 }}>{count === 1 ? "One colleague is" : `${count} colleagues are`} paused while you talk. They resume in 3 business days unless you decide now.</span>
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
        <label className="field"><span>Why</span><input className="input" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="A partner is in touch" /></label>
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

// ---------------------------------------------------------------- the email, as it arrives

/** The body without its signature and footer (both are drawn by MailPreview). */
function bodyOnly(body: string): string {
  const main = body.split("\n\n--\n")[0];
  const parts = main.split("\n\n");
  return parts.length > 2 ? parts.slice(0, -1).join("\n\n") : main;
}

function signatureOf(body: string): string[] {
  const parts = body.split("\n\n--\n")[0].split("\n\n");
  return parts.length > 2 ? parts[parts.length - 1].split("\n") : [];
}

/** A plain-text email shown the way a mail client shows it: who it is from and to, the subject, the body, the
 *  signature, and the legal footer set small and quiet. Links in the footer stay real links. */
function MailPreview({ m, footer, children }: { m: any; footer?: string; children: ReactNode }) {
  const sig = signatureOf(m.body);
  const lines = (footer || "").split("\n").filter(Boolean);
  const link = (text: string) => {
    const url = text.match(/https?:\/\/\S+/)?.[0];
    if (!url) return text;
    const [before, after] = text.split(url);
    return <>{before}<a href={url} target="_blank" rel="noreferrer noopener">{url.replace(/^https?:\/\//, "")}</a>{after}</>;
  };
  return (
    <div className="mail">
      <div className="mail-head">
        <div className="mail-row"><span className="k">From</span><span className="v clip">{m.owner || "The SDR"}{m.mailbox ? <span className="mute"> &lt;{m.mailbox}&gt;</span> : null}</span></div>
        <div className="mail-row"><span className="k">To</span><span className="v clip">{m.full_name}{m.email ? <span className="mute"> &lt;{m.email}&gt;</span> : null}</span></div>
        <div className="mail-subject">{m.subject || "(no subject)"}</div>
      </div>
      <div className="mail-body">
        {children}
        {sig.length ? <div className="mail-sig">{sig.map((l, i) => <div key={i} className={i === 0 ? "name" : ""}>{l}</div>)}</div> : null}
      </div>
      {lines.length ? <div className="mail-foot">{lines.map((l, i) => <div key={i}>{link(l)}</div>)}</div> : null}
    </div>
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
  const open = m.status === "booked" && new Date(m.starts_at).getTime() <= useNowIso();
  // What the desk added: learnings that are not already the notes' own words, shown above.
  const said = m.notes.map((n: any) => n.text).join(" ");
  const added = m.learnings.filter((l: any) => !said.includes(l.text));
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
              <label className="choice"><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} />Use these notes for play suggestions</label>
              {!open ? <button className="btn line sm" disabled={busy || !notes.trim()} onClick={() => save(m.status)}>Add notes</button> : null}
            </div>
          </>
        ) : null}
      </Section>
      {added.length ? (
        <Section title="What the desk learned">
          <div className="ledger">
            {added.map((l: any, i: number) => (
              <div key={i} className="row" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
                <div className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}>{l.text}</span></div>
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

/** The same step names as the play editor. */
/** A step's name, the same everywhere: an email by its number (as Approvals names it), anything else by what it is. */
export function stepLabel(step: any, index: number, sequence?: any[]): string {
  const n = sequence ? sequence.slice(0, index + 1).filter((s: any) => s.channel === "email").length : index + 1;
  return step.channel === "email" ? `Email ${n}` : STEP_NAME[`${step.channel}:${step.job}`] || cap(step.channel);
}

export const STEP_NAME: Record<string, string> = {
  "email:open": "Email, first", "email:follow_up": "Email, follow-up", "email:bump": "Email, short nudge",
  "email:break_up": "Email, last", "linkedin_connect:connect": "LinkedIn, connect", "linkedin_message:message": "LinkedIn, message",
  "call:call": "Call",
};

/** Contact that happened outside the desk. Any of it puts the SDR in the conversation: the desk stops its own steps. */
function OutsideContact({ personId, onDone }: { personId: number; onDone: () => void }) {
  const [busy, run] = useBusy();
  const log = (kind: string) => run(async () => { await api(`/api/people/${personId}/activity`, { method: "POST", body: { kind } }); onDone(); },
    "Logged. The desk stops its own steps for them.");
  return (
    <Section title="Talked outside the desk">
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
      <span style={{ flex: 1 }}>This deletes {name}, their emails, replies and notes, and keeps only a scrambled copy of their address so they are never added again. It cannot be undone.</span>
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
  const me = useData<any>("/api/me").data;
  const integ = useIntegration();
  const [busy, run] = useBusy();
  const [skipping, setSkipping] = useState(false);
  const [reason, setReason] = useState("");
  if (error) return <Frame crumb="Account"><Failed error={error} retry={reload} /></Frame>;
  if (!data) return <Frame crumb="Account"><Loading rows={8} /></Frame>;
  const a = data.account, s = data.score, cur = data.current;
  // A proposal is decided where it is read: the owner (or a manager) accepts or skips it here, as on Today.
  const canDecide = cur?.state === "proposed" && me && (me.user.role !== "sdr" || me.user.id === cur.owner_id);
  const decide = (accept: boolean) => run(
    () => api(`/api/account-plays/${cur.id}/decide`, { method: "POST", body: { accept, reason: accept ? null : reason } }),
    accept ? "Accepted. The desk is researching the account and drafting first emails." : "Skipped.",
  ).then(() => { setSkipping(false); setReason(""); reload(); });
  const decision = canDecide ? (
    <div className="play-decide">
      {skipping ? (
        <>
          <input className="input" placeholder="Why skip?" value={reason} autoFocus onChange={(e) => setReason(e.target.value)} aria-label="Reason for skipping" />
          <button className="btn quiet" onClick={() => setSkipping(false)}>Cancel</button>
          <button className="btn line" disabled={busy || reason.trim().length < 3} onClick={() => decide(false)}>Skip</button>
        </>
      ) : (
        <>
          <span className="small mute">Accept and the desk reads the company, finds the people who buy and drafts first emails for you to approve. Or skip, with a reason.</span>
          <button className="btn line" disabled={busy} onClick={() => setSkipping(true)}>Skip</button>
          <button className="btn" disabled={busy} onClick={() => decide(true)}>Accept</button>
        </>
      )}
    </div>
  ) : null;
  // With Market Desk present its tier is the tier, read-only, and this desk's own fit steps aside for the accounts that have one.
  const recorded = keptBy(integ, "market_desk") && !!a.crm_tier;
  const tabs: [string, string, number?][] = [["overview", "Overview"], ["people", "People", data.people.length],
    ["signals", "Signals", data.signals.length], ["outreach", "Outreach", data.messages.length + data.replies.length]];
  return (
    <Frame kind="account" crumb="Account">
      <div className="who">
        <Logo domain={a.primary_domain} name={a.name} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{a.name}</h2>
          <div className="meta clip">{a.primary_domain} &middot; {a.industry}, {n0(a.employees)} people, {a.hq_country}</div>
        </div>
      </div>
      <div className="figs">
        <Fig value={s?.priority ?? 0} label="Priority" />
        {recorded ? <Fig value={a.crm_tier} label="Tier" /> : <Fig value={s?.fit ?? a.fit_score ?? 0} label={`Fit, tier ${a.fit_tier}`} />}
        <Fig value={s?.intent ?? 0} label="Signals" />
        <Fig value={a.owner || cur?.owner || "Unassigned"} label={keptBy(integ, "market_desk") ? "SDR owner" : "Owner"} sm />
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([k, l, n]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}{n !== undefined ? <span className="n">{n}</span> : null}</button>)}
      </div>
      {tab === "overview" && <AccountOverview d={data} decision={decision} recorded={recorded} />}
      {tab === "people" && <AccountPeople d={data} />}
      {tab === "signals" && <SignalTimeline signals={data.signals} />}
      {tab === "outreach" && <AccountOutreach d={data} />}
      {cur ? null : data.holds.length ? <Section title={`On hold until ${day(data.holds[0].until)}`}><div className="small mute">{cap(data.holds[0].reason)}</div></Section> : null}
      {tab === "overview" ? <div className="acct-tools"><LogMeeting accountId={id} people={data.people} onDone={reload} /><HoldBox accountId={id} onDone={reload} /></div> : null}
      <ElsewhereAccount a={a} />
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
        {safeUrl(why.url) ? <a className="src" href={safeUrl(why.url)} target="_blank" rel="noreferrer noopener">Source <ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a> : null}
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

function CompanyData({ a }: { a: any }) {
  if (!a.enriched_at && !a.keywords?.length && !a.founded_year) return null;
  const millions = a.total_funding_cents ? Math.round(a.total_funding_cents / 100_000_000) : 0;
  const funding = millions ? `$${millions}M raised${a.latest_funding_round ? `, last a ${a.latest_funding_round}` : ""}${a.latest_funding_at ? ` in ${day(a.latest_funding_at)}` : ""}` : null;
  return (
    <Section title="Company data" right={a.enriched_at ? <span className="mute small" title={`Read from ${cap(a.enriched_by || "a data vendor")}`}>Read {ago(a.enriched_at)}</span> : null}>
      <div className="ledger">
        {a.founded_year ? <Reach label="Founded" value={String(a.founded_year)} /> : null}
        {funding ? <Reach label="Funding" value={funding} /> : null}
        {a.tech?.length ? <Reach label="Tools" value={a.tech.join(", ")} /> : null}
        {a.keywords?.length ? <Reach label="Known for" value={a.keywords.join(", ")} /> : null}
        {a.parent_name ? <Reach label="Part of" value={a.parent_name} /> : null}
      </div>
    </Section>
  );
}

function AccountOverview({ d, decision, recorded }: { d: any; decision?: ReactNode; recorded?: boolean }) {
  const cur = d.current;
  const max = Math.max(1, ...grouped(d.contributions).map((c) => c.value));
  const fit = (d.account.fit_breakdown?.factors || []) as any[];
  return (
    <>
      <CompanyData a={d.account} />
      {cur ? (
        <div className={`play-card${cur.state === "proposed" ? " is-proposed" : ""}`}>
        <Section title={cur.state === "proposed" ? "Proposed play" : "In play"} right={<Status kind={PLAY_STATE[cur.state][0]}>{PLAY_STATE[cur.state][1]}</Status>}>
          <div className="play-line">
            <button className="link-row play-name" onClick={() => openSheet("play", cur.play_id)}>{cur.play}</button>
            <span className="mute small">Proposed {day(cur.proposed_at)}{cur.owner ? ` to ${cur.owner}` : ""}</span>
          </div>
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
          {decision}
        </Section>
        </div>
      ) : d.plays[0]?.state === "held_out" ? (
        <Section title="Held back"><div className="mute">Matched <button className="link" onClick={() => openSheet("play", d.plays[0].play_id)}>{d.plays[0].play}</button> on {day(d.plays[0].proposed_at)}. Not contacted, on purpose.</div></Section>
      ) : null}
      {(() => {
        // Every earlier play here, so any of them is one click away.
        const past = (d.plays as any[]).filter((x) => x.id !== cur?.id && !(x === d.plays[0] && !cur && x.state === "held_out"));
        return past.length ? (
          <Section title="Earlier plays here">
            <div className="ledger">
              {past.map((x) => (
                <button key={x.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }} onClick={() => openSheet("play", x.play_id)}>
                  <div className="cell-main"><span className="t">{x.play}</span><span className="s">{day(x.proposed_at)}{x.closed_at ? ` to ${day(x.closed_at)}` : ""}{x.owner ? `, ${x.owner}` : ""}</span></div>
                  <Status kind={PLAY_STATE[x.state]?.[0] || "none"}>{PLAY_STATE[x.state]?.[1] || x.state}</Status>
                </button>
              ))}
            </div>
          </Section>
        ) : null;
      })()}
      <Section title="Signals raising priority">
        {d.contributions.length ? (
          <div className="bars">
            {grouped(d.contributions).slice(0, 7).map((c: any) => <Bar key={c.type} label={<SignalLabel type={c.type} label={c.label} />} value={c.value} of={max} shown={`+${Math.round(c.value)}`} hint="points" />)}
          </div>
        ) : <Empty title="No recent signals">Priority is the fit score alone.</Empty>}
      </Section>
      {recorded ? null : <Section title="Fit">
        {d.account.fit_breakdown?.excluded ? <div className="mute">{d.account.fit_breakdown.excluded}</div> : (
          <div className="ledger">
            {fit.map((f) => (
              <div key={f.key} className="row" style={{ gridTemplateColumns: "1fr auto", minHeight: 36 }}>
                <span>{cap(f.key)}</span>
                <Status kind={f.matched ? (f.weight < 0 ? "stop" : "ok") : "none"}>{f.matched ? (f.weight < 0 ? `${f.contribution}` : `+${f.contribution}`) : f.matched === null ? "Not known" : "No match"}</Status>
              </div>
            ))}
          </div>
        )}
      </Section>}
      {d.opportunities.length ? (
        <Section title="Pipeline">
          <div className="ledger">
            {d.opportunities.map((o: any) => (
              <div key={o.id} className="row" style={{ gridTemplateColumns: "1fr auto auto" }}>
                <div className="cell-main"><span className="t">{o.name}</span><span className="s">{o.stage}, {day(o.created_at)}</span></div>
                <span className="mute small">{ATTR[o.attribution] || ""}</span>
                {o.amount_cents != null ? <span className="num">{money(o.amount_cents)}</span> : <span />}
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
        {e ? <Status kind={GOOD_STOPS.has(p.stop_reason) ? "ok" : e[0]}>{p.stop_reason === "meeting_booked" && !(d.meetings || []).some((m: any) => m.person_id === p.id)
          ? "Colleague's meeting" : p.enrollment === "stopped" || p.enrollment === "paused" ? stopWord(p.stop_reason || p.pause_reason) || e[1] : e[1]}</Status>
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
                <div className="cell-main"><span className="t">No {g.label.toLowerCase()} reached</span><span className="s">{g.reason}</span></div>
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
            <span className="s" style={{ whiteSpace: "normal" }}>{s.evidence.summary}{safeUrl(s.evidence.url) ? <> <a href={safeUrl(s.evidence.url)} target="_blank" rel="noreferrer noopener" className="mute"><ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a></> : null}</span>
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
                <div className="cell-main"><span className="t">{m.subject || "(no subject)"}</span><span className="s">{m.full_name}, Email {m.email_no ?? m.step_index + 1}</span></div>
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
                <Status kind={m.status === "held" ? "ok" : m.status === "booked" ? "go" : "off"}>{({ held: "Held", booked: "Booked", no_show: "No show", cancelled: "Cancelled" } as Record<string, string>)[m.status] || cap(m.status)}</Status>
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
      <span className="mute small" style={{ flex: 1 }}>The mail provider did not confirm whether it sent. Check the mailbox's sent folder.</span>
      <button className="btn line" disabled={busy} onClick={() => run(() => api(`/api/messages/${id}/outcome`, { method: "POST", body: { sent: false } }), "Recorded. It goes out again in their window.")}>It is not there</button>
      <button className="btn" disabled={busy} onClick={() => run(() => api(`/api/messages/${id}/outcome`, { method: "POST", body: { sent: true } }), "Recorded as sent.")}>It went out</button>
    </>
  ) : undefined;
  return (
    <Frame kind={m.channel === "email" ? "email" : "linkedin"} crumb={m.channel === "email" ? <>Email {m.email_no ?? m.step_index + 1}</> : <>LinkedIn note</>} foot={foot}>
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
        <MailPreview m={m} footer={footer}>
          {sentences.length && !m.edited ? (
            <>
              <p>{sentences[0]?.text}</p>
              <p>{sentences.slice(1).map((s: any, i: number) => (
                <span key={i}><span className={sentenceKind(s.kind)}>{s.text}</span>{(s.fact_ids || []).map((f: number) => <sup key={f}>{idOf.get(f) ?? "?"}</sup>)} </span>
              ))}</p>
            </>
          ) : <p style={{ whiteSpace: "pre-wrap" }}>{bodyOnly(m.body)}</p>}
        </MailPreview>
      )}
      <Section title="Facts cited">
        {m.facts.length ? (
          <ul className="facts">
            {m.facts.map((f: any) => (
              <li key={f.id}><span className="id">{idOf.get(f.id)}</span>
                <span>{f.text} <span className="mute small">{f.kind.startsWith("signal:") ? "Signal" : "Their website"}, {day(f.observed_at)}</span>
                  {safeUrl(f.source_url) ? <> <a href={safeUrl(f.source_url)} target="_blank" rel="noreferrer noopener" className="mute"><ArrowSquareOut size={12} style={{ verticalAlign: -1 }} /></a></> : null}</span>
              </li>
            ))}
          </ul>
        ) : <Empty title="No facts cited" />}
      </Section>
      {lastAttempt && m.attempts.length > 1 && m.gate?.passed ? (
        <div className="small mute">First draft: {(lastAttempt.failures || []).map((f: any) => f.message.toLowerCase()).join("; ")}. Rewritten once.</div>
      ) : null}

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
    <Frame kind="reply" crumb={<>{r.company || r.from_addr}</>} foot={foot}>
      <div className="who">
        <Avatar name={r.full_name || r.from_addr} photo={r.photo_url} size={44} />
        <div style={{ minWidth: 0 }}>
          <h2 className="clip">{r.person_id ? <button className="link-row" onClick={() => openSheet("person", r.person_id)}>{r.full_name || r.from_addr}</button> : (r.full_name || r.from_addr)}</h2>
          <div className="meta clip">{r.title ? `${r.title}, ` : ""}{r.account_id ? <button className="btn quiet sm" style={{ padding: 0, height: "auto" }} onClick={() => openSheet("account", r.account_id)}>{r.company}</button> : "No account matched"}</div>
        </div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={l[0]}>{l[1]}</Status>} label="What it says" sm />
        <Fig value={ago(r.received_at)} label="Received" sm />
        {r.hot && open && r.sla_due_at ? <Fig value={ahead(r.sla_due_at)} label="Answer by" sm /> : null}
        {r.handled_at ? <Fig value={r.meeting_id ? <button className="link" onClick={() => openSheet("meeting", r.meeting_id)}>{cap(r.outcome || "handled")}</button> : cap(r.outcome || "handled")} label="Outcome" sm /> : null}
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
      {r.hot && r.account_id && !r.handled_at && r.colleagues_waiting ? <ColleaguesChoice replyId={id} count={r.colleagues_waiting} /> : null}
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
  const [worst, setWorst] = useState<any>(null);
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
      {promo.next && p.status !== "draft" ? (promo.ready && isManager
        ? <button className="btn" disabled={busy} onClick={() => change({ autonomy: promo.next, reason: "Met every check" }, "Promoted to the next stage.")}>Promote to stage {STAGE_ORDER.indexOf(promo.next) + 1} of 4</button>
        : null) : null}
    </>
  ) : undefined;
  return (
    <Frame crumb="Play" foot={foot}>
      <div style={{ display: "grid", gap: 6 }}>
        <h2 className="sheet-title">{p.name}</h2>
        <div className="thesis">
          <span className="thesis-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <div className="thesis-body">
            <p className="thesis-lead">{p.hypothesis}</p>
            <p>So when a company that fits our profile shows {p.trigger.any_of.length === 1 ? "this signal, " : "one of these signals, "}{p.trigger.any_of.map((k: string, n: number, all: string[]) => (
              <span key={k}><b className="thesis-sig"><SignalIcon type={k} size={15} />{signalNames[k] || cap(k)}</b>{n < all.length - 2 ? ", " : n === all.length - 2 ? " or " : ""}</span>
            ))}, I bring it to its SDR. {(() => {
              const has = (c: string) => p.sequence.some((x: any) => x.channel.startsWith(c));
              const ch = [has("email") ? "email" : null, has("linkedin") ? "LinkedIn message" : null, has("call") ? "call" : null].filter(Boolean) as string[];
              return `Every ${ch.length > 1 ? `${ch.slice(0, -1).join(", ")} and ${ch[ch.length - 1]}` : ch[0] || "message"} starts from one idea.`;
            })()} {p.angle}</p>
            <p>If the accounts we work book meetings no more often than the {Math.round(100 / Math.max(1, p.holdout_pct)) === 5 ? "1 in 5" : `${p.holdout_pct}%`} I
              hold back and never contact, the bet is wrong.</p>
          </div>
        </div>
      </div>
      <div className="figs">
        <Fig value={<Status kind={p.status === "live" ? "go" : "off"}>{cap(p.status)}</Status>} label="Status" sm />
        <Fig value={STAGE[p.autonomy]} label="Who writes" sm />
        {p.status === "draft" ? null : <>
          <Fig value={p.median_hours_to_first_touch ? `${Math.round(p.median_hours_to_first_touch)} h` : "None yet"} label="Signal to first email" sm />
          {p.pipeline_cents !== undefined ? <Fig value={money(p.pipeline_cents)} label="Pipeline sourced" sm /> : null}</>}
      </div>
      {p.suggested_from && me && me.user.role !== "sdr" ? <PlayOrigin id={id} /> : null}
      {p.status === "draft" ? null : <Section title="Accounts">
        <div className="funnel">
          <Bar label="Proposed" value={f.proposed} of={f.proposed} />
          <Bar label="Accepted" value={f.accepted} of={f.proposed} hint={pct(f.proposed ? f.accepted / f.proposed : 0)} />
          <Bar label="Contacted" value={f.contacted} of={f.proposed} hint={pct(f.proposed ? f.contacted / f.proposed : 0)} />
          <Bar label="Replied" value={f.replied} of={f.proposed} hint={pct(f.proposed ? f.replied / f.proposed : 0)} />
          <Bar label="Positive reply" value={f.positive} of={f.proposed} hint={pct(f.proposed ? f.positive / f.proposed : 0)} tone="accent" />
          <Bar label="Meeting" value={f.meetings} of={f.proposed} hint={pct(f.proposed ? f.meetings / f.proposed : 0)} tone="accent" />
        </div>
      </Section>}
      {p.status === "draft" ? null : <><div className="play-card is-proposed"><Section title="Is this play creating meetings?"><LiftBlock lift={lift} holdoutPct={p.holdout_pct} /></Section></div>
      <PlayAccounts id={id} /></>}
      <Section title="Which signals start it">
        <dl className="kv">
          <dt>Fit tiers</dt><dd>{p.trigger.fit_tiers.join(" and ")}</dd>
          <dt>Minimum priority</dt><dd>{p.trigger.min_priority}</dd>
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
              <span>{STEP_NAME[`${s.channel}:${s.job}`] || cap(s.channel)}</span>
              <span className="mute small">{whoDoes(s, i, p.sequence, p.autonomy)}</span>
            </div>
          ))}
        </div>
      </Section>
      {p.status === "draft" ? <DraftPreview p={p} hideCost={isManager && !isAuthor} onCost={(c) => { if (!limits && c) { setLimits(defaultCap(c)); setWorst(c); } }} /> : null}
      {p.status === "draft" && isManager && !isAuthor && limits ? <CapForm limits={limits} setLimits={setLimits} worst={worst} /> : null}
      {p.status !== "draft" && p.cap_use?.length ? <CapUse rows={p.cap_use} /> : null}
      {promo.next && p.status !== "draft" ? (
        <Section title="Who writes" right={<StageScale autonomy={p.autonomy} />}>
          <div className="small" style={{ color: "var(--ink-2)" }}>Now: {STAGE[p.autonomy]}. Next: {STAGE[promo.next]}, {p.autonomy === "research"
            ? "when a manager moves it there; the desk has no drafts of its own to judge yet, so only these checks apply."
            : "once every check below is met."}</div>
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

function DraftPreview({ p, onCost, hideCost }: { p: any; onCost?: (c: any) => void; hideCost?: boolean }) {
  const [pv, setPv] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const body = { name: p.name, hypothesis: p.hypothesis, angle: p.angle, personas: p.personas, max_people: p.max_people,
      holdout_pct: p.holdout_pct, urgent: p.urgent, latency_hours: p.latency_hours, sequence: p.sequence, trigger: p.trigger };
    api<any>("/api/play-preview", { method: "POST", body }).then((r) => { setPv(r); onCost?.(r.cost); }).catch((e) => setErr(e.message));
  }, [p.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return <PlayPreview pv={pv && hideCost ? { ...pv, cost: null } : pv} error={err} />;
}

const CAP_NAMES: Record<string, [string, string]> = {
  people_search: ["People search", "credits"], email_finder: ["Email finder", "credits"],
  email_verifier: ["Email verification", "credits"], phone_finder: ["Phone finder", "credits"], anthropic_cents: ["AI", "dollars"],
};

/** The cost card's worst case a month, rounded up, as the starting cap. The manager can lower or raise it. */
function defaultCap(c: any): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(c.per_month.credits as Record<string, number>)) if (v > 0) out[k] = Math.ceil(v);
  out.anthropic_cents = Math.max(100, Math.ceil(c.per_month.ai_dollars * 100));
  return out;
}

function CapForm({ limits, setLimits, worst }: { limits: Record<string, number>; setLimits: (c: Record<string, number>) => void; worst: any }) {
  const worstOf = (k: string) => (k === "anthropic_cents" ? `$${n0(worst?.per_month.ai_dollars || 0)}` : n0(worst?.per_month.credits[k] || 0));
  return (
    <Section title="Monthly cap">
      <div className="ledger">
        <div className="row head" style={{ gridTemplateColumns: CAP_COLS }}><span>Paid for</span><span className="num">Worst case a month</span><span className="num">Cap</span></div>
        {Object.entries(limits).map(([k, v]) => {
          const dollars = k === "anthropic_cents";
          return (
            <div key={k} className="row" style={{ gridTemplateColumns: CAP_COLS }}>
              <span>{CAP_NAMES[k]?.[0] || k} <span className="mute small">{dollars ? "dollars" : "credits"}</span></span>
              <span className="num mute" data-label="Worst case">{worstOf(k)}</span>
              <input className="input num" inputMode="numeric" value={dollars ? Math.round(v / 100) : v} aria-label={`${CAP_NAMES[k]?.[0] || k} cap`}
                onChange={(e) => { const n = Math.max(0, Number(e.target.value.replace(/\D/g, "")) || 0); setLimits({ ...limits, [k]: dollars ? n * 100 : n }); }} />
            </div>
          );
        })}
      </div>
    </Section>
  );
}
const CAP_COLS = "minmax(0,1fr) 150px 110px";

function CapUse({ rows }: { rows: any[] }) {
  return (
    <Section title="This month against its cap">
      <div className="ledger">
        {rows.map((r: any) => (
          <div key={r.key} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(140px,1.4fr)" }}>
            <span>{CAP_NAMES[r.key]?.[0] || r.key}</span>
            <Bar label="" value={r.used} of={Math.max(r.cap, 1)} shown={r.key === "anthropic_cents" ? `$${n0(r.used / 100)} of $${n0(r.cap / 100)}` : `${n0(r.used)} of ${n0(r.cap)}`} hint={r.key === "anthropic_cents" ? undefined : "credits"} tone={r.used >= r.cap ? "accent" : undefined} />
          </div>
        ))}
      </div>
    </Section>
  );
}

const PLAY_GROUP: Record<string, "open" | "held" | "closed"> = {
  proposed: "open", accepted: "open", researching: "open", approving: "open", active: "open", engaged: "open", meeting: "open",
  held_out: "held", converted: "closed", lost: "closed", stopped: "closed", skipped: "closed", expired: "closed",
};
const PLAY_PAGE = 15;

/** Every account the play was offered: searchable, filtered by where it stands, a page at a time in its own scroll. */
function PlayAccounts({ id }: { id: number }) {
  const { data } = useData<any>(`/api/plays/${id}/accounts`);
  const [q, setQ] = useState("");
  const [group, setGroup] = useState<"all" | "open" | "held" | "closed">("all");
  const [page, setPage] = useState(1);
  const all: any[] = data?.accounts || [];
  const count = (g: string) => all.filter((a) => PLAY_GROUP[a.state] === g).length;
  const needle = q.trim().toLowerCase();
  const shown = all.filter((a) => (group === "all" || PLAY_GROUP[a.state] === group)
    && (!needle || `${a.name} ${a.primary_domain || ""} ${a.owner || ""}`.toLowerCase().includes(needle)));
  const pages = Math.max(1, Math.ceil(shown.length / PLAY_PAGE));
  const p = Math.min(page, pages);
  if (!all.length) return null;
  return (
    <Section title={`Accounts (${n0(all.length)})`}>
      <div className="pa-tools">
        <Seg label="Where they stand" value={group} onChange={(v) => { setGroup(v); setPage(1); }}
          options={[["all", "All"], ["open", `Open ${count("open")}`], ["held", `Held back ${count("held")}`], ["closed", `Closed ${count("closed")}`]]} />
        <input className="input" type="search" placeholder="Company or SDR" value={q} aria-label="Search this play's accounts"
          onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      </div>
      {shown.length === 0 ? <Empty title="No accounts match" /> : (
        <div className="ledger pa-list">
          {shown.slice((p - 1) * PLAY_PAGE, p * PLAY_PAGE).map((a: any) => {
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
      )}
      {shown.length > PLAY_PAGE ? (
        <nav className="pager" aria-label="Pages of this play's accounts">
          <span className="mute small">{n0((p - 1) * PLAY_PAGE + 1)} to {n0(Math.min(p * PLAY_PAGE, shown.length))} of {n0(shown.length)}</span>
          <span className="pager-buttons">
            <button className="btn line sm" disabled={p <= 1} onClick={() => setPage(p - 1)}>Previous</button>
            <span className="small">Page {p} of {pages}</span>
            <button className="btn line sm" disabled={p >= pages} onClick={() => setPage(p + 1)}>Next</button>
          </span>
        </nav>
      ) : null}
    </Section>
  );
}

const STAGE_ORDER = ["research", "draft", "supervised", "autonomous"];
/** Four steps, the earned ones filled, the current one cobalt, then "n of 4". */
function StageScale({ autonomy }: { autonomy: string }) {
  const stage = Math.max(0, STAGE_ORDER.indexOf(autonomy));
  return (
    <span className="prow-stage" style={{ marginTop: 0 }}>
      <span className="prow-meter" aria-hidden="true">{STAGE_ORDER.map((x, k) => <i key={x} className={k < stage ? "on" : k === stage ? "on is-now" : ""} />)}</span>
      <span className="prow-of">Stage {stage + 1} of 4</span>
    </span>
  );
}

/** Who actually does a step, given the play's stage: a desk step is only "sent by the desk" once the play has earned it. */
function whoDoes(step: any, i: number, seq: any[], autonomy: string): string {
  if (step.by !== "desk") return "SDR does it";
  const firstEmail = seq.findIndex((x) => x.by === "desk" && x.channel === "email") === i;
  if (autonomy === "research") return "SDR writes it";
  if (autonomy === "draft") return "Desk drafts, SDR approves";
  if (autonomy === "supervised") return firstEmail ? "Desk drafts, SDR approves" : "Desk sends, SDR checks a sample";
  return "Desk sends to tier B, SDR approves tier A";
}

/** Each stage in one wording, the same as whoDoes says it step by step (and plays.py STAGE_WORDS in alerts). */
export const STAGE: Record<string, string> = { research: "SDR writes everything", draft: "SDR approves every email", supervised: "SDR approves first emails and checks a sample of the rest", autonomous: "Desk sends to tier B, SDR approves tier A" };

/** Does the play cause meetings? Accounts it worked against a random share it never contacted. Said in words a
 *  new hire can read: the two rates, then a verdict, or how much longer until there is one. */
export function LiftBlock({ lift, holdoutPct = 20 }: { lift: any; holdoutPct?: number }) {
  const t = lift.treated, h = lift.holdout;
  const share = Math.max(1, Math.round(100 / Math.max(1, holdoutPct)));
  const more = lift.still_needed?.holdout || 0;
  if (!t.accounts && !h.accounts) return (
    <div className="lift">
      <p className="lift-why">1 in {share} accounts this play would work is held back and never contacted. If the worked
        accounts book more meetings, the play is the reason.</p>
      <Status kind="none">No accounts proposed for this play yet</Status>
    </div>
  );
  return (
    <div className="lift">
      <p className="lift-why">1 in {share} accounts this play would work is held back and never contacted. If the worked
        accounts book more meetings, the play is the reason.</p>
      <div className="lift-pair">
        <div><b>{pct(t.rate, 0)}</b><span>of worked accounts booked a meeting <span className="mute">({t.meetings} of {t.accounts})</span></span></div>
        <div><b>{pct(h.rate, 0)}</b><span>of held-back accounts booked one anyway <span className="mute">({h.meetings} of {h.accounts})</span></span></div>
      </div>
      {lift.enough && lift.difference !== null ? (
        <Status kind={lift.interval[0] > 0 ? "ok" : "off"}>
          {lift.interval[0] > 0 ? `Worked accounts meet ${pct(lift.difference, 0)} more often (likely ${pct(lift.interval[0], 0)} to ${pct(lift.interval[1], 0)})`
            : "No clear difference yet: the play may not be adding meetings"}
        </Status>
      ) : (
        <div className="lift-verdict">
          <Status kind="wait" title="With this few accounts, a difference could be luck.">Too few to tell</Status>
          <span className="mute small">{lift.out_of_reach
            ? `Settling it needs about ${n0(more * share)} more accounts proposed for this play, and only ${n0(lift.room)} in this desk have never been proposed for it. At this size the comparison cannot answer; it needs a larger list or a bigger difference.`
            : `About ${n0(more * share)} more accounts proposed for this play, so ${n0(more)} more are held back.`}</span>
        </div>
      )}
    </div>
  );
}

/** Offered a play against held back (any meeting or deal, inbound included, so not the funnel's outbound count), one row per outcome: each group's rate, then the difference or what is still needed. */
export function Comparison({ rows }: { rows: [string, any][] }) {
  return (
    <div className="ledger">
      <div className="row head" style={{ gridTemplateColumns: CMP }}><span>Accounts with any</span><span className="num">Worked</span><span className="num">Held back, never contacted</span><span className="num">Difference</span></div>
      {rows.map(([label, l]) => (
        <div key={label} className="row" style={{ gridTemplateColumns: CMP }}>
          <span className="cell-main"><span className="t">{label}</span></span>
          <span className="num" data-label="Worked">{pct(l.treated.rate, 1)} <span className="mute small">{l.treated.meetings} of {l.treated.accounts}</span></span>
          <span className="num" data-label="Held back">{pct(l.holdout.rate, 1)} <span className="mute small">{l.holdout.meetings} of {l.holdout.accounts}</span></span>
          <span className="num" data-label="Difference">{l.enough && l.difference !== null
            ? <>{l.difference >= 0 ? "+" : ""}{pct(l.difference, 1)} <span className="mute small">likely {pct(l.interval[0], 1)} to {pct(l.interval[1], 1)}</span></>
            : <span className="mute small" title="With this few accounts, a difference could be luck.">Too few to tell</span>}</span>
        </div>
      ))}
    </div>
  );
}
const CMP = "minmax(0,1.2fr) 130px 130px minmax(0,1.3fr)";

export { withParam };

// ---------------------------------------------------------------- a play suggested from call learnings

export function SuggestionSheet({ id }: { id: number }) {
  const { data: s, error, reload } = useData<any>(`/api/play-suggestions/${id}`);
  const plays = useData<any>("/api/plays").data;
  const me = useData<any>("/api/me").data;
  const [busy, run] = useBusy();
  const [asking, setAsking] = useState<null | "not_now" | "dismissed">(null);
  const [reason, setReason] = useState("");
  // One that became a play is the play now: its old link lands on the play's sheet, in place of this one.
  const toPlay = s?.status === "drafted" && s.play_id ? s.play_id : null;
  useEffect(() => {
    if (!toPlay) return;
    const u = new URL(window.location.href);
    u.searchParams.set("sheet", `play:${toPlay}`);
    navigate(u.pathname + "?" + u.searchParams.toString(), true);
  }, [toPlay]);
  if (error) return <Frame crumb="Suggested play" kind="suggestion"><Failed error={error} retry={reload} /></Frame>;
  if (!s || toPlay) return <Frame crumb="Suggested play" kind="suggestion"><Loading rows={8} /></Frame>;
  const e = s.evidence, d = s.draft;
  const role = me?.user.role;
  // A live play that already starts on this signal: the suggestion is a new angle for it, not a play from nothing.
  const already = (plays?.plays || []).filter((p: any) => p.status === "live" && p.trigger.any_of.includes(s.segment_signal_type));
  const decide = (decision: "not_now" | "dismissed") => run(async () => {
    await api(`/api/play-suggestions/${id}/decide`, { method: "POST", body: { decision, reason: reason.trim() || null } });
    closeSheet();
  }, decision === "not_now" ? "Set aside. It comes back when heard at 1.5 times as many accounts as when it was set aside." : "This theme is not suggested again.");
  const makeDraft = () => {
    const u = new URL(window.location.href);
    u.searchParams.set("sheet", "playedit:new");
    u.searchParams.set("suggestion", String(id));
    u.searchParams.set("from", `suggestion:${id}`);
    navigate(u.pathname + "?" + u.searchParams.toString());
  };
  const open = s.status === "open";
  const foot = open && (role === "gtm" || role === "manager") ? (asking ? (
    <div style={{ display: "grid", gap: 8, width: "100%" }}>
      <textarea className="input" rows={2} value={reason} maxLength={300} onChange={(x) => setReason(x.target.value)} autoFocus
        aria-label="Why" placeholder={asking === "not_now" ? "Why not now? Required" : "Why not? Optional"} />
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn quiet sm" disabled={busy} onClick={() => { setAsking(null); setReason(""); }}>Back</button>
        <button className="btn sm" disabled={busy || (asking === "not_now" && !reason.trim())} onClick={() => decide(asking)}>
          {asking === "not_now" ? "Set aside" : "Never suggest this theme"}</button>
      </div>
    </div>
  ) : (
    <>
      <button className="btn quiet" disabled={busy} onClick={() => setAsking("dismissed")}>Never suggest</button>
      <button className="btn line" disabled={busy} onClick={() => setAsking("not_now")}>Not now</button>
      {role === "gtm" ? <button className="btn lead" disabled={busy} onClick={makeDraft}>Make it a draft play</button> : null}
    </>
  )) : undefined;
  const STATUS: Record<string, string> = { not_now: "Set aside", dismissed: "Never suggested again", lapsed: "No longer heard often enough" };
  return (
    <Frame crumb="Suggested play" kind="suggestion" foot={foot}>
      <div style={{ display: "grid", gap: 6 }}>
        <div className="mute small">{s.kind === "competitor" ? "Competitor" : "Reason to buy"}</div>
        <h2 className="sheet-title">{s.theme || "Theme removed"}</h2>
      </div>
      {!open ? <div className="notice decided"><b>{STATUS[s.status] || cap(s.status)}</b>
        {s.reason ? <span>{s.reason}</span> : null}
        <span className="mute">{s.decided_by_name ? `${s.decided_by_name}, ` : ""}{day(s.decided_at)}</span></div> : null}
      <Heard e={e} segment={s.segment_label}>From {e.sdrs} {e.sdrs === 1 ? "SDR" : "SDRs"}, last {e.window_days} days</Heard>
      <div className={`play-card${open ? " is-proposed" : ""}`}>
        <Section title="The draft play">
          <dl className="kv">
            <dt>Name</dt><dd>{d.name}</dd>
            <dt>Heard</dt><dd>{d.hypothesis}</dd>
            <dt>Starts on</dt><dd style={{ display: "grid", gap: 6 }}>{d.trigger.any_of.map((k: string) => <SignalLabel key={k} type={k} label={s.draft_labels?.signals[k] || cap(k)} />)}</dd>
            {already.length ? <><dt>Already live</dt><dd className="actions" style={{ flexWrap: "wrap" }}>{already.map((p: any) => (
              <button key={p.id} className="btn line sm" onClick={() => openSheet("play", p.id)}>{p.name}</button>))}</dd></> : null}
            <dt>Who</dt><dd>{d.personas.map((k: string) => s.draft_labels?.personas[k] || PERSONA[k] || k).join(", ")}</dd>
            <dt>First touch</dt><dd>{d.angle}</dd>
          </dl>
        </Section>
      </div>
      <Section title="What they said" count={s.quotes.length}><Quotes quotes={s.quotes} /></Section>
      {s.objections.length ? (
        <Section title="Objections at these accounts">
          <div className="ledger">
            {s.objections.map((o: any) => (
              <div key={o.id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto", minHeight: 36 }}>
                <span className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}>{o.label}</span>
                  {o.kind === "reason_not" ? <span className="s">Reason not to buy</span> : null}</span>
                <span className="num mute small">{o.accounts} {o.accounts === 1 ? "account" : "accounts"}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </Frame>
  );
}

/** How often a theme came up at accounts on one signal, against every other account with call notes. The second bar
    is left out when there are no other accounts to compare with. */
function Heard({ e, segment, children }: { e: any; segment: string; children: ReactNode }) {
  const share = (a: number, b: number) => (b ? pct(a / b) : "");
  return (
    <div className="heard">
      <Bar label={<b>{segment}</b>} value={e.accounts} of={e.segment_accounts} shown={`${e.accounts} of ${e.segment_accounts}`}
        hint={share(e.accounts, e.segment_accounts)} />
      {e.elsewhere_accounts > 0 ? <Bar label="Other accounts" value={e.elsewhere} of={e.elsewhere_accounts}
        shown={`${e.elsewhere} of ${e.elsewhere_accounts}`} hint={share(e.elsewhere, e.elsewhere_accounts)} tone="soft" /> : null}
      <div className="mute small">{children}</div>
    </div>
  );
}

/** A buyer's words from call notes, each opening its meeting: three, then the rest behind a button. */
function Quotes({ quotes }: { quotes: any[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? quotes : quotes.slice(0, 3);
  return (
    <>
      <div className="ledger">
        {shown.map((q: any) => (
          <button key={q.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr)" }} onClick={() => openSheet("meeting", q.meeting_id)}>
            <Logo domain={q.primary_domain} name={q.company} />
            <div className="cell-main"><span className="t" style={{ whiteSpace: "normal" }}><span className="qmark" aria-hidden="true">&ldquo;</span>{q.quote}</span>
              <span className="s">{q.company}{q.sdr ? `, ${q.sdr}` : ""}, {day(q.created_at)}</span></div>
          </button>
        ))}
      </div>
      {!all && quotes.length > 3 ? <div><button className="btn line sm" onClick={() => setAll(true)}>All {quotes.length} quotes</button></div> : null}
    </>
  );
}

/** On a play made from a suggestion: the evidence it was made on, so it stays with the play. Manager and GTM only. */
function PlayOrigin({ id }: { id: number }) {
  const s = useData<any>(`/api/plays/${id}/origin`).data?.suggestion;
  const [quotes, setQuotes] = useState(false);
  if (!s) return null;
  const e = s.evidence;
  return (
    <Section title="Why this play exists">
      <Heard e={e} segment={s.segment_label}>
        Heard on calls by {e.sdrs} {e.sdrs === 1 ? "SDR" : "SDRs"}{s.decided_by_name ? `; made a play by ${s.decided_by_name}, ${day(s.decided_at)}` : ""}
      </Heard>
      {s.quotes.length ? (quotes ? <Quotes quotes={s.quotes} />
        : <div><button className="btn line sm" onClick={() => setQuotes(true)}>{s.quotes.length} {s.quotes.length === 1 ? "quote" : "quotes"}</button></div>) : null}
    </Section>
  );
}
