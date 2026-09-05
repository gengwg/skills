#!/usr/bin/env bash
# PostToolUse Write|Edit: format .py/.go, lint .yml/.yaml (advisory).
f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty'); [ -f "$f" ] || exit 0
up() { local d; d=$(dirname "$f"); while [ "$d" != "/" ]; do for n in "$@"; do [ -e "$d/$n" ] && { echo "$d"; return; }; done; d=$(dirname "$d"); done; }
msg=""
case "$f" in
  *.py)
    proj=$(up pyproject.toml); [ -n "$proj" ] && grep -q ruff "$proj/pyproject.toml" || exit 0
    cd "$proj" || exit 0
    r="uv run ruff"; $r --version >/dev/null 2>&1 || r="uv run --with ruff ruff"
    $r format -q "$f" 2>&1 | head -5
    msg=$($r check --fix -q "$f" 2>&1 | head -30) ;;
  *.go)
    gofmt -w "$f" 2>&1 | head -5 ;;
  *.yml|*.yaml)
    ycfg=$(up .yamllint .yamllint.yml .yamllint.yaml); y=$( (cd "${ycfg:-$(dirname "$f")}" && yamllint -f parsable "$f" 2>&1) | head -20)
    acfg=$(up .ansible-lint ansible.cfg); a=""
    [ -n "$acfg" ] && a=$( (cd "$acfg" && timeout 50 ansible-lint -p --offline "$f" 2>/dev/null) | grep -v '^$' | head -20)
    msg=$(printf '%s\n%s' "$y" "$a" | sed '/^$/d') ;;
esac
[ -n "$msg" ] && jq -n --arg m "Lint findings for $f (advisory):"$'\n'"$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
exit 0
