# Classify merged MRs for a change-management test.
# Input: array of MR objects, each with approved_by (from /approvals) and versions (from /versions) added.
# GitLab does not record which commit was approved, so "on the merged code" means
# approved after the version whose head is the merged sha was pushed.
["mr", "merged_at", "author", "approvers", "result", "url"],
(.[] | . as $mr
  | ([.versions[] | select(.head_commit_sha == $mr.sha) | .created_at] | min) as $pushed
  | [.approved_by[] | select(.user.username != $mr.author.username)] as $indep
  | [$indep[] | select(.approved_at <= $mr.merged_at)] as $pre
  | [.iid, .merged_at, .author.username,
     ([$pre[].user.username] | unique | join(";")),
     (if ($indep | length) == 0 then "NO_INDEPENDENT_APPROVAL"
      elif ($pre | length) == 0 then "APPROVED_AFTER_MERGE"
      elif $pushed == null then "UNKNOWN_HEAD"
      elif any($pre[]; .approved_at >= $pushed) then "OK"
      else "STALE_APPROVAL" end),
     .web_url])
| @csv
