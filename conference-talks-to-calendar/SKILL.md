---
name: conference-talks-to-calendar
description: Use when someone shares a conference, meetup or summit page or agenda and asks whether to go, which talks suit them, or to put the event or its talks on their calendar. Also when they ask what time to leave for an event, or to block conference days.
---

# Conference Talks to Calendar

## Overview

Three jobs, in order: decide whether the event is worth it, pick talks, and write them to the calendar so the person never has to clean up after you. The cleanup is what goes wrong. Each rule below is a correction people have had to make by hand.

## 1. Go or skip

Judge the agenda against what the person works on and cares about, not the event's marketing. Name the two or three sessions that justify going, the cost (ticket, travel, a lost workday), and what it collides with on their calendar. Give a yes or no, then the reasons.

## 2. Pick talks

- Read the **speakers and keynotes**, not just the track sessions. A headline speaker is often the best slot of the day.
- Read the whole multi-day agenda, then say which days are worth it.
- Two talks in one slot: pick one and name the runner-up in the event description.

## 3. Write to the calendar

Every event you create is **private** (`visibility: private`). Nobody needs to ask.

| Event | Shape |
|---|---|
| Conference day | One block, busy, venue address as location |
| Each talk | Own event, title `<Conf>: <talk>`, room as location. **Free** when inside the day block, busy when not |
| Multi-day conference | Offer an out-of-office block too. Say that it auto-declines new invites |

Existing events on those days:

- **Remove commute and similar routine blocks for conference days without asking.** Delete only that day's instance, never the series, with no notifications. Say which ones you removed.
- **Never decline, accept or reschedule an existing invite** unless the person asks. List the conflicts and leave the RSVPs alone.
- Account for travel: the time to leave for the venue, and the time to leave a talk to reach the next fixed commitment.

## Common mistakes

- Creating events with default visibility, then marking them private only when asked.
- Asking "should I remove the commute blocks?" instead of removing that day's copies.
- Deleting a whole recurring series to clear one day.
- Declining or offering to decline a conflicting meeting.
- Picking talks from the track list and missing the keynote speakers.
- Marking talks busy inside an all-day busy block, double-booking the person.
