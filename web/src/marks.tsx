import { useState } from "react";
import { initials } from "./lib";

// ---------------------------------------------------------------- invented company marks
// Every company in the demo is invented, so each gets an invented mark: a geometric glyph on a brand colour,
// chosen from its domain so the same company always wears the same logo.

const COLORS = ["#1D3A8A", "#0F766E", "#9A3412", "#1F2937", "#047857", "#9D174D", "#0E7490", "#B45309", "#3F3F9C",
  "#BE123C", "#166534", "#334155", "#C2410C", "#155E75", "#6D28D9", "#A16207"];

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

const GLYPHS: ((c: string) => JSX.Element)[] = [
  (c) => <><circle cx="13" cy="16" r="6.5" fill={c} /><circle cx="19" cy="16" r="6.5" fill={c} opacity=".55" /></>,
  (c) => <><rect x="9" y="9" width="14" height="3.4" rx="1.7" fill={c} /><rect x="9" y="14.3" width="10" height="3.4" rx="1.7" fill={c} /><rect x="9" y="19.6" width="14" height="3.4" rx="1.7" fill={c} /></>,
  (c) => <><path d="M9 23V13a4 4 0 0 1 4-4h10v10a4 4 0 0 1-4 4z" fill={c} /><circle cx="13.5" cy="18.5" r="2.6" fill="var(--logo-bg)" /></>,
  (c) => <path d="M16 8.5 24 23H8z" fill={c} />,
  (c) => <><circle cx="16" cy="16" r="7.5" fill="none" stroke={c} strokeWidth="3.2" /><rect x="15" y="7" width="9" height="4" fill="var(--logo-bg)" /></>,
  (c) => <><rect x="9" y="9" width="6" height="6" rx="1.6" fill={c} /><rect x="17" y="9" width="6" height="6" rx="3" fill={c} /><rect x="9" y="17" width="6" height="6" rx="3" fill={c} /><rect x="17" y="17" width="6" height="6" rx="1.6" fill={c} opacity=".55" /></>,
  (c) => <path d="M9 12.5 16 19l7-6.5" fill="none" stroke={c} strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />,
  (c) => <><path d="M8 20a8 8 0 0 1 16 0z" fill={c} /><rect x="8" y="22" width="16" height="2.6" rx="1.3" fill={c} opacity=".55" /></>,
  (c) => <><rect x="14.2" y="8" width="3.6" height="16" rx="1.8" fill={c} /><rect x="8" y="14.2" width="16" height="3.6" rx="1.8" fill={c} /></>,
  (c) => <path d="M8 18c2.7-4.5 5.3-4.5 8 0s5.3 4.5 8 0" fill="none" stroke={c} strokeWidth="3.2" strokeLinecap="round" />,
  (c) => <><path d="M9 23V9" stroke={c} strokeWidth="3.4" strokeLinecap="round" /><path d="M9 9h6.5a4.5 4.5 0 0 1 0 9H9" fill="none" stroke={c} strokeWidth="3.4" strokeLinejoin="round" /></>,
  (c) => <><path d="M8 24a16 16 0 0 1 16-16" fill="none" stroke={c} strokeWidth="3" strokeLinecap="round" /><path d="M13 24a11 11 0 0 1 11-11" fill="none" stroke={c} strokeWidth="3" strokeLinecap="round" opacity=".55" /><circle cx="22.5" cy="22.5" r="2" fill={c} /></>,
  (c) => <path d="m16 8 8 8-8 8-8-8z" fill={c} />,
  (c) => <><rect x="8.5" y="8.5" width="15" height="15" rx="4" fill="none" stroke={c} strokeWidth="3" /><circle cx="16" cy="16" r="2.6" fill={c} /></>,
];

export function Logo({ domain, name, size = 28 }: { domain: string; name: string; size?: number }) {
  const h = hash(domain || name);
  const color = COLORS[h % COLORS.length];
  const glyph = GLYPHS[(h >>> 4) % GLYPHS.length];
  const light = ((h >>> 9) % 5) === 0; // one in five marks is coloured on white, as real brands vary
  const bg = light ? "#FFFFFF" : color;
  const fg = light ? color : "#FFFFFF";
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={`${name} logo`}
      style={{ ["--logo-bg" as any]: bg, borderRadius: size * 0.26, flex: "none", boxShadow: light ? "inset 0 0 0 1px var(--line-2)" : undefined }}>
      <rect width="32" height="32" fill={bg} />
      {glyph(fg)}
    </svg>
  );
}

// ---------------------------------------------------------------- a person's face, or their initials

export function Avatar({ name, photo, size = 28 }: { name: string; photo?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size, borderRadius: "50%", flex: "none" } as const;
  if (photo && !failed) {
    return <img className="avatar" src={photo} alt="" width={size} height={size} loading="lazy" decoding="async"
      referrerPolicy="no-referrer" onError={() => setFailed(true)} style={{ ...style, objectFit: "cover", background: "var(--well-2)" }} />;
  }
  return <span className="avatar mono" aria-hidden="true" style={{ ...style, display: "grid", placeItems: "center", background: "var(--well-2)", color: "var(--ink-2)", fontSize: size * 0.38, fontWeight: 620, fontFamily: "var(--sans)", letterSpacing: "-0.01em" }}>{initials(name)}</span>;
}
