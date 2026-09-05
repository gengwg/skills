#!/usr/bin/env bash
# SessionStart: print facts every session otherwise re-derives.
cwd=$(jq -r '.cwd // empty' 2>/dev/null); cwd=${cwd:-$PWD}
ctx=$(kubectl config current-context 2>/dev/null) && echo "kubectl current-context: $ctx (always pass --context explicitly; treat non-local contexts as production)."
if top=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null); then
  echo "git: branch $(git -C "$cwd" branch --show-current) at $top. Never commit on main/master/develop; branch or worktree first."
fi
exit 0
