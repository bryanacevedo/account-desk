import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";

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
export function setNow(iso: string) { NOW = new Date(iso).getTime(); }

export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (NOW - new Date(iso).getTime()) / 1000;
  if (s < -60) return ahead(iso);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.round(s / 86400)} d ago`;
  return day(iso);
}
export function ahead(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (new Date(iso).getTime() - NOW) / 1000;
  if (s < 0) return "due";
  if (s < 3600) return `in ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `in ${Math.round(s / 3600)} h`;
  return `in ${Math.round(s / 86400)} d`;
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

// A shape only where the state needs someone's attention (waiting, stopped, on hold). Everything else is a word.
const ATTENTION = new Set<Glyph>(["wait", "stop", "hold"]);
export function Status({ kind, children }: { kind: Glyph; children: ReactNode }) {
  return <span className="status">{ATTENTION.has(kind) ? <i className={`glyph ${kind}`} aria-hidden="true" /> : null}{children}</span>;
}

export function Fig({ value, label, unit, onClick, sm }: { value: ReactNode; label: string; unit?: string; onClick?: () => void; sm?: boolean }) {
  const inner = <><b>{value}{unit ? <small>{unit}</small> : null}</b><span>{label}</span></>;
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

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty" role="status"><b>{title}</b>{children}</div>;
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

export function Section({ title, count, right, children }: { title: string; count?: number; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      <header><h2>{title}{count !== undefined ? <span className="count">{count}</span> : null}</h2>{right}</header>
      {children}
    </section>
  );
}

export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}
