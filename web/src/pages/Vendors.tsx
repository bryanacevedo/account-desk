import { Fragment } from "react";
import { Empty, Failed, Fig, Loading, Section, Status, ago, n0, useData } from "../lib";
import { openSheet } from "../sheets";

/** Dollars with cents: these are small numbers, and $0 would hide them. */
const usd = (cents: number) => `$${(Number(cents) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
/** A per-credit rate under a dollar reads in cents. */
const rate = (cents: number) => (cents < 100 ? `${Number(cents).toLocaleString("en-US", { maximumFractionDigits: 2 })}¢` : usd(cents));

const STATE: Record<string, ["ok" | "off" | "stop", string, string]> = {
  connected: ["ok", "Connected", "A real account is connected and the desk uses it."],
  simulated: ["off", "Simulated", "This demo stands in for the vendor. Nothing real is called and the prices are assumed."],
  not_connected: ["off", "Not connected", "Not set up. Work that needs it waits, or is skipped for optional vendors, and the team is told."],
  webhook: ["ok", "Webhook", "Sends events to the desk as they happen."],
};
const PAID: Record<string, [string, string]> = {
  metered: ["Pay per use", "Charged per lookup or per token. The desk meters every call and holds it to the monthly cap."],
  subscription: ["Subscription", "A flat fee paid to the vendor. The desk does not see the bill, so no figure is shown."],
  free: ["Free", "No charge to use."],
};

/** Every system the desk touches, whether it costs money, whether it is connected, and what this month cost. */
export function Vendors() {
  const { data, error, reload } = useData<any>("/api/vendors");
  if (error) return <div className="page"><Failed error={error} retry={reload} /></div>;
  if (!data) return <div className="page"><div className="head"><h1>Vendors and costs</h1></div><Loading rows={10} /></div>;
  const groups = [...new Set<string>(data.vendors.map((v: any) => v.group))];
  const playTotal = data.by_play.reduce((t: number, p: any) => t + Number(p.cents), 0);
  const demo = data.mode === "demo";
  return (
    <div className="page">
      <div className="head"><div><h1>Vendors and costs</h1>
        <p className="sub">{demo ? "Demo: every vendor is simulated and every price is an assumption." : `Day ${data.day} of ${data.days} this month.`}
          {!demo && data.assumed ? " Some flat fees are still assumptions, not figures from a bill." : ""}</p></div></div>
      <div className="figs">
        <Fig value={usd(data.total_cents)} label={`This month so far, day ${data.day} of ${data.days}`} />
        <Fig value={usd(data.projected_cents)} label="At this pace, by month end" />
        <Fig value={usd(data.last_month.cents)} label="Last month, with this month's flat fees" />
      </div>
      <div className="figs">
        <Fig sm value={usd(data.metered_cents)} label="Data and AI, metered" />
        <Fig sm value={usd(data.flat_so_far_cents)} label={`Flat fees so far, of ${usd(data.flat_cents)}`} />
        <Fig sm value={n0(data.credits)} label={`Data credits, ${n0(data.last_month.credits)} last month`} />
        <Fig sm value={data.last_month.per_meeting_cents == null ? "None yet" : usd(data.last_month.per_meeting_cents)}
          label={`Per outbound meeting, last month (${n0(data.last_month.meetings)})`} />
      </div>

      <Section title="Vendors" count={data.vendors.length}>
        <div className="ledger vendors">
          <div className="row head" style={{ gridTemplateColumns: V_COLS }}>
            <span>Vendor</span><span>Cost</span><span>Status</span><span className="num">This month</span><span className="num">Cap used</span>
          </div>
          {groups.map((g) => (
            <Fragment key={g}>
              <div className="row group-head"><span>{g}</span></div>
              {data.vendors.filter((v: any) => v.group === g).map((v: any) => <VendorRow key={v.key} v={v} demo={demo} />)}
            </Fragment>
          ))}
        </div>
      </Section>

      <Section title="Data and AI spend by play" count={data.by_play.length}>
        {data.by_play.length ? (
          <div className="ledger">
            <div className="row head" style={{ gridTemplateColumns: P_COLS }}><span>Play</span><span className="num">Accounts</span><span className="num">Spent</span><span className="num">Share</span></div>
            {data.by_play.map((p: any) => (
              <button key={p.id} className="row" onClick={() => openSheet("play", p.id)} style={{ gridTemplateColumns: P_COLS }}>
                <span className="cell-main"><span className="t">{p.name}</span></span>
                <span className="num" data-label="Accounts">{n0(p.accounts)}</span>
                <span className="num strong" data-label="Spent">{usd(Number(p.cents))}</span>
                <span className="num mute" data-label="Share">{playTotal ? Math.round((Number(p.cents) / playTotal) * 100) : 0}%</span>
              </button>
            ))}
          </div>
        ) : <Empty title="Nothing charged to a play this month" />}
        {data.untagged_cents ? <p className="mute small" style={{ marginTop: 8 }}>{usd(data.untagged_cents)} was not for any play.</p> : null}
      </Section>

      <Section title="Signal sources" count={data.sources.length}>
        <div className="ledger">
          <div className="row head" style={{ gridTemplateColumns: S_COLS }}><span>Source</span><span>Cost</span><span>Status</span><span className="num">Signals this month</span><span className="num">Last run</span></div>
          {data.sources.map((s: any) => {
            const st = STATE[s.status];
            return (
              <div key={s.key} className="row" style={{ gridTemplateColumns: S_COLS }}>
                <span className="cell-main"><span className="t">{s.label}</span>{s.enabled ? null : <span className="s">Switched off</span>}</span>
                <span data-label="Cost" title={s.paid ? "A paid data feed, billed by the vendor as a subscription." : "No charge to use."}>
                  {s.subscription ? `${usd(s.subscription.monthly_cents)} a month` : s.key === "crm" ? "Part of the CRM" : s.key === "enrichment" ? "Company data, above" : s.paid ? "Subscription" : "Free"}</span>
                <span data-label="Status"><Status kind={st[0]} title={st[2]}>{st[1]}</Status></span>
                <span className="num" data-label="Signals">{n0(s.signals)}</span>
                <span className="num mute" data-label="Last run">{s.last_run ? ago(s.last_run) : "Never"}</span>
              </div>
            );
          })}
        </div>
      </Section>
    </div>
  );
}

const V_COLS = "minmax(0,1.8fr) 120px 120px 110px 80px";
const P_COLS = "minmax(0,1fr) 90px 100px 70px";
const S_COLS = "minmax(0,1.4fr) 120px 120px 140px 110px";

function VendorRow({ v, demo }: { v: any; demo: boolean }) {
  const st = STATE[v.status];
  const paid = PAID[v.paid];
  const capUsed = v.cap ? (v.cap_unit === "cents" ? v.cents / v.cap : v.used / v.cap) : null;
  const sub = v.subscription;
  const per = sub ? (sub.per === "mailbox" ? `${usd(sub.unit_cents)} a mailbox` : sub.per === "sender" ? `${usd(sub.unit_cents)} a sender` : `${usd(sub.unit_cents)} a month`) : null;
  const price = sub ? per : v.paid !== "metered" ? paid[0]
    : v.key === "anthropic" ? "Per token"
    : v.rate_cents ? `${rate(v.rate_cents)} a credit` : "Per credit";
  const capText = v.cap ? (v.cap_unit === "cents" ? `Monthly cap ${usd(v.cap)}` : `Monthly cap ${n0(v.cap)} credits`) : undefined;
  return (
    <div className="row" style={{ gridTemplateColumns: V_COLS }}>
      <span className="cell-main"><span className="t">{v.name}</span><span className="s wrap">{v.purpose}</span>
        {v.suggest ? <span className="s wrap suggest" title="What we would use for this. Prices on this page are our own assumptions, not this vendor's.">We'd use: {v.suggest}</span> : null}
        {v.waterfall?.length ? (
          <span className="finders" aria-label="Email finders, asked in order"
            title="Each finder is asked when the one before found nothing, or found an address that failed its check.">
            <span className="fh">Finder</span><span className="fh num">Asked</span><span className="fh num">Found</span>
            {v.waterfall.map((w: any) => (
              <Fragment key={w.provider}>
                <span>{w.step}. {w.name}</span><span className="num">{n0(w.asked)}</span><span className="num">{n0(w.found)}</span>
              </Fragment>
            ))}
          </span>
        ) : null}
        <span className="s only-sm">{[price, st[1], v.paid === "metered" ? usd(v.cents) + " this month" : sub ? usd(sub.monthly_cents) + " a month" : null,
          capUsed != null ? `${capUsed > 0 && capUsed < 0.01 ? "<1" : Math.round(capUsed * 100)}% of cap` : null].filter(Boolean).join(" · ")}</span></span>
      <span className="hide-sm" title={paid[1]}>{price}</span>
      <span className="hide-sm"><Status kind={st[0]} title={st[2]}>{st[1]}</Status></span>
      <span className="num hide-sm">
        {sub ? <><span className="strong">{usd(sub.monthly_cents)}</span><span className="s mute">{sub.per === "month" ? "flat" : `${n0(sub.count)} × ${usd(sub.unit_cents)}`}</span></>
          : v.paid !== "metered" ? <span className="mute">{v.paid === "free" ? "Free" : "Not entered"}</span>
          : <><span className="strong">{usd(v.cents)}</span>
            <span className="s mute">{v.key === "anthropic" ? `${n0(v.calls)} calls${demo ? ", estimated" : ""}` : `${n0(v.used)} credits`}</span></>}
      </span>
      <span className="num hide-sm" title={capText}>
        {capUsed == null ? <span className="mute">No cap</span> : `${capUsed > 0 && capUsed < 0.01 ? "<1" : Math.round(capUsed * 100)}%`}
      </span>
    </div>
  );
}
