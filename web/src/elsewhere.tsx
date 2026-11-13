// The other desks (shared-world DESIGN 2b and 9), kept in one file so the way they show can change cheaply.
// Alone, none of this renders: no links, no calls, the screens are the standalone ones.
import { useEffect } from "react";
import { ArrowSquareOut } from "@phosphor-icons/react";
import { Section, dayTime, day, useData } from "./lib";

export type Integration = { integrated_with: string[]; links: Record<string, string> };
const NONE: Integration = { integrated_with: [], links: {} };

export const DESK_NAME: Record<string, string> = { crm_desk: "CRM Desk", market_desk: "Market Desk", events_desk: "Events Desk" };

export function useIntegration(): Integration {
  return useData<{ integration?: Integration }>("/api/me").data?.integration ?? NONE;
}

/** True when another desk owns this job (INTEGRATED_WITH names it). */
export const keptBy = (i: Integration, desk: string) => i.integrated_with.includes(desk);

/** Once per page load the linked desks start waking (a free plan sleeps them) while the visitor reads. */
export function usePrewarm(links: Record<string, string> | undefined) {
  useEffect(() => {
    for (const url of Object.values(links ?? {})) fetch(`${url}/api/health`, { mode: "no-cors" }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(links ?? {})]);
}

type Row = { desk: string; says: string; href: string };

function Rows({ rows }: { rows: Row[] }) {
  return (
    <div className="ledger">
      {rows.map((r) => (
        <a key={r.desk} className="row" href={r.href} target="_blank" rel="noopener noreferrer" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
          <span className="cell-main"><span className="t">{DESK_NAME[r.desk]}</span><span className="s">{r.says}</span></span>
          <ArrowSquareOut size={15} className="mute" aria-hidden="true" />
        </a>
      ))}
    </div>
  );
}

const enc = encodeURIComponent;

/** The foot of an account sheet: one row per linked desk, saying what that desk holds for this account. */
export function ElsewhereAccount({ a }: { a: any }) {
  const i = useIntegration();
  const ref = a.world_id ? `world:${a.world_id}` : a.primary_domain ? `domain:${a.primary_domain}` : null;
  const rows: Row[] = [];
  if (ref) {
    if (i.links.crm_desk) rows.push({ desk: "crm_desk", says: "The record", href: `${i.links.crm_desk}/go/account/${enc(ref)}` });
    if (i.links.market_desk) rows.push({ desk: "market_desk", says: keptBy(i, "market_desk") && a.crm_segment ? a.crm_segment : "Tier and plan",
      href: `${i.links.market_desk}/go/account/${enc(ref)}` });
  }
  return rows.length ? <Section title="Elsewhere"><Rows rows={rows} /></Section> : null;
}

/** The foot of a person sheet: the contact in CRM Desk. A person with no world id or CRM id has no row. */
export function ElsewherePerson({ p }: { p: any }) {
  const i = useIntegration();
  const ref = p.world_id ? `world:${p.world_id}` : p.crm_id ? `crm:${p.crm_id}` : null;
  if (!ref || !i.links.crm_desk) return null;
  return <Section title="Elsewhere"><Rows rows={[{ desk: "crm_desk", says: "The contact", href: `${i.links.crm_desk}/go/contact/${enc(ref)}` }]} /></Section>;
}

/** Settings, with Market Desk present: the two things it keeps, in place of the profile and the accounts import. */
export function KeptInMarketDesk({ kept, links }: { kept: any; links: Record<string, string> }) {
  const base = links.market_desk;
  const inner = (t: string, s: string) => (
    <>
      <span className="cell-main"><span className="t">{t}</span><span className="s" style={{ whiteSpace: "normal" }}>{s}</span></span>
      {base ? <ArrowSquareOut size={15} className="mute" aria-hidden="true" /> : <span />}
    </>
  );
  const row = (path: string, t: string, s: string) => base
    ? <a className="row" href={`${base}${path}`} target="_blank" rel="noopener noreferrer" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>{inner(t, s)}</a>
    : <div className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>{inner(t, s)}</div>;
  return (
    <Section title="Kept in Market Desk">
      <div className="ledger">
        {row("/profile", "Ideal customer profile", kept.icp ? `Version ${kept.icp.id}, in force since ${day(kept.icp.published_at)}` : "None published yet")}
        {row("/accounts", "Accounts", `From Market Desk's book, through the record. ${kept.accounts_read_at ? `Last read ${dayTime(kept.accounts_read_at)}` : "Not read yet"}`)}
      </div>
    </Section>
  );
}
