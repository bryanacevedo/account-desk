# Design checklist

The rules the Account Desk screens are held to, as checks. Nothing goes out for review until every screen it touches passes these, checked in a real browser by a reviewer who has not seen the work, not only by the builder.

No automated gate for copy, layout or interactions exists yet. `npm run typecheck` is the only script that checks the web app; everything below is checked by eye, at 1440 and 375 wide. Where a rule could be measured by a script, that script is not built.

The pages are Today, In flight, Accounts, Approvals, Replies, Signals, Plays, Results, Inboxes, Vendors and costs, Health and Settings. Managers and GTM engineering see the last four; SDRs see the rest.

## Words

- [ ] No sentence explains a screen, a heading, a figure or a row. The screen explains itself.
- [ ] No data written as a sentence ("17 people dropped as low tier, 1 deal since", "$43,802, $14,601 per meeting, plus 136 credits"). Values are laid out as values: a figure with a one-word label, or a field.
- [ ] Words people wrote (an SDR's notes, a buyer's reply) are welcome. Words the app strings together are not.
- [ ] No jargon an SDR or a VP of sales would not use ("held out at random", "waterfall", "flat-priced", "the model"). Plain words. Where a term has to stay, such as "held back" or "autonomy stage", the README glossary defines it.
- [ ] A label never claims more than the data: a deal is pipeline, not "won"; "on target" needs a target.
- [ ] One name for one thing across every screen (held back, not holdout on one page and comparison group on another).
- [ ] Where a fact or a person came from (a signal's source, the CRM, a reply, an import) is always named.
- [ ] A value is shown once per view: never as a heading and again in the line under it.
- [ ] A status is a small icon and a word, never a bare coloured ring or dot. A bare ring read as machine-made (Bryan, 2026-11-11); subtle, elegant icons are wanted, not fewer statuses.
- [ ] Every bar says what it measures, on the bar: a share ("31%"), a share of something named, or used of allowed ("44 of 604"). A bar with no number beside it is decoration. The exception is the step strip on In flight, where the steps themselves are the scale.
- [ ] Rows in one list share one right edge: amounts, actions and the figure above them line up. An action that appears on hover takes the place of the value it acts on.
- [ ] A history or log line that is really counts shows them as figures with a plain label ("Tier mix: 87 tier A, 133 tier B"), never a run-on sentence.
- [ ] A decision card (a proposal on Today, a draft on Approvals) shows only what helps make the decision; raw fields that say nothing about it (import row numbers, vendor record IDs) stay out.
- [ ] Display tidies what people read (company names in capitals become Title Case) without changing what the pipeline reads.
- [ ] Each figure has one home. Its breakdown lives in one place (spend by vendor on Vendors and costs); elsewhere it appears as one figure that links there.
- [ ] Late work reads the same everywhere ("Overdue by 2 days"), against the desk's own clock.
- [ ] No em dashes or en dashes. No red or orange text.

## Look

- [ ] Nothing that reads machine-made: no coloured status dots, no status pills or tags, no quote cards with a coloured left edge, no icon-in-a-circle cards, no KPI tile rows, no gradients. The one coloured mark allowed is a count of work waiting on the reader (the numbers beside Today, Approvals and Replies in the menu).
- [ ] A pill-shaped button is not a status pill. The main action on a screen is a filled pill button in the accent colour; the rule above is about labels and tags that sit in the content.
- [ ] Nothing is underlined to say it can be clicked.
- [ ] Elegant and subtle, never overdesigned: the lightest fix wins (a figure, a field, or removing the thing).
- [ ] Built from the shared parts in `web/src/lib.tsx` and `web/src/sheets.tsx`: figures in a row, bar rows, folds, side sheets. No new kind of element without a reason.
- [ ] Space: nothing cramped, nothing floating in empty white.
- [ ] Alignment: blocks share the page's edges; a row of figures has equal space between figures (not equal columns, which leave uneven gaps when numbers differ in length), each label centred under its figure and every label on one baseline; nothing narrower than its neighbours by accident.
- [ ] Numbers that sit together are the same size; a supporting figure is a step under the verdict it supports.
- [ ] A buyer's own words carry the green opening quote mark. Our own text in the same place does not.
- [ ] One button per purpose: never two buttons that take you to the same place.
- [ ] Button words cannot be misread: Approve and Reject behave alike, and a panel closes with the same × as every other sheet.
- [ ] Buttons look like buttons: the filled accent pill for the main action, never a plain bordered box.

## Structure

- [ ] One layer at a time. Replace, don't add: new information takes a weaker thing's place.
- [ ] Separate jobs live on separate pages. Drafts to approve live on Approvals; replies and what to do about them on Replies; who is in which sequence on In flight; the ranked list of accounts on Accounts.
- [ ] A page or tab with decisions waiting shows how many, as the menu does beside Today, Approvals and Replies.
- [ ] The menu follows the person's job: SDRs do not see Inboxes, Vendors and costs, Health or Settings, and nobody sees a page that would be empty for them.
- [ ] Company money (spend, cost per meeting, pipeline, deals, AI cost) shows only to managers and GTM engineering, on every screen and every read. SDRs never see it.
- [ ] Work belongs to someone: each page says whether it shows your work or the team's (Mine and Team on In flight), and one owner is named, never two.
- [ ] Everything that names a person, an account, a play, an email, a reply, a call, a meeting or a task opens it.

## Side sheets (account, person, email, reply, call or LinkedIn task, meeting, play)

- [ ] Who or what it is: mark or photo, name, context as links. Each kind has its own mark and a hairline in its own quiet tint.
- [ ] Its key figures in one row.
- [ ] The action that matters (approve, reply, record the outcome, mark done).
- [ ] The account it belongs to, and the people there.
- [ ] What it came from and what it led to (the signal behind a play, the reply behind a meeting), each one tap away.
- [ ] The path so far, as one history across email, LinkedIn, calls and signals.
- [ ] A sheet opened from another sheet shows the way back to it.
- [ ] Opening, switching and closing keep the reader's place; Esc, a click outside, back and × all close it.

## Behaviour

- [ ] Motion stays in one language: rows arrive one after another, figures settle, bars draw, running states pulse, rows lift on hover. Everything is off under reduced motion.
- [ ] Nothing jumps, flashes, reloads or loses the reader's place, including switching tabs. Filters stay in the URL.
- [ ] Clicking a row does the same kind of thing everywhere.
- [ ] A link to a person lands on that person: their row open and scrolled into view.
- [ ] Time words fit the state: a finished sequence shows no countdown, and a step that was skipped is not shown as sent.
- [ ] No console errors. Nothing takes over a second to answer.
- [ ] Phone width (375): nothing scrolls sideways, nothing overlaps, every tap target is at least 44px.

## Data a visitor will see

- [ ] Demo data holds up to a close look: dates fit the story, times vary, names are distinct, sample controls do not look like real work.
- [ ] The same figure is the same value on every screen.
