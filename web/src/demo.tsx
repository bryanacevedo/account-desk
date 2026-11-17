// What a visitor to the sample world needs before they touch anything: that it is a sample, what the date means, what a
// click will do, where to start. Nothing here renders on a real install (simulation fixes 2, 3, 4, 5, 6, 18).
import { useEffect, useState, type ReactNode } from "react";
import { navigate } from "./lib";

/** The one sentence the public demo's refusal already uses (api/app.py PUBLIC_DEMO_MESSAGE, scripts/static_snapshot/shim.js). */
export const REFUSAL = "Not available in the public demo.";

/** Where a buyer goes next. Not decided: left empty on purpose so no invented address ships. Set it to a real contact
 *  link (a booking page or a mailto:) and the next-step line below becomes a link. */
export const NEXT_STEP_URL = "";

export type DemoMe = { simulated: boolean; public_demo: boolean; now: string; snapshot?: { taken_on: string } };

export const isSample = (me: DemoMe | null | undefined) => !!me && (me.simulated || me.public_demo || !!me.snapshot);

/** "Thu 12 Nov 2026", the sample day, from the demo's own clock. */
export function sampleDay(iso: string): string {
  const d = new Date(iso);
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" })
    .formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month} ${p.year}`;
}

const KEY = "ad-demo-bar-dismissed";
const read = () => { try { return sessionStorage.getItem(KEY) === "1"; } catch { return false; } };

/** One slim bar at the top of every screen, desktop and phone, while the desk runs its sample world. Dismissible for the session. */
export function DemoBar({ me }: { me: DemoMe }) {
  const [gone, setGone] = useState(read);
  if (gone) return null;
  const snap = !!me.snapshot;
  return (
    <div className="demo-bar" role="note">
      <span className="demo-text">
        <b>Sample company, invented data.</b>{" "}
        {snap
          ? <>This is a read-only snapshot taken {me.snapshot!.taken_on}: changes are not saved. A change you try answers &ldquo;{REFUSAL}&rdquo;</>
          : me.public_demo
            ? <>Everyone who visits shares this demo. Changes that would affect all of them are refused with &ldquo;{REFUSAL}&rdquo;</>
            : <>Every vendor and signal here is simulated.</>}{" "}
        <span className="demo-day">Sample day: {sampleDay(me.now)} (the demo keeps its own clock).</span>
      </span>
      <button className="demo-start" onClick={() => navigate("/")}>Start here</button>
      <button className="demo-x" aria-label="Hide this notice" onClick={() => { try { sessionStorage.setItem(KEY, "1"); } catch { /* private mode */ } setGone(true); }}>Hide</button>
    </div>
  );
}

// Buttons that change something. On the read-only snapshot each says so before the click, in the tooltip.
const WRITES = /^(accept|skip|approve|reject|send|save|add\b|move\b|propose|log\b|hold|erase|dismiss|pause|resume|publish|cancel|it happened|they did not|lift|set\b|mark|turn|start|create|make|use this|import|rewrite|edit)/i;

/** On the snapshot every write is refused. Say so on every write control before it is clicked: a tooltip on the button
 *  (a phone has the notice at the top). Buttons are found by their words, so a new write button with an unusual
 *  name still works, it just does not carry the tooltip. */
export function useRefusalTitles(on: boolean) {
  useEffect(() => {
    if (!on) return;
    const mark = () => document.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
      if (b.title || b.closest(".demo-bar") || b.getAttribute("role") === "tab") return;
      const t = (b.textContent || "").trim();
      if (t && WRITES.test(t)) b.title = `${REFUSAL} This page is a read-only snapshot: nothing you change is saved.`;
    });
    mark();
    const mo = new MutationObserver(mark);
    mo.observe(document.body, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [on]);
}

/** One short line under a heading that says what the words on the page mean. */
export function Hint({ children }: { children: ReactNode }) {
  return <p className="hint">{children}</p>;
}

/** The mark beside a name that is invented for the sample (a vendor, a tool, a source). */
export function Sample({ children = "sample" }: { children?: ReactNode }) {
  return <span className="sample-tag" title="Invented for this sample company">{children}</span>;
}

/** The first screen of the sample: what this is for, one first step, and two short paths. */
export function Welcome({ firstStep }: { firstStep: { label: string; go: () => void } | null }) {
  const [shut, setShut] = useState(() => { try { return localStorage.getItem("ad-welcome-shut") === "1"; } catch { return false; } });
  if (shut) return (
    <div className="welcome-closed"><button className="link" onClick={() => { try { localStorage.removeItem("ad-welcome-shut"); } catch { /* private mode */ } setShut(false); }}>Show the tour again</button></div>
  );
  return (
    <section className="welcome" aria-label="What this is and where to start">
      <p className="welcome-value">Account Desk watches a company&rsquo;s accounts for signs they may buy, proposes who to contact and why now, drafts the emails, and waits for a person to approve every one.</p>
      <div className="welcome-first">
        {firstStep ? <button className="btn" onClick={firstStep.go}>{firstStep.label}</button> : null}
        <span className="mute small">Takes about a minute. Nothing is sent: every email and vendor here is simulated.</span>
      </div>
      <details className="tour">
        <summary>Take the tour</summary>
        <div className="tour-paths">
          <div>
            <h3>If you are hiring</h3>
            <ol>
              <li>Today: what needs a person right now.</li>
              <li>Open the first email waiting: it cites the facts it uses.</li>
              <li>Plays: the rule behind each proposal.</li>
              <li>Results: whether outreach beats leaving accounts alone.</li>
            </ol>
          </div>
          <div>
            <h3>If you are buying</h3>
            <ol>
              <li>Signals: what the desk watches, and where from.</li>
              <li>Accounts: who is worth contacting, and why.</li>
              <li>In flight: each person&rsquo;s sequence, with the next step.</li>
              <li>Results: meetings and deals, against accounts held back.</li>
            </ol>
            <p className="tour-next"><b>Next step:</b>{" "}
              {NEXT_STEP_URL ? <a href={NEXT_STEP_URL} className="link">Run this on your own accounts and data.</a> : "to run this on your own accounts and data, get in touch with Leandrive."}</p>
          </div>
        </div>
      </details>
      <button className="link small" onClick={() => { try { localStorage.setItem("ad-welcome-shut", "1"); } catch { /* private mode */ } setShut(true); }}>Hide this</button>
    </section>
  );
}
