---
name: soc2-change-evidence
description: Use when pulling SOC 2 change-management (CC8.1) evidence from GitHub pull requests or GitLab merge requests for an auditor, testing whether every merged change had independent review across a Type 2 audit period, or writing the control description and exception list that go with it
---

# SOC 2 Change-Management Evidence

## Overview

For each merged change the auditor asks one question: did someone other than the author approve this exact code before it merged? "Has an APPROVED review" and `reviewDecision` answer a weaker question. Agents reliably pull the full population, paginate and flag direct pushes, but they skip approval timing and staleness. The two jq files here test all three conditions.

| Test | Fails when | Result |
|---|---|---|
| Independent | the only approvers are the author (or, on GitHub, someone who pushed commits) | `NO_INDEPENDENT_APPROVAL` |
| Before merge | every independent approval is timestamped after the merge | `APPROVED_AFTER_MERGE` |
| On the merged code | no pre-merge approval covers the final head | `STALE_APPROVAL` |

On a public repo sampled over three weeks, 14 of 51 merged PRs were stale, mostly from rebases after approval. That's common, and every one is still a row the auditor will ask about.

## GitHub

```bash
R=org/repo
gh pr list -R "$R" --base main --state merged --limit 1000 \
  --search "merged:2026-01-01..2026-06-30" --json number --jq '.[].number' > prs.txt
wc -l < prs.txt        # 1000 means the search cap truncated it: split the range
while read n; do
  gh pr view "$n" -R "$R" --json number,url,author,mergedAt,headRefOid,reviews,commits
done < prs.txt | jq -s . > prs.json
jq length prs.json     # must equal prs.txt
jq -r -f approvals.jq prs.json > approvals.csv
```

Fetch one PR at a time. `gh pr list --json commits` fails above roughly 50 PRs with "exceeds the maximum limit of 500,000" nodes.

## GitLab

GitLab does not record which commit was approved. The MR versions API records when each head was pushed, so an approval covers the merged code if it is later than the push of the version whose head is the MR's `sha`.

```bash
P=group%2Fproject
glab api --paginate "projects/$P/merge_requests?state=merged&target_branch=main&updated_after=2026-01-01T00:00:00Z&per_page=100" \
  | jq -s -r 'add | map(select(.merged_at >= "2026-01-01" and .merged_at < "2026-07-01")) | .[].iid' > mrs.txt
while read i; do
  jq -n --argjson mr "$(glab api projects/$P/merge_requests/$i)" \
        --argjson ap "$(glab api projects/$P/merge_requests/$i/approvals)" \
        --argjson v  "$(glab api projects/$P/merge_requests/$i/versions)" \
        '$mr + {approved_by: $ap.approved_by, versions: $v}'
done < mrs.txt | jq -s . > mrs.json
jq length mrs.json     # must equal mrs.txt
jq -r -f gitlab-approvals.jq mrs.json > approvals.csv
```

The list endpoint filters on update time, and merging an MR updates it, so `updated_after` misses nothing. The `merged_at` filter does the real cut. `UNKNOWN_HEAD` means no version matched the merged sha; check that MR by hand.

### GitLab direct pushes

These are commits on `main` that no MR merged. With merge commits, every MR leaves a "See merge request" line on its first-parent commit, so only the rest need a lookup. On fast-forward projects there is no such line, so drop the `--grep` and look up every commit.

```bash
git log origin/main --first-parent --since=2026-01-01T00:00:00Z --until=2026-07-01T00:00:00Z \
  --grep='See merge request' --invert-grep --format=%H > candidates.txt
while read c; do
  r=$(glab api "projects/$P/repository/commits/$c/merge_requests") || r=""
  v=$(printf '%s' "$r" | jq -r 'if type == "array" then (if any(.[]; .state == "merged") then "MR" else "DIRECT" end) else "ERR" end')
  echo "$c ${v:-ERR}"
done < candidates.txt > direct-pushes.txt
grep -c ' ERR$' direct-pushes.txt     # must be 0: rerun those commits
```

Use `printf`, not `echo`. zsh's `echo` expands the `\n` inside MR descriptions, jq rejects the result, and every lookup looks like a failure. Never count `ERR` as either `DIRECT` or clean.

## Before trusting the CSV

The row count must equal the list count. In testing, a TLS handshake timeout dropped changes with exit 0 on both GitHub and GitLab, and the CSV looked complete.

## Reading exceptions

- **`STALE_APPROVAL`.** Run `git range-diff` between the approved head and the merged head. If it shows a rebase with no content change, record that as the reason and keep the row.
- **`APPROVED_AFTER_MERGE`** is a retroactive review. It is an exception, not evidence.
- **Bot approvals** (Copilot, GitLab Duo, apps) count as independent in the CSV. Agree with the control owner whether they count, then filter by login.
- **GitLab commit authors** come back as emails only, so the GitLab check compares approvers to the MR author alone. The project setting `merge_requests_disable_committers_approval` is the evidence for the rest.

## Control description

Write it from the settings you export, not from the policy:

- **GitHub:** `repos/R/branches/main/protection` (`dismiss_stale_reviews`, `enforce_admins`), or `repos/R/rules/branches/main` for rulesets.
- **GitLab:** `projects/:id/approvals` (`reset_approvals_on_push`, `merge_requests_author_approval`, `merge_requests_disable_committers_approval`). This needs Maintainer; Developer gets 403.

If stale approvals are not dismissed or reset, don't write "every change is approved before merge". The `STALE_APPROVAL` rows contradict it.

These snapshots show today's settings, not the settings during the period. GitHub's org audit log, which has the change history, keeps 180 days, and its API needs Enterprise Cloud. Export it before the period ages out.
