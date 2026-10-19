---
name: tofu-gitlab-state-local-apply
description: Use when running `tofu`/`terraform` plan or apply locally against a GitLab-managed HTTP state backend, when init fails with "HTTP remote state endpoint requires auth", when one credentials file serves several modules/states, or when an MR's plan job stays red until someone applies.
---

# Local tofu apply against GitLab-managed state

For modules whose CI only plans and a person applies locally. Each trap below looks like success or like an auth problem, and costs a round trip to find.

## Setup

```sh
set -a; . ~/.config/<team>/<module>.env; set +a   # KEY=value files have no `export`
export TF_HTTP_ADDRESS="https://gitlab.com/api/v4/projects/<id>/terraform/state/<state-name>"
export TF_HTTP_LOCK_ADDRESS="$TF_HTTP_ADDRESS/lock" TF_HTTP_UNLOCK_ADDRESS="$TF_HTTP_ADDRESS/lock"
export TF_HTTP_LOCK_METHOD=POST TF_HTTP_UNLOCK_METHOD=DELETE
echo "$TF_HTTP_ADDRESS"                  # confirm the state name before anything else
tofu init -reconfigure -input=false
tofu plan -out=tmp/apply.tfplan          # review, then:
tofu apply tmp/apply.tfplan
```

If the repo ships a wrapper script for this, use it. Its whole job is these lines.

## Traps

- **`source file` exports nothing** when the file is plain `KEY=value`. The shell sees the variables and tofu does not, so init asks for `address` interactively or fails with `requires auth`. Use `set -a`. To check a file without printing secrets: `grep -oE '^(export )?[A-Za-z_]+=' file`.
- **A shared credentials file aims every module at one state.** If the file sets `TF_HTTP_ADDRESS` for module A and you source it for module B, B plans against A's state. The usual symptom is a plan to destroy everything A manages. Always re-export the address after sourcing, and read the resources in the plan before typing `yes`.
- **`.terraform` remembers the last backend address.** After fixing the env, run `init -reconfigure`, or init either keeps the stale address or stops to ask about migrating state.
- **glab's token is not a PAT.** `glab config get token` can return a 64-character OAuth token. It was rejected as `TF_HTTP_PASSWORD` in practice, with the username and with `oauth2`. Use a PAT with `api` scope. Writing state (the lock) also needs Maintainer on the project.
- **A plan without `-out` is not an apply.** Pasted output ending in "You didn't use the -out option" means nothing changed. Apply the saved plan so what lands is what was reviewed.
- **Verify the target, not the tool's message.** After `Apply complete!`, read the live object back: version or `updated` bumped, the new field present. Then re-run the MR's plan job and expect `No changes`.
- **`-detailed-exitcode` MR gates go red on any diff**, including the MR's own change. Pick one order per module and make the tooling agree with it:
  - *Apply, then merge:* apply from the MR branch, re-run the pipeline, merge.
  - *Merge, then apply:* set the plan job to `allow_failure: exit_codes: [2]` so the MR's own diff is a warning, and have it still fail when rc 2 comes without a `Plan:` line, so a crash stays red. Apply from the default branch after the merge.

  A red-until-applied gate plus an apply script that only runs from the default branch is a deadlock. Someone will end up bypassing one of them.
- **The plan shows all drift in the workspace, not just your change.** A resource your diff doesn't touch may have been applied live from someone else's unmerged branch. Applying the whole plan reverts their fix. Account for every resource in the plan. For a foreign one, read the live object's version history to see who wrote it, then `-target` your own resource or sort the drift out with that person first. A list element inserted mid-list shows as one element "changing into" the new one plus a re-added element at the end. That is normal.
- **OpenTofu ignores `required_version` in a `.tf` file.** It reads that as Terraform's constraint. Only a `.tofu` file binds it, and once a `.tofu` sibling exists OpenTofu skips the matching `.tf` file entirely, including its `required_providers`. Moving the constraint means moving the whole file. Test a version claim with an unsatisfiable constraint and check the exit code of both `init` and `plan`.
