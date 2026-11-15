/** Helpers for the approval sheet's margin (bl_122): what changed against the draft the desk wrote, one change at a
 *  time, how the server's check problems read as a ledger, and the send slot in the recipient's own time. */

export interface Hunk { was: string; now: string; oStart: number; oEnd: number; nStart: number; nEnd: number }

const tokens = (s: string) => s.split(/(\s+)/).filter((t) => t !== "");

/** Word-level changes from `original` to `current`: each run of tokens that differs is one change. */
export function changes(original: string, current: string): { hunks: Hunk[]; o: string[]; n: string[] } {
  const o = tokens(original), n = tokens(current);
  const L: number[][] = Array.from({ length: o.length + 1 }, () => new Array(n.length + 1).fill(0));
  for (let i = o.length - 1; i >= 0; i--) for (let j = n.length - 1; j >= 0; j--) {
    L[i][j] = o[i] === n[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  }
  const hunks: Hunk[] = [];
  let i = 0, j = 0;
  let open: Hunk | null = null;
  const close = () => {
    if (open) {
      open.was = o.slice(open.oStart, open.oEnd).join("").trim();
      open.now = n.slice(open.nStart, open.nEnd).join("").trim();
      hunks.push(open);
      open = null;
    }
  };
  while (i < o.length || j < n.length) {
    if (i < o.length && j < n.length && o[i] === n[j]) {
      // Whitespace between two changes does not split them.
      if (open && /^\s+$/.test(o[i]) && (i + 1 < o.length && j + 1 < n.length && o[i + 1] !== n[j + 1])) {
        open.oEnd = ++i; open.nEnd = ++j; continue;
      }
      close(); i++; j++; continue;
    }
    if (!open) open = { was: "", now: "", oStart: i, oEnd: i, nStart: j, nEnd: j };
    if (j < n.length && (i >= o.length || L[i][j + 1] >= L[i + 1][j])) { j++; open.nEnd = j; } else { i++; open.oEnd = i; }
  }
  close();
  return { hunks: hunks.filter((h) => h.was || h.now), o, n };
}

/** The text with one change put back as the desk wrote it. */
export function restoreOne(original: string, current: string, k: number): string {
  const { hunks, o, n } = changes(original, current);
  const h = hunks[k];
  if (!h) return current;
  return [...n.slice(0, h.nStart), ...o.slice(h.oStart, h.oEnd), ...n.slice(h.nEnd)].join("");
}

/** The ledger of readings. A row's value is what the server's dry run found, or its quiet "fine" word. */
const ROWS: [string, RegExp, string][] = [
  ["Opt-out line", /opt-out/i, "Kept"],
  ["Long dash", /long dash/i, "None"],
  ["Merge fields", /merge field/i, "None"],
  ["Banned phrases", /^Uses /, "None"],
  ["Spam words", /^Spam-filter/, "None"],
  ["Links", /links/i, "None"],
  ["Numbers", /^The number /, "All cited"],
];

export function ledger(problems: string[]): { rows: { label: string; value: string; bad: boolean }[]; other: string[] } {
  const used = new Set<number>();
  const rows = ROWS.map(([label, re, fine]) => {
    const hit = problems.map((p, i) => [p, i] as const).filter(([p]) => re.test(p));
    hit.forEach(([, i]) => used.add(i));
    const value = !hit.length ? fine : label === "Banned phrases" || label === "Spam words" || label === "Numbers"
      ? hit.map(([p]) => p.replace(/^Uses |^Spam-filter word |^The number | is not in any fact we hold about them/g, "")).join(", ")
      : label === "Opt-out line" ? "Missing" : label === "Links" ? "Found" : "Found";
    return { label, value, bad: hit.length > 0 };
  });
  return { rows, other: problems.filter((_, i) => !used.has(i) && !/words; this step needs/.test(problems[i])) };
}

/** "Sends today 10:12 AM, Sofia's time", worked out in the recipient's zone against the desk's own clock. */
export function slotLabel(m: any, now: number): string | null {
  if (!m?.next_slot) return null;
  const tz = m.slot_label?.recipient_tz || "UTC";
  const first = m.slot_label?.recipient_first_name;
  const at = new Date(m.next_slot);
  const key = (d: Date) => { try { return d.toLocaleDateString("en-CA", { timeZone: tz }); } catch { return d.toISOString().slice(0, 10); } };
  const hm = (() => { try { return at.toLocaleTimeString("en-US", { timeZone: tz, hour: "numeric", minute: "2-digit" }); } catch { return at.toISOString().slice(11, 16) + " UTC"; } })();
  if (at.getTime() <= now + 60000) return `Sends on approval${first ? `, ${first}'s time` : ""}`;
  const when = key(at) === key(new Date(now)) ? "today" : key(at) === key(new Date(now + 86400000)) ? "tomorrow"
    : at.toLocaleDateString("en-US", { timeZone: tz, weekday: "short", day: "numeric", month: "short" });
  return `Sends ${when} ${hm}${first ? `, ${first}'s time` : ""}`;
}
