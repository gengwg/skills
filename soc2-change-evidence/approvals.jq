# Classify merged PRs for a change-management test.
# Input: gh pr list --json number,url,author,mergedAt,headRefOid,reviews,commits
# Output: CSV, one row per PR; anything but OK is an exception.
["pr", "merged_at", "author", "approvers", "result", "url"],
(.[] | . as $pr
  | ([.author.login] + [.commits[].authors[].login] | unique) as $authors
  | [.reviews[] | select(.state == "APPROVED" and (.author.login | IN($authors[]) | not))] as $indep
  | [$indep[] | select(.submittedAt <= $pr.mergedAt)] as $pre
  | [.number, .mergedAt, .author.login,
     ([$pre[].author.login] | unique | join(";")),
     (if ($indep | length) == 0 then "NO_INDEPENDENT_APPROVAL"
      elif ($pre | length) == 0 then "APPROVED_AFTER_MERGE"
      elif any($pre[]; .commit.oid == $pr.headRefOid) then "OK"
      else "STALE_APPROVAL" end),
     .url])
| @csv
