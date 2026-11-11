import {
  ArrowCounterClockwise, ArrowsLeftRight, Briefcase, Browser, CalendarCheck, Coins, Lightning, MagnifyingGlass, Plug,
  PlugsConnected, Receipt, RocketLaunch, Star, Tag, ThumbsUp, TrendDown, UserCirclePlus, UserSwitch,
  type Icon,
} from "@phosphor-icons/react";

// One icon per kind of signal, so a feed or a timeline reads at a glance. Ink, never colour: the icon names the
// kind; it does not rate it.
const ICONS: Record<string, Icon> = {
  champion_moved: UserSwitch, new_exec: UserCirclePlus, hiring_function: Briefcase, funding: Coins,
  pricing_visit: Tag, site_visit: Browser, intent_topic: MagnifyingGlass, competitor_review: Star,
  tech_added: PlugsConnected, tech_removed: Plug, pricing_change: Receipt, social_engaged: ThumbsUp,
  job_change: ArrowsLeftRight, closed_lost_revisit: ArrowCounterClockwise, product_signup: RocketLaunch,
  event_attended: CalendarCheck, news_negative: TrendDown,
};

export function SignalIcon({ type, size = 16 }: { type: string; size?: number }) {
  const C = ICONS[type] || Lightning;
  return <span className="sig-icon" aria-hidden="true"><C size={size} weight="regular" /></span>;
}

export function SignalLabel({ type, label }: { type: string; label: string }) {
  return <span className="sig-label"><SignalIcon type={type} />{label}</span>;
}
