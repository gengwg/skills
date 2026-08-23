---
name: grafana-oncall-shift-override
description: Use when taking over someone's on-call shift, swapping shifts, or fixing a corrupted rotation in Grafana OnCall / IRM via API — overrides, rotation edits, and the schedule UI all have non-obvious traps
---

# Grafana OnCall Shift Overrides and Rotation Edits

## Overview

"Cover the rest of X's shift" is one API call — an override — but verifying it, and especially editing the underlying rotation, is where sessions go wrong. The rotation PUT re-anchors itself, the server overrides your start index, and the UI rendering makes correct schedules look broken.

## API surface

Grafana Cloud proxies the OnCall/IRM API under the regular Grafana API with a normal service-account token — no separate OnCall token needed:

```
GET  /api/plugins/grafana-irm-app/resources/schedules/          # list — resolve name → SCHEDULE_ID
GET  /api/plugins/grafana-irm-app/resources/schedules/<SCHEDULE_ID>
GET  /api/plugins/grafana-irm-app/resources/schedules/<SCHEDULE_ID>/events?date=YYYY-MM-DD&days=N
POST /api/plugins/grafana-irm-app/resources/oncall_shifts/
GET|PUT|DELETE /api/plugins/grafana-irm-app/resources/oncall_shifts/<SHIFT_PK>
```

Writes need an Admin-role token; timestamps are ISO-8601 UTC (`2026-08-05T15:41:00Z`); the events `date` param is a day in the schedule's own `time_zone`. Users in shift bodies are **OnCall user pks** (`U…`), not Grafana user ids — list them via the OnCall users endpoint or the Grafana MCP `list_oncall_users`.

The schedule object carries `on_call_now` and `time_zone`. The events endpoint renders what the schedule actually resolves to — trust it over the stored config.

## Taking over a shift: create an override

An override is a shift of `type: 3` at `priority_level: 99`. It shadows whatever is underneath (rotation or another override) for its window without modifying it:

```json
POST oncall_shifts/
{
  "name": "Override", "type": 3, "priority_level": 99,
  "schedule": "<SCHEDULE_ID>",
  "shift_start": "<now, UTC>",
  "shift_end": "<end of their shift, UTC>",
  "rotation_start": "<same as shift_start>",
  "rolling_users": [["<oncall user pk>"]]
}
```

This field set is sufficient — no `frequency`/`duration` needed for type 3.

- End the override exactly at the shift's handoff time — pull it from the events endpoint (`is_override`, event `end`), don't compute it yourself.
- Check what you're covering first: if the person is on the **base rotation**, priority-99 shadows it cleanly and the rotation is untouched. If they're on an **override** (same priority 99), two overlapping overrides don't resolve deterministically — DELETE theirs for the window, then create yours.

## Verify — and expect the cache lag

1. Events endpoint: your override appears with `is_override: true`, covering the window with no gap.
2. `on_call_now` on the schedule lags by a minute or two — it's cached. Poll until it flips; don't re-write because it "didn't take".

## Rotation (type 2) edits — here be dragons

Editing the rotation itself (user list, order) via PUT:

- **PUT re-anchors a past `rotation_start` to "now"** and returns a **new shift pk**. This is versioning: history under the old pk stays intact and past days still render correctly, but your stored reference is stale.
- A **future** `rotation_start` is honored. So anchor the edit at the *next handoff boundary* and reorder the user list cyclically so the future cycle renders as intended, instead of fighting the re-anchor.
- The server **overrides `start_rotation_from_user_index`** to preserve whoever is currently on call — you cannot rotate the current slot out via index; reorder the list instead.
- After any rotation PUT, **verify by rendering**: walk `events?date=...&days=...` day-by-day through at least one full cycle and compare against the intended roster. The stored config can look wrong while rendering right (and vice versa).
- Check history too: past days should still show who actually was on call. Days that re-rendered *before* your fix cannot be repaired — paging already happened; it's cosmetic.

## UI rendering trap

Day columns are drawn at midnight, but shifts run handoff-to-handoff (e.g. 08:00 → 08:00). Every bar therefore spills past its day's gridline. A bar reaching into the next day's column is not a moved or extended shift — pull the raw event boundaries before concluding anything moved.

## Diagnosing "the schedule shifted"

If future days show the wrong people, diff the rotation's user list against the intended roster — a duplicated or extra slot in `rolling_users` shifts every subsequent day. Establish when it changed (insight/audit logs) before assuming your own write did it.

## Common mistakes

- Editing the rotation to cover one day — that's what overrides are for; the rotation should change only when the roster changes.
- Trusting `on_call_now` immediately after a write — it's cached; use the events endpoint for truth.
- Re-anchoring a rotation at "now" mid-shift and corrupting the cycle — anchor at the next handoff.
- Keeping the old shift pk after a PUT — the PUT returned a new one; the old is a historical version.
- Reading the UI bars as evidence — day gridlines don't align with handoff times.
