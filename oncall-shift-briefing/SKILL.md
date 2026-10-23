---
name: oncall-shift-briefing
description: Use when starting an on-call shift or taking over from the previous on-call ("start oncall", "get me up to speed", "what changed since the handoff") or asked to watch and acknowledge new pages during the shift, especially with Grafana IRM / OnCall, where the schedule API can report nobody on call while the rotation is live
---

# On-call Shift Briefing

## Overview

One read-only briefing at the start of a shift: what the previous on-call handed over, what changed since, and what to look at first. Team specifics (where the handoff lives, alert title format, incident label, chat channels) come from the project's AGENTS.md / CLAUDE.md or `docs/oncall.md`. If none says, ask.

## Steps

Run the independent reads in parallel.

1. **Handoff.** The most recent handoff note or doc. Its timestamp splits "carried over" from "new".
2. **Your shift.** Confirm you are on call and until when. Read the trap below first.
3. **Alerts.** Firing and acknowledged groups from the last 24h, grouped by cluster or service. Tag each "in handoff" or "new since handoff".
4. **Open incidents** in the team's tracker.
5. **Waiting on you.** Unanswered mentions and customer threads awaiting a reply since the handoff.

## The empty-schedule trap (Grafana IRM / OnCall)

`list_oncall_schedules` returning `"shifts": []` and `get_current_oncall_users` returning no users do **not** mean nobody is on call. Rotations built in the UI are not exposed as schedule shifts, so both come back empty while paging works normally.

- Resolve your own shift instead: ask Grafana Assistant "list my own current and upcoming on-call shifts". It can't read a schedule by ID or show other people's shifts.
- The full rotation, overrides included: `GET /api/v1/schedules/<id>/final_shifts?start_date=&end_date=` on the OnCall API host, with a service-account token and the `X-Grafana-Instance-ID` header. The Grafana plugin-proxy path (`/api/plugins/grafana-irm-app/resources/...`) returns 405.
- When your own shift resolves, report it and say nothing about a paging gap. Claim a gap only if `final_shifts` or the IRM UI shows one.

## Report

```
My shift: <start> -> <end> (or: not on call, next <start>)
Handoff: <source>, <time>

New since handoff
  <cluster> <alert> <state> <since>
Still open from handoff
  <item> <current state; say so if it no longer matches the note>
Open incidents
  <id> <title> <age>
Waiting on you
  <mention or thread> <where> <status>

Look at first: <1-3 items, why>
```

Deep dives only when asked. Stay read-only (no ack, silence, or comment) unless told.

## Watch mode

When asked to watch alerts during the shift, repeat this every 15 minutes (Claude Code: `/loop 15m`). The paging channel comes from the team specifics above.

1. List alert groups in state `new` (Grafana IRM: `list_alert_groups`, `state: new`).
2. Keep those routed to the paging channel. Info-only channels are not paged; leave them.
3. Acknowledge each one and confirm the returned state.
4. Report every ack: alert number, title, cluster or service, fire time. An ack stops escalation to the next person on the schedule, so nothing acked may go unreported. Say "no new alerts" when there are none.

## Common mistakes

| Mistake | Fix |
|---|---|
| "Nobody is on call, pages may not reach you" from empty schedule results | Resolve your own shift first; an empty result is not a gap |
| Repeating the handoff note's wording | Compare it with current alert state: a "flap" firing continuously for hours is an outage |
| Re-querying narrower windows after an alert-group result hits the MCP token cap | Parse the dumped result file instead |
| Reporting Slack as unavailable because no `slack_*` tools appear | The Slack server may sit under a plugin that needs a one-time OAuth; search for its tools and run its `authenticate` before giving up |
