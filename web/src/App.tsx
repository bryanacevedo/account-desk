import { useEffect, useState, type ReactNode } from "react";
import {
  CaretRight, ChartLineUp, CheckSquare, ChatsCircle, DotsThree, GearSix, Lightning, ListChecks, Pulse, Sun, Target,
  EnvelopeSimple, PaperPlaneTilt,
} from "@phosphor-icons/react";
import { api, setActingAs } from "./api";
import { Toaster, changed, navigate, setNow, toast, useBusy, useData, usePath } from "./lib";
import { SheetHost } from "./sheets";
import { Accounts, Today } from "./pages/Work";
import { Flight } from "./pages/Flight";
import { Approvals, Plays, Replies, Signals } from "./pages/Flow";
import { Deliverability, Ops, Results, Settings } from "./pages/Desk";

type Me = { user: { id: number; name: string; role: string }; users: any[]; counts: Record<string, number>; money: boolean;
  now: string; simulated: boolean; public_demo: boolean; company: string };

const ROUTES: { path: string; label: string; icon: ReactNode; page: () => JSX.Element; roles?: string[]; count?: string; group?: string; offBar?: boolean }[] = [
  { path: "/", label: "Today", icon: <Sun size={18} />, page: Today, count: "today" },
  { path: "/in-flight", label: "In flight", icon: <PaperPlaneTilt size={18} />, page: Flight },
  { path: "/accounts", label: "Accounts", icon: <Target size={18} />, page: Accounts, offBar: true },
  { path: "/approvals", label: "Approvals", icon: <CheckSquare size={18} />, page: Approvals, count: "approvals" },
  { path: "/replies", label: "Replies", icon: <ChatsCircle size={18} />, page: Replies, count: "replies" },
  { path: "/signals", label: "Signals", icon: <Lightning size={18} />, page: Signals, group: "How it works" },
  { path: "/plays", label: "Plays", icon: <ListChecks size={18} />, page: Plays },
  { path: "/results", label: "Results", icon: <ChartLineUp size={18} />, page: Results },
  { path: "/inboxes", label: "Inboxes", icon: <EnvelopeSimple size={18} />, page: Deliverability, roles: ["gtm", "manager"], group: "Running it" },
  { path: "/health", label: "Health", icon: <Pulse size={18} />, page: Ops, roles: ["gtm", "manager"] },
  { path: "/settings", label: "Settings", icon: <GearSix size={18} />, page: Settings, roles: ["gtm", "manager"] },
];

const ROLE: Record<string, string> = { sdr: "SDR", manager: "Manager", gtm: "GTM" };

export function App() {
  const [path] = usePath();
  const { data: me } = useData<Me>("/api/me");
  const [, setTick] = useState(0);
  useEffect(() => { if (me?.now) setNow(me.now); }, [me?.now]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if ((t && typeof t.closest === "function" && t.closest("input, textarea, select")) || e.metaKey || e.ctrlKey) return;
      const map: Record<string, string> = { t: "/", a: "/accounts", p: "/approvals", r: "/replies", s: "/signals" };
      if (map[e.key] && !new URLSearchParams(window.location.search).get("sheet")) navigate(map[e.key]);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  const routes = ROUTES.filter((r) => !r.roles || (me && r.roles.includes(me.user.role)));
  // The phone's bottom bar: the first four pages that belong there; everything else is under More.
  const bar = routes.filter((r) => !r.offBar).slice(0, 4);
  const rest = routes.filter((r) => !bar.includes(r));
  const more = { path: "/more", label: "More", icon: null, page: () => <More routes={rest} me={me} /> } as any;
  const route = path === "/more" ? more : routes.find((r) => r.path === path) || routes[0];
  const Page = route.page;
  useEffect(() => { document.title = `${route.label}, Account Desk`; }, [route.label]);
  const nav = (
    <nav className="nav" aria-label="Main">
      {routes.map((r) => (
        <div key={r.path} style={{ display: "contents" }}>
          {r.group ? <div className="group">{r.group}</div> : null}
          <a href={r.path} aria-current={r.path === route.path ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); navigate(r.path); }}>
            {r.icon}<span>{r.label}</span>
            {r.count && me?.counts[r.count] ? <span className="n" aria-label={`${me.counts[r.count]} waiting`}>{me.counts[r.count]}</span> : null}
          </a>
        </div>
      ))}
    </nav>
  );
  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><Mark />Account Desk</div>
        {nav}
        <div className="grow" />
        <div className="side-foot">
          {me?.simulated ? <Clock me={me} /> : null}
          {me && me.users.length ? (
            <div className="acting">
              <label htmlFor="acting">Acting as</label>
              <select id="acting" className="select" value={me.user.id} onChange={(e) => { setActingAs(Number(e.target.value)); changed(); setTick((x) => x + 1); }}>
                {me.users.map((u) => <option key={u.id} value={u.id}>{u.name}, {ROLE[u.role]}</option>)}
              </select>
            </div>
          ) : null}
        </div>
      </aside>
      <main className="main">
        <div className="phone-bar">
          <span className="brand" style={{ margin: 0 }}><Mark />{route.label}</span>
          {me && me.users.length ? (
            <select className="select" style={{ width: 170, height: 40 }} value={me.user.id} aria-label="Acting as"
              onChange={(e) => { setActingAs(Number(e.target.value)); changed(); }}>
              {me.users.map((u) => <option key={u.id} value={u.id}>{u.name.split(" ")[0]}, {ROLE[u.role]}</option>)}
            </select>
          ) : null}
        </div>
        {me ? <Page key={`${route.path}:${me.user.id}`} /> : null}
      </main>
      <nav className="phone-nav" aria-label="Main">
        {bar.map((r) => (
          <a key={r.path} href={r.path} aria-current={r.path === route.path ? "page" : undefined} onClick={(e) => { e.preventDefault(); navigate(r.path); }}>
            <span className="pn-icon">{r.icon}{r.count && me?.counts[r.count] ? <i className="pn-n">{me.counts[r.count]}</i> : null}</span><span>{r.label}</span>
          </a>
        ))}
        <a href="/more" aria-current={route.path === "/more" || rest.some((r) => r.path === route.path) ? "page" : undefined}
          onClick={(e) => { e.preventDefault(); navigate("/more"); }}><span className="pn-icon"><DotsThree size={18} weight="bold" /></span><span>More</span></a>
      </nav>
      <SheetHost />
      <Toaster />
    </div>
  );
}

// The pages that do not fit the phone's bottom bar, and the demo clock.
function More({ routes, me }: { routes: typeof ROUTES; me: Me | null }) {
  return (
    <div className="page">
      <div className="head"><h1>More</h1></div>
      <div className="ledger">
        {routes.map((r) => (
          <a key={r.path} href={r.path} className="row" style={{ gridTemplateColumns: "24px minmax(0,1fr) auto" }}
            onClick={(e) => { e.preventDefault(); navigate(r.path); }}>
            <span className="mute">{r.icon}</span><span className="cell-main"><span className="t">{r.label}</span></span><CaretRight size={16} className="mute" />
          </a>
        ))}
      </div>
      {me?.simulated ? <Clock me={me} /> : null}
    </div>
  );
}

function Clock({ me }: { me: Me }) {
  const [busy, run] = useBusy();
  const when = new Date(me.now).toLocaleString("en-US", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return (
    <div className="clock">
      <span className="when">{when}</span>
      <span className="note">A simulated company with invented accounts. Every vendor is simulated.</span>
      <button className="btn line sm" disabled={busy} onClick={() => run(async () => {
        const r = await api<any>("/api/sim/advance", { method: "POST", body: { hours: 24 } });
        toast(`A day passed: ${r.signals} new signals.`);
      })}>{busy ? "Working" : "Move a day ahead"}</button>
    </div>
  );
}

/** The Account Desk mark: one account, the people in it, one still to reach. */
function Mark() {
  return <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#2B47C9"/><rect x="8.5" y="8.5" width="15" height="15" rx="4" stroke="#fff" strokeWidth="2.4" fill="none"/><circle cx="13" cy="13" r="1.9" fill="#fff"/><circle cx="19" cy="13" r="1.9" fill="#fff"/><circle cx="13" cy="19" r="1.9" fill="#fff"/><circle cx="19" cy="19" r="1.9" fill="#fff" fillOpacity=".45"/></svg>;
}
