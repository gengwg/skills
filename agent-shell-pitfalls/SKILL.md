---
name: agent-shell-pitfalls
description: Use when a shell script run through an AI agent's Bash tool or a CI job must stop on a failing check before a commit, push, or deploy; when capturing an exit code through a pipe or tee; when a gate is a python heredoc; when stopping a background process by name with pkill -f or pgrep -f; or when the agent's shell is zsh and bash-style commands fail with "no matches found", "read-only variable: status", "parse error near ()", "= not found", or a pathspec holding several space-separated names.
---

# Agent shell pitfalls

## Overview

Each of these looks like a gate or a safe stop and is not. The failure is
silent: the script carries on, or kills the wrong process, and the output
looks normal.

## 1. `set -e` does nothing inside `&&`, `||` or `if`

Bash ignores errexit for every command in an `&&`/`||` list (except the last)
and in an `if` or `while` condition, including inside functions called there.
Agent harnesses commonly wrap your script as `eval '<script>' && ...`, so
`set -e` at the top of a tool call gates nothing:

```bash
set -e
go vet ./...                          # fails
git commit -m "add tests" -- f_test.go   # runs anyway
git push                               # runs anyway
```

Probe your harness once: `set -e; false; echo REACHED`. If it prints, chain
every gate explicitly:

```bash
go vet ./... && go test ./... && git commit -m "..." -- f_test.go && git push
```

or end each check with `|| exit 1`. The same holds for a python heredoc used
as a gate: its `sys.exit(1)` only ends python. Write `python3 - <<'EOF' || exit 1`
or `&&` the next step onto it.

## 2. Capturing `$?` inside a piped group under `set -e`

```bash
set -eu
{ tofu plan -detailed-exitcode; echo "$?" > rc; } | tee plan.txt
```

The group is a pipeline element, so it runs in a subshell that inherits
errexit. On exit 2 the subshell dies before the `echo`. `rc` is never
written, `tee` returns 0, and the step stays green. It works on every
exit-0 day, so it passes for weeks and breaks on the first real result.
Fix inside the group: `{ set +e; cmd; echo "$?" > rc; } | tee out`, or
`rc=0; cmd > out 2>&1 || rc=$?` with no pipe. `rm -f rc` first: a stale
file from an earlier run reads as this run's result. Separately,
`cmd | tee log && next` runs `next` even when `cmd` fails; write
`set -o pipefail; cmd | tee log && next`.

**Test the producer's failing path, not the consumer.** A fixture file
holding `2` proves only that the reader handles 2. Run the real snippet with
a stub that exits 2, and confirm the old version fails that test.

## 3. `pkill -f` and `pgrep -f` match more than the target

`-f` matches full command lines. Any live shell whose argv contains the
pattern matches too:

- The calling shell, when the pattern is in its own command. pkill then kills the tool call itself (exit 143).
- An ancestor that holds the start command: the same script that started the process, or the harness's wrapper for a background task.

`pkill -f '[n]ode server.js'` only fixes the first case. The bracket stops
the pattern matching its own literal text, but the ancestor's argv holds
the unbracketed `node server.js` and still matches. With no such ancestor
alive, the bracket avoids the self-match, but `-f` still hits any other
process with that text. Killing by port is worse: whatever holds the port
may belong to someone else.

Record the PID when you start the process, and stop that PID:

```bash
node server.js --port 4111 > server.log 2>&1 & echo $! > server.pid
pid=$(cat server.pid)
ps -o args= -p "$pid" | grep -q '^node server.js' && kill "$pid"
```

Inside `bash -c '... &'`, write `$!` to the file in that same command; the
outer shell never sees it. Matching the args guards against a reused PID;
`ps -p` alone succeeds for whatever process now holds it.
If the PID is lost, list candidates with `pgrep -a -x node`, read each
`args`, and kill one exact PID.

## 4. The Bash tool may be running zsh

An agent's "Bash" tool runs the user's login shell, often zsh with
oh-my-zsh. Probe once: `echo ${ZSH_VERSION:-bash}`. Under zsh, ordinary
bash fails like this:

| Bash habit | zsh result | Fix |
|---|---|---|
| `F="a b c"; git add $F` | One argument, `pathspec 'a b c' did not match` | `F=(a b c); git add "${F[@]}"` |
| `echo ====` | `=== not found`, and the rest of the call is skipped (a leading `=` means command path expansion) | Quote it: `echo '===='` |
| `ls *.bak 2>/dev/null` with no match | `no matches found`; the command never runs and `2>/dev/null` doesn't silence it | `find . -maxdepth 1 -name '*.bak'` |
| `status=$?` | `read-only variable: status` aborts the call | Use another name: `rc=$?` |
| `g() { ...; }` | `parse error near ()` when an alias `g` exists; `unalias g` in the same call doesn't help, since aliases expand at parse time | `function g { ...; }`, or a longer name |
| `rm file` | Aliased to `rm -i`, prompts with no terminal | `command rm -f file` |

For anything longer than a line or two, run it in bash instead of
translating it: `bash <<'EOF' ... EOF`. Non-interactive bash has no
aliases and none of the traps above. Everything in sections 1-3 still
applies inside it.

## Common mistakes

- Reading "the script has `set -e`" as proof that a failed check stopped the push.
- Calling a gate verified because its check printed a failure. Check the lines after it did not run.
- Verifying an exit-code fix with a fixture instead of a real non-zero run.
- Trusting the `[x]yz` bracket trick to make `pkill -f` safe.
