import { useCallback, useEffect, useRef, useState, type ReactNode, useLayoutEffect } from "react";
import { api } from "./api";
import { STATUS_ICONS } from "./statusIcons";
import { STATUS_MEANING } from "./statusMeaning";
import { CheckCircle, Clock, PauseCircle, WarningCircle, type Icon } from "@phosphor-icons/react";

// ---------------------------------------------------------------- routing: the path is the state

export function navigate(to: string, replace = false) {
  if (replace) window.history.replaceState(null, "", to); else window.history.pushState(null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function usePath(): [string, URLSearchParams] {
  const [loc, setLoc] = useState(() => window.location.pathname + window.location.search);
  useEffect(() => {
    const on = () => setLoc(window.location.pathname + window.location.search);
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  const [path, search = ""] = loc.split("?");
  return [path, new URLSearchParams(search)];
}

export function withParam(key: string, value: string | null): string {
  const u = new URL(window.location.href);
  if (value === null) u.searchParams.delete(key); else u.searchParams.set(key, value);
  const q = u.searchParams.toString();
  return u.pathname + (q ? "?" + q : "");
}

export const useGo = () => useCallback((to: string, replace = false) => navigate(to, replace), []);

// ---------------------------------------------------------------- data

// A change anywhere tells every open view to refetch, so no screen shows a stale count.
const listeners = new Set<() => void>();
export function changed() { listeners.forEach((f) => f()); }

export function useData<T>(path: string | null): { data: T | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    const f = () => setN((x) => x + 1);
    listeners.add(f);
    return () => { listeners.delete(f); };
  }, []);
  useEffect(() => {
    if (!path) return;
    let live = true;
    api<T>(path).then((d) => { if (live) { setData(d); setError(null); } }).catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [path, n]);
  return { data, error, reload: () => setN((x) => x + 1) };
}

let toastSet: ((s: string | null) => void) | null = null;
export function toast(msg: string) { toastSet?.(msg); }
export function Toaster() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { toastSet = setMsg; return () => { toastSet = null; }; }, []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2800);
    return () => clearTimeout(t);
  }, [msg]);
  return msg ? <div className="toast" role="status">{msg}</div> : null;
}

export function useBusy(): [boolean, (f: () => Promise<unknown>, done?: string) => Promise<void>] {
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  useEffect(() => () => { live.current = false; }, []);
  const run = useCallback(async (f: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await f();
      if (done) toast(done);
      changed();
    } catch (e: any) {
      toast(e.message || "That did not go through.");
    } finally {
      if (live.current) setBusy(false);
    }
  }, []);
  return [busy, run];
}

// ---------------------------------------------------------------- formatting

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
let NOW = Date.now();
/** One name per paid vendor, on every page. */
export const VENDOR_NAME: Record<string, string> = {
  people_search: "People search", email_finder: "Email finder", email_verifier: "Email verification",
  phone_finder: "Phone finder", anthropic: "AI", research: "Website research",
};

export function setNow(iso: string) { NOW = new Date(iso).getTime(); }

export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (NOW - new Date(iso).getTime()) / 1000;
  if (s < -60) return ahead(iso);
  const say = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"} ago`;
  if (s < 3600) return say(Math.max(1, Math.round(s / 60)), "minute");
  if (s < 86400) return say(Math.round(s / 3600), "hour");
  if (s < 86400 * 14) return say(Math.round(s / 86400), "day");
  return day(iso);
}
export function ahead(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (new Date(iso).getTime() - NOW) / 1000;
  if (s < 0) return "overdue";  // callers that show it use late(), which says by how much
  const say = (n: number, unit: string) => `in ${n} ${unit}${n === 1 ? "" : "s"}`;
  if (s < 3600) return say(Math.max(1, Math.round(s / 60)), "minute");
  if (s < 86400) return say(Math.round(s / 3600), "hour");
  return say(Math.round(s / 86400), "day");
}
/** "Overdue by 2 days" for something past due; otherwise when it is due. One wording on every screen. */
export function late(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (NOW - new Date(iso).getTime()) / 1000;
  if (s <= 0) return ahead(iso);
  const say = (n: number, unit: string) => `Overdue by ${n} ${unit}${n === 1 ? "" : "s"}`;
  if (s < 3600) return say(Math.max(1, Math.round(s / 60)), "minute");
  if (s < 86400) return say(Math.round(s / 3600), "hour");
  return say(Math.round(s / 86400), "day");
}
export function useNowIso(): number { return NOW; }
/** A link from data (a source, a profile) only when it is http or https; anything else is not made a link. */
export function safeUrl(u: string | null | undefined): string | undefined {
  const t = (u || "").trim();
  return /^https?:\/\/[^\s/]+/i.test(t) ? t : undefined;
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
export function dayTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
export function weekday(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" });
}
export const pct = (x: number | null | undefined, digits = 0) => (x === null || x === undefined ? "" : `${(x * 100).toFixed(digits)}%`);
export const n0 = (x: number | null | undefined) => (x === null || x === undefined ? "" : Math.round(x).toLocaleString("en-US"));
export function money(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "";
  const d = cents / 100;
  if (d >= 1_000_000) return `$${(d / 1_000_000).toFixed(1)}M`;
  if (d >= 10_000) return `$${Math.round(d / 1000)}k`;
  return `$${d.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}
export function initials(name: string): string {
  return name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w) && !/^(Dr|Mr|Ms|Mrs)\.?$/.test(w)).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase();
}
export const cap = (s: string | null | undefined) => (s ? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "");

// ---------------------------------------------------------------- shared parts

export type Glyph = "ok" | "go" | "wait" | "half" | "stop" | "off" | "hold" | "none";

// A status is a small icon and a word. Colour only for the states that need someone's attention.
const FALLBACK: Partial<Record<Glyph, Icon>> = { wait: Clock, stop: WarningCircle, hold: PauseCircle, ok: CheckCircle };
// The accent is for what can be pressed (Instrument T1), so states never wear it. Ink by default; colour only where
// someone must act (amber on hold, red stopped or failed); green for a healthy, working state.
const TONE: Partial<Record<Glyph, string>> = { wait: "var(--ink-2)", stop: "var(--stop)", hold: "var(--wait)", ok: "var(--ok)" };
// Running states: something is happening right now, so they read as on air instead of as a still icon.
const LIVE = new Set(["Live", "Sending mail", "In sequence", "Reaching out", "Watching"]);
export function Status({ kind, children, title }: { kind: Glyph; children: ReactNode; title?: string }) {
  const word = typeof children === "string" ? children : "";
  const meaning = title ?? STATUS_MEANING[word];
  if (LIVE.has(word)) {
    const Plane = STATUS_ICONS["Live"];
    return <span className="status live" title={meaning}><Plane size={15} weight="regular" aria-hidden="true" className="breathe" />{children}</span>;
  }
  const Ic = STATUS_ICONS[word] || FALLBACK[kind];
  return (
    <span className="status" title={meaning}>
      {Ic ? <Ic size={15} weight={kind === "wait" || kind === "stop" ? "bold" : "regular"} aria-hidden="true"
        style={{ color: TONE[kind] || "var(--mute)", flex: "none" }} /> : null}
      {children}
    </span>
  );
}

/** A number that counts to its value: "$1,234.50", "56", "12%". Anything else is shown as it is. */
export function Count({ value }: { value: ReactNode }) {
  const text = typeof value === "number" ? value.toLocaleString("en-US") : typeof value === "string" ? value : null;
  const m = text?.match(/^([^0-9-]*)(-?[0-9][0-9,]*(?:\.[0-9]+)?)(.*)$/);
  const target = m ? Number(m[2].replace(/,/g, "")) : NaN;
  const decimals = m && m[2].includes(".") ? m[2].split(".")[1].length : 0;
  const [shown, setShown] = useState(() => (reduced() ? target : 0));
  const from = useRef(0);
  useEffect(() => {
    if (!m || Number.isNaN(target) || reduced() || /\b(ago|in|day|days|hour|hours|minute|minutes|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|:\d\d/.test(m[3])) { setShown(target); return; }
    const start = performance.now(), a = from.current, dur = 520;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      setShown(a + (target - a) * e);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!m || Number.isNaN(target) || /\b(ago|in|day|days|hour|hours|minute|minutes|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|:\d\d/.test(m[3])) return <>{value}</>;
  const body = shown.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return <span className="count-up" aria-label={text!}>{m[1]}{body}{m[3]}</span>;
}
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function Fig({ value, label, unit, onClick, sm }: { value: ReactNode; label: string; unit?: string; onClick?: () => void; sm?: boolean }) {
  const inner = <><b><Count value={value} />{unit ? <small>{unit}</small> : null}</b><span>{label}</span></>;
  if (onClick) {
    return <button type="button" className={`fig go${sm ? " sm" : ""}`} onClick={onClick}
      style={{ background: "none", border: 0, borderLeft: "1px solid var(--line)", textAlign: "left", font: "inherit", color: "inherit" }}>{inner}</button>;
  }
  return <div className={`fig${sm ? " sm" : ""}`}>{inner}</div>;
}

export function Bar({ label, value, of, shown, tone, hint }: { label: ReactNode; value: number; of: number; shown?: ReactNode; tone?: "soft" | "accent"; hint?: ReactNode }) {
  const w = of > 0 ? Math.max(0, Math.min(1, value / of)) : 0;
  return (
    <div className="barrow">
      <span className="lbl">{label}</span>
      <span className="track"><i className={`fill${tone ? " " + tone : ""}`} style={{ width: `${(w * 100).toFixed(1)}%` }} /></span>
      <span className="val">{shown ?? n0(value)}{hint ? <small>{hint}</small> : null}</span>
    </div>
  );
}

export function Empty({ title, children, icon: Ic = CheckCircle }: { title: string; children?: ReactNode; icon?: Icon }) {
  return (
    <div className="empty" role="status">
      <span className="empty-icon" aria-hidden="true"><Ic size={18} /></span>
      <div><b>{title}</b>{children}</div>
    </div>
  );
}

export function Loading({ rows = 6 }: { rows?: number }) {
  return (
    <div className="ledger" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ margin: "4px 0" }} />)}
    </div>
  );
}

export function Failed({ error, retry }: { error: string; retry: () => void }) {
  return <div className="empty" role="alert"><b>Could not load this.</b>{error} <button className="btn quiet sm" onClick={retry}>Try again</button></div>;
}

export function Section({ title, count, right, icon: Ic, children }: { title: string; count?: number; right?: ReactNode; icon?: Icon; children: ReactNode }) {
  return (
    <section className="section">
      <header><h2>{Ic ? <Ic size={17} className="h-icon" aria-hidden="true" /> : null}{title}{count !== undefined ? <span className="count">{count}</span> : null}</h2>{right}</header>
      {children}
    </section>
  );
}

export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, ReactNode][]; onChange: (v: T) => void; label: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<{ left: number; width: number } | null>(null);
  const place = useCallback(() => {
    const on = box.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]');
    if (on) setThumb({ left: on.offsetLeft, width: on.offsetWidth });
  }, []);
  useLayoutEffect(place, [value, options.length, place]);
  useEffect(() => {
    if (!box.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(place); ro.observe(box.current);
    return () => ro.disconnect();
  }, [place]);
  return (
    <div className="seg" role="group" aria-label={label} ref={box}>
      {thumb ? <i className="seg-thumb" aria-hidden="true" style={{ transform: `translateX(${thumb.left - 3}px)`, width: thumb.width }} /> : null}
      {options.map(([v, l]) => <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}
