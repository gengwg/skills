---
name: grafana-alert-noise-reduction
description: Use when an alert is "too spammy", fires once per target/node when one page would do, or a warning and its critical sibling both page for the same episode — reducing Grafana alert noise without blinding the rule
---

# Grafana Alert Noise Reduction

## Overview

"Too noisy" has several distinct mechanisms, each with a different correct fix. Applying the wrong one (or reaching for `unless` filters) either leaves the noise or silently disables the rule. Diagnose the mechanism first.

## Step 0: noisy ≠ false

Verify the alert is a true positive before tuning. A rule paging about a real, unfixed fault is doing its job — the fix is the fault, and weakening its *detection* (threshold, severity, deletion) belongs to whoever owns the fault. Repackaging its *notifications* (grouping, sibling dedup) is fair game either way. Count the actual pages (notification groups per day) and identify which dimension multiplies them before touching anything.

When several mechanisms apply, do the cheapest reversible one first (grouping is a one-line change), re-measure, and only then add query guards.

## Mechanism → fix

### N pages per episode, one per target/node → collapse grouping

If `notification_settings.group_by` includes a fine-grained label (`probe_target`, `node`), one episode fans out into one page per value. Drop the fine label so one group forms per episode:

- Grafana always appends `alertname` and `grafana_folder` to your `group_by` — you can't lose those.
- **Cost to record:** a new value failing *later* joins the already-open group silently and won't page until `repeat_interval`. With a long `keep_firing_for`, the group stays open that much longer.

### Warning + critical sibling both page → guard inside the query

Classic Alertmanager inhibition is not reachable for Grafana-managed rules on simplified routing — `notification_settings` bypasses the notification-policy tree entirely (and the policy tree itself is often provenance-locked). Instead, build the suppression into the warning's query: add a term so its value cannot cross the threshold while the critical condition holds for the same scope.

### Suppression guards: additive, never `unless`

Filtering series out with `unless` (or a filter that drops them) makes the series disappear → the alert resolves via MissingSeries → **`keep_firing_for` becomes inert** and you get flap-noise back. Add guard terms that *move the value away from the threshold* instead. For a fires-when-low rule (success ratio < 0.8):

```
<original ratio expr>
  + on(cluster) group_left()
    (<critical condition, boolean per cluster> * 10  or  <always-present zero series>)
```

Two traps in the arithmetic:

- The guard must be **present with value 0** when inactive. `+ on(...)` against an *absent* right side drops the left series — the same MissingSeries failure by another route. `or` it with a zero-valued vector carrying the same grouping labels.
- Match scope explicitly (`on(cluster)` etc.); sloppy vector matching suppresses the wrong scope or nothing.

Properties to verify and state: series count constant (see below), and suppression is a strict subset — the guard only pushes values *away* from firing, so nothing can fire now that wouldn't have before. **Cost to record:** an independent same-scope fault is invisible for the duration of any guard-active episode.

### Shared-cause noise on probe-style rules → quorum guard

Same target failing from ≥3 vantage points means the *target* is down, not your side — guard the per-vantage rule on that quorum. The same logic runs in the other direction: one source failing to reach many targets is the source's fault, which is what a "multi-target down" critical aggregate encodes — dedup against it with the critical-sibling guard above. Scopes with fewer than 3 members can't form a quorum; leave them unguarded so single-path faults still page. **Cost to record:** correlated-but-independent failures at quorum scale are attributed to the shared cause.

### Flapping → duration, not deletion

`for` delays firing; `keep_firing_for` (snake_case in the provisioning API — camelCase is accepted and silently ignored) holds a firing alert through short recoveries. Tune these before considering deleting a rule. **Cost to record:** detection delayed by `for`; resolution delayed by `keep_firing_for` (the alert shows firing through brief real recoveries).

### What severity is NOT for

Demoting critical→warning to quiet a channel confuses blast radius with annoyance. Severity encodes "must a human act now"; noise is a grouping/guard problem. Fix the noise at its mechanism and leave severity meaning something.

## Verify after any change

- **GET the rule back and diff** — this API's failure mode is silent acceptance (200 with fields ignored or reset). Check `keep_firing_for`, `for`, labels, and the rule group's evaluation interval survived.
- **Series count**: `count(<the rule's query expr>)` flat across ~7 days before vs after — the invariant is the *query's* series, not `ALERTS{}` churn (state changes there are expected).
- **Backtest**: re-run the changed query over past episodes. Episodes that should have paged must still cross the threshold; the noise events must not.
- **Counter-reset check**: before arguing a fault is "getting worse" from restart/error counters, check the counters didn't reset (pod/manifest replaced) inside your window — a reset makes the pre-fix storm look current.
- **Record the decision in the rule description**: what fired, what you changed, and the cost you accepted (e.g. "later target joins open group silently until repeat_interval"). The next person tuning this rule needs the history inline, not in a chat log.

## Common mistakes

- Tuning a true positive instead of escalating the fault.
- `unless`-style filters that trade page-noise for MissingSeries flapping.
- Collapsing `group_by` without recording the late-joiner cost.
- Trusting the PUT's 200 — always GET back and diff.
- Trying to inhibit via the policy tree on simplified routing — `notification_settings` never consults it.
