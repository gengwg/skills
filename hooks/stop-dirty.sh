#!/usr/bin/env bash
# Stop: list uncommitted changes to tracked files in the session repo. Reminder only.
cwd=$(jq -r '.cwd // empty'); cwd=${cwd:-$PWD}
git -C "$cwd" rev-parse --show-toplevel >/dev/null 2>&1 || exit 0
dirty=$(git -C "$cwd" status --porcelain -uno --ignore-submodules=all 2>/dev/null | head -15)
[ -z "$dirty" ] && exit 0
jq -n --arg m "Uncommitted changes to tracked files in $(git -C "$cwd" rev-parse --show-toplevel) ($(git -C "$cwd" branch --show-current)):"$'\n'"$dirty" '{systemMessage:$m}'
exit 0
