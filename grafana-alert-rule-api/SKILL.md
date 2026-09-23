---
name: grafana-alert-rule-api
description: Use when creating or editing Grafana-managed alert rules via the provisioning API (curl/scripts, not the UI) — especially on a 409 conflict, when keep_firing_for silently doesn't stick, when fields vanish after a PUT, when a rule group's evaluation interval changes unexpectedly, or when a PUT returns 200 with a "Deprecated API" warning and nothing changes (Grafana 13)
---

# Grafana Alert Rule Provisioning API

## Overview

Editing Grafana-managed alert rules over `/api/v1/provisioning/alert-rules` has five traps that all return 200 (or a confusing 409) while doing the wrong thing. Every one has cost real debugging time.

## The traps

### 1. `provenance` decides your headers — check per rule

Rules created via the API carry `"provenance": "api"`; rules created in the UI have no provenance field. A folder can contain both. Test before writing:

```sh
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/v1/provisioning/alert-rules/$UID" | jq 'has("provenance")'
```

- `provenance` = `"api"` → PUT **without** `X-Disable-Provenance`, or you get **409 Conflict**.
- no provenance field (UI-created) → PUT **with** `X-Disable-Provenance: true`, or you get 409 the other way.
- `provenance` = `"file"` (or terraform) → the rule is owned by file provisioning and is **not editable via this endpoint** — change the source file instead.

### 2. PUT replaces the whole rule

There is no PATCH. Any field you omit is wiped. Always GET the current rule, modify the JSON, and re-send **everything**: `data`, `labels`, `annotations`, `noDataState`, `execErrState`, `isPaused`, `for`, `keep_firing_for`.

### 3. `keep_firing_for` is snake_case — camelCase is silently ignored

Sending `keepFiringFor` is accepted, ignored, and returns 200. The rule quietly loses its keep-firing window. Send `keep_firing_for` and verify it in the GET response afterwards.

### 4. Rule updates can silently reset the group interval

After any rule PUT, re-check the rule group's evaluation interval. `$FOLDER_UID` and `$GROUP` come from the rule body itself (`folderUID`, `ruleGroup`):

```sh
curl -s -H "Authorization: Bearer $TOKEN" \
  "$GRAFANA/api/v1/provisioning/folder/$FOLDER_UID/rule-groups/$GROUP" | jq .interval
```

If it changed, fix it by PUTting the group document back — GET it first and re-send it whole with the corrected `interval` (the group PUT replaces the group, same as trap 2):

```sh
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @group.json "$GRAFANA/api/v1/provisioning/folder/$FOLDER_UID/rule-groups/$GROUP"
```

### 5. On Grafana 13 the legacy PUT can be a silent no-op

A rule PUT returns 200 with a `Warning: 299 ... Deprecated API` response header and persists nothing: the rule's `updated` timestamp and version stay put. Tools that wrap this endpoint (MCP servers, scripts) inherit the no-op. The ruler group POST is no way around it either: it returns 400 when the group mixes provenance.

Write through the App Platform API instead, as a merge patch:

```sh
NS=$(curl -s -H "Authorization: Bearer $TOKEN" "$GRAFANA/api/frontend/settings" | jq -r .namespace)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/merge-patch+json" \
  -d '{"spec":{"paused":false}}' \
  "$GRAFANA/apis/rules.alerting.grafana.app/v0alpha1/namespaces/$NS/alertrules/$UID"
```

The namespace is `default` on self-hosted Grafana and `stacks-<id>` on Grafana Cloud. Take it from `/api/frontend/settings` instead of guessing. Confirm that `metadata.resourceVersion` changed on the GET-back. One token's PATCH has been seen to return success without bumping it; if that happens, retry with a different credential rather than trusting the response.

## Verify-after-write (always)

A 200 is not confirmation. GET the rule back and diff the fields you care about — especially `keep_firing_for` (the GET response echoes it in snake_case; if it's missing or zero, your write didn't stick), `for`, `isPaused`, and the group interval. The API's failure mode is silent acceptance, not errors.

## If the rules also live in IaC

When alert rules are provisioned from files in a repo, a change is **two writes**: the repo file (reviewable, survives re-provisioning) *and* the live API (takes effect now). Doing only one means either no effect today or your change reverted on the next sync. Update both, in whichever order your team reviews, and say so in the MR.

## Beyond the API write

A rule change isn't done when the PUT succeeds:

- **Runbook**: update the rule's runbook/description doc in the same change — a threshold nobody can explain six months later gets deleted or ignored.
- **Routing**: confirm the rule's labels still match the intended notification policy (a renamed severity/team label silently reroutes to the default receiver).
- **Severity sanity check**: "would I want on-call woken at 2am for this?" A single-entity fault (one node, one pod) is usually `warning`; only cluster-aggregate conditions ("N nodes down", "egress down") earn `critical`.

## Quick reference

```sh
# List rules (find a UID)
curl -s -H "Authorization: Bearer $TOKEN" "$GRAFANA/api/v1/provisioning/alert-rules" | jq -r '.[] | [.uid, .title] | @tsv'

# Read one rule
curl -s -H "Authorization: Bearer $TOKEN" "$GRAFANA/api/v1/provisioning/alert-rules/$UID"

# Update (API-provenance rule: NO X-Disable-Provenance)
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @rule.json "$GRAFANA/api/v1/provisioning/alert-rules/$UID"

# Update (UI-created rule: WITH the header)
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "X-Disable-Provenance: true" -d @rule.json "$GRAFANA/api/v1/provisioning/alert-rules/$UID"
```

## Common mistakes

- Assuming one header policy for a whole folder — provenance is per rule.
- Trusting the 200 — `keepFiringFor` typo-cases return success and do nothing.
- PUTting a minimal JSON body — everything not sent is deleted.
- Skipping the group-interval check after a rule edit.
- Ignoring a `Deprecated API` warning header on Grafana 13, where the legacy PUT may have saved nothing.
- Updating the live rule but not the IaC file (or vice versa).
