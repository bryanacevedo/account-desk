import {
  AirplaneTilt, ArrowBendUpRight, CalendarCheck, CalendarPlus, ChatCircleText, CheckCircle, Clock, CurrencyCircleDollar,
  EyeSlash, HandPalm, HourglassLow, Lightbulb, MagnifyingGlass, MinusCircle, PaperPlaneRight, PaperPlaneTilt,
  PauseCircle, PencilSimpleLine, Prohibit, Question, Robot, SignOut, StopCircle, ThumbsUp, UserMinus, UserPlus,
  WarningCircle, XCircle, type Icon,
} from "@phosphor-icons/react";

// Every status word has one icon, everywhere it appears. The icon says what kind of state it is; colour is kept
// for the few that need attention.
export const STATUS_ICONS: Record<string, Icon> = {
  // emails
  "Draft": PencilSimpleLine, "To approve": PencilSimpleLine, "Needs a rewrite": WarningCircle, "Approved": CheckCircle,
  "Rejected": XCircle, "Scheduled": Clock, "Sending": PaperPlaneTilt, "Sent": PaperPlaneRight,
  "Outcome unknown": Question, "Failed": WarningCircle, "Cancelled": MinusCircle,
  // account plays
  "Proposed": Lightbulb, "Accepted": CheckCircle, "Researching": MagnifyingGlass, "Drafts to approve": PencilSimpleLine,
  "In sequence": PaperPlaneTilt, "Replied": ChatCircleText, "Meeting": CalendarCheck, "Opportunity": CurrencyCircleDollar,
  "Ended": StopCircle, "Skipped": ArrowBendUpRight, "Expired": HourglassLow, "Held back": EyeSlash,
  // replies
  "Interested": ThumbsUp, "Wants a meeting": CalendarPlus, "Asked a question": Question, "Not now": Clock,
  "Not interested": HandPalm, "Referred someone": UserPlus, "Left the company": SignOut, "Out of office": AirplaneTilt,
  "Unsubscribed": Prohibit, "Wrong person": UserMinus, "Bounced": WarningCircle, "Automatic reply": Robot,
  "Unclear": Question, "Needs a person": HandPalm,
  // people in a sequence
  "First email to approve": PencilSimpleLine, "Paused": PauseCircle, "Stopped": StopCircle, "Finished": CheckCircle,
  "Meeting booked": CalendarCheck, "Approval came too late": HourglassLow, "Changed jobs": SignOut,
  "Replied, reading it": ChatCircleText, "Colleague replied": ChatCircleText, "Email rejected": XCircle,
  "Blocked by a contact rule": Prohibit, "Play ended": StopCircle,
  // mail and health
  "Sending mail": PaperPlaneTilt, "Live": PaperPlaneTilt, "Held": CalendarCheck, "Booked": CalendarPlus,
  "No show": UserMinus, "Delivered": CheckCircle, "Not delivered": WarningCircle, "Watching": Clock,
  "Past the first batch": CheckCircle,
};
