---
name: pto-planner
description: Find low-impact days to take PTO by reading the user's calendar, then book it — block the work calendar, file it in the HR system, post a heads-up to the team channel, and schedule a reminder before the first day. Use this whenever someone asks about taking time off, a day off, vacation, a long weekend, or "what's a good week to be out" — and also when they name a specific date and ask whether they can take it, or ask you to book, block, announce, or request PTO. Don't wait for the phrase "PTO"; "can I disappear on the 22nd" counts.
---

# PTO Planner

Picking a day off is really a question about blast radius: what breaks, or gets awkward, if this person isn't there? The calendar answers that, but only if you read it for *consequence* rather than for busyness. A day packed with recurring internal meetings is a great day to be out. A day with one customer handoff on it is not.

Booking it is a second question, and a procedural one: most companies want the calendar, the team, and the HR system all to agree.

## Org specifics live outside this file

The team channel, the policy page, the HR system, and the approval thresholds are per-company. Read `~/.claude/pto-planner.local.md` if it exists; otherwise ask once and offer to write it there. Never hardcode a channel name, an internal URL, or a colleague's name into this skill — it's shared.

## Workflow

### 1. Establish "now"

Get the current date and time before anything else — a time tool if the harness has one, `date` otherwise. Relative windows ("next month or so", "week after next") need an anchor, and PTO requests are almost always phrased relatively. You also need the user's timezone later, to schedule a message for a sane hour.

### 2. Read the PTO policy before recommending anything

Fetch the policy page. Pull out the four things that change your answer:

- **Notice expected** for trips of this length
- **Thresholds** — the day count above which the HR system, or a manager conversation, is required
- **Required steps and their order** — typically calendar, then team, then HR system
- **In-office expectations** — a standing WFH day is not PTO, and proposing PTO on a day that's already WFH is worth flagging rather than counting as a day off

If there's no policy, say you're working without one and fall back on the defaults here: two weeks' notice, tell the team, mark the calendar.

### 3. Pull the calendar across the whole window

List events with whatever calendar tool is available, and make sure all-day events are in the results — that's where the dated milestones live. Results are capped, so a month-long window will truncate, or overflow the tool-output limit and spill to a file — query in roughly week-long chunks and continue from where the last chunk ended until you've covered the window. If a chunk times out or returns nothing, say what you actually covered rather than presenting a partial picture as complete.

Read every calendar, not just the work one. Family calendars and birthday calendars carry constraints the work calendar doesn't know about.

### 4. Classify what you find

Sort events by how much the user's absence costs. The rough hierarchy:

**High cost — avoid these days**
- External or customer-facing commitments: handoffs, acceptance calls, vendor syncs, anything with outside-domain attendees
- Dated milestones and deadlines, including ones recorded as all-day informational events (a delivery date, a funding decision, a cabling-complete target)
- Events the user personally organizes or presents at
- One-off company events — launches, offsites, all-hands

**Low cost — good days**
- Recurring internal meetings: standup, weekly sync, sprint ceremonies, team lunch, social hours
- Commute blocks, focus blocks, "Office"/"Home" location markers — these are scaffolding, not obligations
- Days with nothing at all

**Read the event body, not just the title.** A calendar entry titled with a cluster name may be a milestone with a hard date buried in the description. That's the difference between a day that's fine to miss and one that isn't.

### 5. Don't assume whose event it is

Personal commitments on a work calendar look identical to work obligations. A conference, a class, a networking session — any of these might be the user's own thing, which they can skip or attend freely while on PTO. Don't silently treat them as blockers, and don't silently dismiss them either. If a judgment hinges on one, name it and let the user correct you. When they do correct you, re-run the assessment for that day rather than just conceding the point.

### 6. Give a recommendation, not a data dump

Lead with the best window and why. Then:
- Name one or two alternates with their tradeoffs
- List the days to avoid, each with the specific reason
- If it's a close call, end with a concrete pick ("if I had to choose two days: X and Y")
- Say which extra steps the length triggers — HR filing, manager approval — before they commit, not after

Keep it scannable. The user wants a decision, not a calendar transcript.

### 7. Book it — only when asked, and in this order

Nothing gets created, sent, or scheduled until the user says go. Then work in order, because each step assumes the one before it landed.

**a. Block the work calendar.** An all-day event on the *work* calendar, marked free rather than busy — PTO shouldn't read as a meeting block, and the field for that is spelled differently in every calendar API (`transparent`, `free`, `availability`), so check before assuming. Title it plainly — "PTO", or "PTO — <reason>" only if the reason is something they'd say out loud to the whole company.

**b. File it in the HR system, if the length requires it.** Try the connector. If it's not authenticated, it will offer you an auth handshake and nothing else — say that plainly, tell them where the request lives in that product, and don't imply anything was submitted. Being logged in on their end doesn't give you their session.

**c. Post the heads-up to the team channel.** Draft it, show it, send only on an explicit yes. Timing matters as much as content: announce about two weeks out, and no earlier. A notice sent a month ahead is forgotten by the time it's relevant. So:
- PTO is under ~2 weeks away → send now
- PTO is further out → schedule the announcement for roughly two weeks before the first day

**d. Schedule the reminder.** One more message to the same channel, 1–2 days before the first day, in the morning in the user's timezone. This is the one people actually act on. Use the scheduled-message tool rather than promising to remember.

**e. Hand off what you can't do.** Say it explicitly: the calendar block won't decline existing invites and won't notify anyone, Slack status is theirs to set, and if the length crosses the approval threshold, the manager conversation still has to happen. Until that approval exists, the time off is provisional — don't write about it as confirmed.

### 8. Keep private things out of everything you send

The heads-up carries dates, coverage, and a return date. Not the reason.

Anything medical, financial, family, legal, or interview-shaped that you saw while reading the calendar stays out of the outbound message, out of the scheduled reminder, and out of the calendar title — "PTO" is always enough. The same goes for other people's events you passed on the way through. If you're unsure whether a detail is shareable, leave it out and let the user add it.

## Writing the two messages

Both versions, drafted together:

- **Team channel:** dates, what they'll miss, when they're back, who to go to meanwhile
- **Manager:** the same dates, plus why nothing critical lands that day, plus an offer to hand off coverage

Ground both in real specifics from the calendar — which meetings they'll miss, what milestone cleared beforehand, what's waiting when they return. Generic PTO boilerplate is worse than useless; the whole value is that you actually read the calendar. Leave the recipient's name as a blank for them to fill.

## Worth remembering

- A four-day weekend from two days of PTO is usually the highest-value answer. Look for Mondays and Fridays adjacent to quiet weeks.
- Crossing a length threshold (often 3 days, then 5) changes the required steps. Check the length against the policy before drafting anything.
- Check what lands the day *after* the proposed PTO. Returning to a launch party or a handoff means prep may need to happen before they leave.
- Handoff and delivery dates slip constantly. Treat any milestone within a few days of the proposed PTO as a soft risk worth flagging, not a hard blocker.
