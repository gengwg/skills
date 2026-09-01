---
name: grafana-alert-silences
description: Use when silencing Grafana alerts for a maintenance window, when a silence doesn't match the alerts it should, when deciding between a silence and a mute timing, or when silencing one node/instance must not blind cluster-wide alerts
---

# Grafana Alert Silences

## Overview

Silences suppress notifications for alerts matching a set of label matchers, for a bounded time. Two things go wrong in practice: the silence doesn't match (missing the rule-UID matcher), or it matches too much (blinding aggregate alerts during a window when you most need them).

## Silence vs mute timing

- **Silence**: one-off, time-boxed (a maintenance window, a vendor intervention, a known-bad node awaiting hardware). Expires on its own.
- **Mute timing**: recurring schedule attached to a notification policy (every Sunday 02:00–04:00). Not for one-off windows.

Picking a mute timing for a one-off means someone must remember to remove it. Use silences for anything with an end date.

## Creating a silence that actually matches

Grafana-managed alerts carry the rule UID as a label. To silence one specific rule, match on it:

```
__alert_rule_uid__ = <rule UID>
```

Matching only on `alertname` can fail for Grafana-managed rules (folders can contain same-named rules; notification-time labels may differ from what you expect). The UID matcher is exact. Get the UID from the rule's URL or `/api/v1/provisioning/alert-rules`. (`__alert_rule_uid__` exists only on Grafana-managed rules — for data-source-managed Mimir/Loki rules, match on the rule's own labels.)

When a silence isn't matching, look at the firing alert's actual notification-time labels rather than guessing:

```sh
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/alerts" | jq '.[].labels'
```

## Scope tightly — keep aggregates armed

Silencing for one node's maintenance:

```
__alert_rule_uid__ = <per-node rule UID>
node               = <the node>
```

(The label holding the node name varies per deployment — `node`, `instance`, `hostname` — check the firing alert's labels, above.)

Do NOT silence on broad labels (`cluster=X`, or alertname alone) — that also suppresses the cluster-aggregate rules ("N nodes down") which are exactly the ones that must stay armed while you work. One silence per (rule, node) pair beats one broad silence.

## Hygiene per silence

- **Explicit UTC start and end** — never open-ended. Size the window to the work plus margin; extend later if needed.
- **Comment with a ticket/issue reference** and what the window is for — the comment is the only context the next on-call sees.
- **Record the silence UID** (returned on create) in the ticket so it can be extended or lifted early:

```sh
# Create (Alertmanager API, works for Grafana-managed alerts)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/silences" -d '{
    "matchers": [
      {"name": "__alert_rule_uid__", "value": "<uid>", "isRegex": false, "isEqual": true},
      {"name": "node", "value": "<node>", "isRegex": false, "isEqual": true}
    ],
    "startsAt": "2026-01-01T02:00:00Z",
    "endsAt":   "2026-01-01T06:00:00Z",
    "comment":  "ticket ABC-123: NIC swap on <node>",
    "createdBy": "<your-name>"
  }'
# → {"silenceID": "..."}   record this

# Lift early (DELETE expires the silence — it stays visible as "expired")
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/silence/$SILENCE_ID"

# Lost the UID? List active silences:
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/silences" | jq '.[] | select(.status.state=="active") | {id, comment}'

# VERIFY (do this after every create or edit — both halves):
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/silences" \
  | jq '.[] | select(.id=="<id>") | {state: .status.state, startsAt, endsAt}'   # want state=active
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/alerts?active=true&silenced=true" \
  | jq '.[] | select(<your target>) | {state: .status.state, by: .status.silencedBy}'  # want suppressed
# And confirm the blast radius — everything that must stay armed still is:
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/alertmanager/grafana/api/v2/alerts?active=true&silenced=false" \
  | jq '[.[] | select(.labels.__alert_rule_uid__=="<uid>") | .labels.node]'
```

**`startsAt` in the future creates a silence that suppresses nothing.** It sits in `state: pending` and the alert stays `active` — with no error to tell you. Unless you deliberately want a scheduled window, set `startsAt` to now or earlier. A window you believed was covering you but was still pending is exactly when the pages you were preventing arrive.

**Editing may or may not reuse the silence ID — never assume.** Changing only `endsAt` on an *active* silence has been seen to keep the same ID; changing `startsAt`, or editing a silence that is still *pending*, expires the old one and mints a new ID. The expiry is silent, so the old ID looks like a failed edit when the edit in fact succeeded under a new ID.

Two consequences:

- **Never "repair" a silence you think failed by creating another one.** List the silences first — you may already have minted one, and you will end up with two overlapping silences on the same target, which is confusing to the next responder and easy to half-lift later.
- **Re-read the list after every create *and* edit**, and confirm both halves: the silence is `state: active`, **and** the target alert is `status.state: suppressed` carrying that silence's ID in `silencedBy`. A silence that exists is not a silence that matches.

## Maintenance batches: verify the work started first

Silencing a batch of nodes for a rolling maintenance (firmware, reboots): before creating the silence, confirm on-cluster that those exact nodes are actually staged — cordoned, tainted, or drained. Silencing on someone's "starting batch N now" message alone can blind the wrong node set, or the right set hours before anything happens.

- One silence per batch with a regex matcher over the node names beats N single-node silences — one ID to extend or expire.
- End the window at a fixed boundary (e.g. midnight local) with margin over the expected duration. If the work runs long, extend *before* it lapses, and re-read the list afterwards in case the edit minted a new ID.
- When the next batch starts, verify the previous batch's nodes came back (Ready, expected GPU/device count, taint removed) — the expiring silence was hiding exactly those alerts.

## After the window

Verify the silence expired or delete it, then check the silenced alerts' current state — a silence hides state changes; the alert may have been firing the whole time for an unrelated reason.

## Common mistakes

- Matching on `alertname` only and wondering why the alert still pages — add `__alert_rule_uid__`.
- A `startsAt` a few minutes in the future — the silence is `pending`, suppresses nothing, and reports no error.
- Assuming the returned `silenceID` is still the live one after an edit — re-read the list.
- Creating a replacement for a silence you believed the edit killed — check for the minted one first, or you get overlapping duplicates.
- Declaring done because the silence exists — verify the target alert actually reads `suppressed`, and that the alerts which must stay armed still do.
- One broad cluster-wide silence for a one-node job — aggregate alerts go blind.
- Open-ended or local-time windows — always explicit UTC start/end.
- No comment/ticket — the next on-call can't tell if it's safe to lift.
- Losing the silence UID — now lifting early means hunting through the UI.
