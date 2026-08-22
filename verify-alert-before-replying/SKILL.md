---
name: verify-alert-before-replying
description: Use when someone pastes an alert, a monitoring digest, or a claim like "X is down / is this real?" and expects an answer — before replying, agreeing, or acting on it. Also when triaging whether a firing alert is a true positive, stale, or a false positive
---

# Verify an Alert's Claim Before Replying

## Overview

An alert message is a claim, not a fact. It reflects one query's result at one moment, possibly minutes-to-hours ago, possibly from a rule with a known artifact. Answering from the alert text alone propagates whatever it got wrong. The loop: re-derive the claim from live data, classify it, then draft a reply.

## The loop

1. **Extract the claim.** What exactly does the alert assert? Which entity (node, service, cluster), which condition, at what time? Pull these from the alert's labels/annotations, not from the human's paraphrase.
2. **Find the originating rule.** Get the rule's actual query — not the alert summary. The query defines what "down" meant to the rule. (Grafana-managed: the rule UID is in the alert's labels; fetch it via `/api/v1/provisioning/alert-rules/<uid>` — see the grafana-alert-rule-api skill.)
3. **Re-run the same query twice**: at the alert's firing timestamp (`&time=<then>`) and now. This splits the world:
   - fired-then and true-now → **ongoing, true positive**
   - fired-then but false-now → **was real, since recovered (stale alert / already resolved)**
   - can't reproduce at fire-time → **suspect the rule** (wrong labels, scrape gap, threshold artifact)
4. **Cross-check with an independent source.** The metric and the alert share a pipeline; confirm through a different one — `kubectl get nodes` / service health endpoint / logs. Metric says NotReady but kubectl says Ready ⇒ telemetry problem, not an outage.
5. **Classify explicitly** in the reply — four verdicts:
   - **true positive** (ongoing)
   - **true-but-recovered**
   - **false positive** — only once you've named the mechanism (stale data, known artifact, mislabeled series); "can't reproduce" alone is suspicion, not a verdict
   - **telemetry fault** — the query reproduces but the independent check disagrees (step 4): the pipeline is lying, the system is fine, and the fix is in monitoring, not the system
6. **Draft, don't post.** Write the reply and show it to the human for review before it goes anywhere. Verification earns confidence, not authority to speak for someone.

## Reply shape

One sentence of verdict, then evidence with timestamps:

> Real but recovered: node X was NotReady 14:02–14:31 UTC (kubelet down, matches the alert window); it's Ready now and the alert resolved at 14:33. No action needed.

Include the query or command used, so the reader can re-check.

## Common mistakes

- Answering from the alert text or a dashboard screenshot without re-querying.
- Querying only "now" — a recovered alert looks like a false positive unless you also query fire-time.
- Trusting the same telemetry pipeline that produced the alert as its own confirmation.
- Saying "false positive" without naming the mechanism — if you can't say *why* it misfired, you haven't verified, you've guessed.
- Posting the reply directly instead of drafting for the human.
