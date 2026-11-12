import { useEffect, useMemo, useState } from "react";
import { Plus, Trash } from "@phosphor-icons/react";
import { api } from "./api";
import { Empty, Fig, Loading, Section, n0, navigate, useBusy, useData } from "./lib";
import { Logo } from "./marks";
import { SignalLabel } from "./signalIcons";

type Step = { day: number; channel: string; job: string; by: string };
type Draft = {
  name: string; hypothesis: string; angle: string; personas: string[]; max_people: number; holdout_pct: number;
  urgent: boolean; latency_hours: number; sequence: Step[];
  trigger: { any_of: string[]; fit_tiers: string[]; min_priority: number; within_days: number };
  suggested_from?: number | null;
};

const BLANK: Draft = {
  name: "", hypothesis: "", angle: "", personas: ["cfo"], max_people: 2, holdout_pct: 20, urgent: false, latency_hours: 48,
  trigger: { any_of: [], fit_tiers: ["A", "B"], min_priority: 40, within_days: 30 },
  sequence: [{ day: 0, channel: "email", job: "open", by: "desk" }, { day: 3, channel: "email", job: "follow_up", by: "desk" },
    { day: 6, channel: "call", job: "call", by: "sdr" }, { day: 9, channel: "email", job: "break_up", by: "desk" }],
};

const STEP_KINDS: [string, string, string, string][] = [
  ["email:open", "Email, first", "email", "open"], ["email:follow_up", "Email, follow-up", "email", "follow_up"],
  ["email:bump", "Email, short nudge", "email", "bump"], ["email:break_up", "Email, last", "email", "break_up"],
  ["linkedin_connect:connect", "LinkedIn, connect", "linkedin_connect", "connect"],
  ["linkedin_message:message", "LinkedIn, message", "linkedin_message", "message"], ["call:call", "Call", "call", "call"],
];

const PERSONAS: [string, string][] = [["cfo", "Finance leader"], ["controller", "Controller"],
  ["revops", "Revenue operations"], ["data", "Data and systems"]];

export function PlayEditor({ id, fromSuggestion = null }: { id: number | null; fromSuggestion?: number | null }) {
  const existing = useData<any>(id ? "/api/plays" : null).data;
  // From a suggestion: its drafted fields over the defaults for a new play; every other field stays the default.
  const suggestion = useData<any>(!id && fromSuggestion ? `/api/play-suggestions/${fromSuggestion}` : null).data;
  const settings = useData<any>("/api/settings").data;
  const me = useData<any>("/api/me").data;
  const [d, setD] = useState<Draft | null>(id || fromSuggestion ? null : BLANK);
  const [pv, setPv] = useState<any>(null);
  const [pvError, setPvError] = useState<string | null>(null);
  const [busy, run] = useBusy();

  useEffect(() => {
    if (!id || !existing || d) return;
    const p = existing.plays.find((x: any) => x.id === id);
    if (p) setD({ name: p.name, hypothesis: p.hypothesis, angle: p.angle, personas: p.personas, max_people: p.max_people,
      holdout_pct: p.holdout_pct, urgent: p.urgent, latency_hours: p.latency_hours, sequence: p.sequence, trigger: p.trigger });
  }, [id, existing, d]);
  useEffect(() => {
    if (id || !suggestion || d) return;
    const x = suggestion.draft;
    setD({ ...BLANK, name: x.name, hypothesis: x.hypothesis, angle: x.angle, personas: x.personas,
      trigger: { ...BLANK.trigger, any_of: x.trigger.any_of }, suggested_from: suggestion.theme_id });
  }, [id, suggestion, d]);

  // Preview and price as the play is written, a moment after the last change.
  const key = JSON.stringify(d);
  useEffect(() => {
    if (!d || !d.trigger.any_of.length || d.name.length < 3 || d.hypothesis.length < 10 || d.angle.length < 10) {
      setPv(null);
      return;
    }
    const t = window.setTimeout(() => {
      api("/api/play-preview", { method: "POST", body: d }).then((r) => { setPv(r); setPvError(null); })
        .catch((e) => { setPv(null); setPvError(e.message); });
    }, 350);
    return () => window.clearTimeout(t);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const types = useMemo(() => (settings?.signal_types || []).filter((t: any) => t.enabled && Number(t.weight) > 0), [settings]);
  if (!d || !settings) return <Loading rows={8} />;
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const setTrigger = (patch: Partial<Draft["trigger"]>) => set({ trigger: { ...d.trigger, ...patch } });
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const setStep = (i: number, patch: Partial<Step>) => set({ sequence: d.sequence.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const canSave = me?.user.role === "gtm";
  const missing = [d.name.length < 3 && "a name", d.hypothesis.length < 10 && "who needs us and why (10 characters or more)",
    d.angle.length < 10 && "what the first touch leads with (10 characters or more)", !d.trigger.any_of.length && "a signal"]
    .filter(Boolean) as string[];

  const save = () => run(async () => {
    if (id) {
      await api(`/api/plays/${id}`, { method: "PUT", body: d });
      navigate(window.location.pathname + `?sheet=play:${id}`, true);
    } else {
      const r = await api<any>("/api/plays", { method: "POST", body: d });
      navigate(window.location.pathname + `?sheet=play:${r.id}`, true);
    }
  }, id ? "Saved." : "Saved as a draft. A manager launches it.");

  return (
    <div className="editor">
      {suggestion && d.suggested_from ? (
        <div className="notice"><span className="mute">Drafted from a suggestion. Edit anything before you save.</span></div>
      ) : null}
      <Section title="The idea">
        <label className="field"><span>Name</span><input className="input" value={d.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} placeholder="New finance leader, first 90 days" /></label>
        <label className="field"><span>When this happens, these people need us, because</span>
          <textarea className="input" rows={3} value={d.hypothesis} maxLength={400} onChange={(e) => set({ hypothesis: e.target.value })} /></label>
        <label className="field"><span>What the first touch leads with</span>
          <textarea className="input" rows={2} value={d.angle} maxLength={400} onChange={(e) => set({ angle: e.target.value })} /></label>
      </Section>

      <Section title="Which signals start it">
        <div className="choices">
          {types.map((t: any) => (
            <label key={t.key} className="choice">
              <input type="checkbox" checked={d.trigger.any_of.includes(t.key)} onChange={() => setTrigger({ any_of: toggle(d.trigger.any_of, t.key) })} />
              <SignalLabel type={t.key} label={t.label} />
            </label>
          ))}
        </div>
        <div className="form-row">
          <label className="field"><span>Signal no older than, days</span><input className="input num" inputMode="numeric" value={d.trigger.within_days} onChange={(e) => setTrigger({ within_days: Number(e.target.value) || 0 })} /></label>
          <label className="field"><span>Priority from</span><input className="input num" inputMode="numeric" value={d.trigger.min_priority} onChange={(e) => setTrigger({ min_priority: Number(e.target.value) || 0 })} /></label>
          <div className="field"><span>Fit</span>
            <div className="actions">
              {["A", "B"].map((t) => (
                <label key={t} className="choice"><input type="checkbox" checked={d.trigger.fit_tiers.includes(t)} onChange={() => setTrigger({ fit_tiers: toggle(d.trigger.fit_tiers, t) })} />Tier {t}</label>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <Section title="Who to reach, in this order">
        <div className="choices">
          {PERSONAS.map(([k, l]) => (
            <label key={k} className="choice">
              <input type="checkbox" checked={d.personas.includes(k)} onChange={() => set({ personas: toggle(d.personas, k) })} />
              {l}{d.personas.includes(k) ? <span className="mute small">{d.personas.indexOf(k) + 1}</span> : null}
            </label>
          ))}
        </div>
        <div className="form-row">
          <label className="field"><span>People per account, at most</span><input className="input num" inputMode="numeric" value={d.max_people} onChange={(e) => set({ max_people: Number(e.target.value) || 1 })} /></label>
          <label className="field"><span>Held back, not contacted, %</span><input className="input num" inputMode="numeric" value={d.holdout_pct} onChange={(e) => set({ holdout_pct: Number(e.target.value) || 0 })} /></label>
          <label className="field"><span>First email within, hours</span><input className="input num" inputMode="numeric" value={d.latency_hours} onChange={(e) => set({ latency_hours: Number(e.target.value) || 4 })} /></label>
        </div>
        <label className="choice"><input type="checkbox" checked={d.urgent} onChange={(e) => set({ urgent: e.target.checked })} />Decide within a day</label>
      </Section>

      <Section title="Sequence">
        <div className="ledger">
          {d.sequence.map((s, i) => (
            <div key={i} className="row" style={{ gridTemplateColumns: "92px minmax(0,1fr) 120px 44px" }}>
              <label className="sr-only" htmlFor={`day${i}`}>Day</label>
              <input id={`day${i}`} className="input num" style={{ width: 72 }} inputMode="numeric" value={s.day} onChange={(e) => setStep(i, { day: Number(e.target.value) || 0 })} aria-label="Day" />
              <select className="select" value={`${s.channel}:${s.job}`} aria-label="Step" onChange={(e) => {
                const k = STEP_KINDS.find((x) => x[0] === e.target.value)!;
                setStep(i, { channel: k[2], job: k[3], by: k[2] === "email" ? "desk" : "sdr" });
              }}>
                {STEP_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <span className="mute small">{s.by === "desk" ? "Desk sends" : "SDR does it"}</span>
              <button className="iconbtn" aria-label="Remove step" onClick={() => set({ sequence: d.sequence.filter((_, j) => j !== i) })}><Trash size={16} /></button>
            </div>
          ))}
        </div>
        <button className="btn quiet sm" onClick={() => set({ sequence: [...d.sequence, { day: (d.sequence.at(-1)?.day || 0) + 3, channel: "email", job: "follow_up", by: "desk" }] })}>
          <Plus size={14} />Add a step</button>
      </Section>

      <PlayPreview pv={pv} error={pvError} missing={missing} />

      {canSave ? (
        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn" disabled={busy || !pv} onClick={save}>{id ? "Save changes" : "Save draft"}</button>
        </div>
      ) : null}
    </div>
  );
}

export function PlayPreview({ pv, error, missing }: { pv: any; error: string | null; missing?: string[] }) {
  if (error) return <Section title="If it were live today"><div className="mute">{error}</div></Section>;
  if (!pv) return <Section title="If it were live today"><Empty title={missing?.length ? `Still needed: ${missing.join(", ")}` : "Working it out"} /></Section>;
  const p = pv.preview, c = pv.cost;
  return (
    <>
      <Section title="If it were live today">
        <div className="figs">
          <Fig value={n0(p.free_now)} label="Accounts it would propose now" />
          <Fig value={n0(p.per_month_contacted)} label="Contacted a month" />
          <Fig value={n0(p.per_month_held_back)} label="Held back a month" />
          {p.in_another_play ? <Fig value={n0(p.in_another_play)} label="Already in another play" /> : null}
        </div>
        {p.sample.length ? (
          <div className="ledger">
            {p.sample.map((a: any) => (
              <div key={a.id} className="row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto" }}>
                <Logo domain={a.primary_domain} name={a.name} />
                <div className="cell-main"><span className="t">{a.name}</span><span className="s">{a.signal}, tier {a.fit_tier}</span></div>
                <span className="num"><span className="mute small">Priority </span>{a.priority}</span>
              </div>
            ))}
          </div>
        ) : null}
      </Section>
      {c ? (
        <Section title="What it costs, worst case">
          <div className="ledger">
            {Object.entries(c.per_account.credits as Record<string, number>).filter(([, v]) => v > 0).map(([k, v]) => (
              <div key={k} className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 140px 160px" }}>
                <span>{VENDOR[k] || k}</span>
                <span className="num">{v} <span className="mute small">an account</span></span>
                <span className="num strong">{n0(c.per_month.credits[k])} <span className="mute small">credits a month</span></span>
              </div>
            ))}
            <div className="row" style={{ gridTemplateColumns: "minmax(0,1fr) 140px 160px" }}>
              <span>AI</span>
              <span className="num">${c.per_account.ai_dollars.toFixed(2)} <span className="mute small">an account</span></span>
              <span className="num strong">${n0(c.per_month.ai_dollars)} <span className="mute small">a month</span></span>
            </div>
          </div>
        </Section>
      ) : null}
    </>
  );
}

const VENDOR: Record<string, string> = { people_search: "People search", email_finder: "Email finder",
  email_verifier: "Email verification", phone_finder: "Phone finder", anthropic: "AI" };
