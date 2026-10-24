# MCP action classifier

Status: design draft, 2026-10-17.

Gate MCP tool calls in `guard.py` by what their effect does to the world, not
by their exact tool name. The idea comes from the "system boundary" section
(6.1) of *A Programming Paradigm for Spatiotemporal Composability*
(https://arxiv.org/abs/2608.25512).

## Problem

The guard matches MCP calls by exact tool name, and names drift. The one MCP
rule so far lived in the private overlay (`~/.claude/hooks/guard_local.py`,
`tool()`) and denied `mcp__claude_ai_Slack__slack_send_message` outside an
allowlist. The Slack connector now registers as
`mcp__plugin_operations_slack__slack_send_message`, so the rule silently stopped
firing. This was verified by driving the installed `guard.py` (1.7.5) with hook
JSON: the old name was denied, the current name got no decision. That one gap
is now closed (rollout step 1); the general problem remains.

Every other write-capable MCP tool in a session (Gmail send/forward, Calendar
create/delete, Grafana silences/rules/dashboards/incidents, Notion page writes,
Drive share/trash, Neon deletes) has no guard rule and relies on the harness's
generic permission prompt.

## Classification

Each call lands in one of three classes:

| Class | Meaning | Gate |
|---|---|---|
| inside | reads, and writes nobody else can see yet (drafts) | allow |
| compensatable | leaves our control, but has a known undo | allow, record the undo |
| irrecoverable | others see it or it cannot be taken back | ask (withhold) |

The hook receives only `tool_name` and `tool_input`. MCP tool annotations
(`readOnlyHint`, `destructiveHint`) are not passed to hooks, and the spec says
clients must treat them as untrusted anyway, so they are not an input.

Decision order:

1. **Override table**, exact `server + tool`, from the private overlay. It
   gives the class, plus the undo for compensatable entries.
2. **Destination allowlist.** Some irrecoverable calls are inside the boundary
   for one target, such as a Slack post to your own DM or a bot test channel.
   Private overlay.
3. **Verb defaults.** Split the tool part of `mcp__<server>__<tool>` on `_` and
   `-`, then apply the strongest match:
   - `draft` anywhere: inside (`slack_send_message_draft`, `create_draft`);
   - `send post reply forward share publish schedule delete trash drop revoke rotate reset`: irrecoverable;
   - `create update write add set install mutate patch`: irrecoverable unless
     overridden as compensatable;
   - `get list search query read fetch describe explain inspect find analyze`
     only: inside;
   - anything else: ask. Fail closed, so a new server is gated until classified.
4. **Multiplexers are always ask** unless overridden, because one tool can do
   anything: `grafana_api_request`, WorkOS `mutate`, Claude Docs `batch`,
   `browser_exec`, `javascript_tool`.

Compensatable starting set:

| Call | Undo | Undo needs |
|---|---|---|
| Grafana silence create (`alerting_silences_write`) | expire the silence | id from the response |
| Calendar `create_event` | `delete_event` | id from the response |
| Notion `notion-create-pages` | `notion-delete-pages` | id from the response |
| Notion `notion-delete-pages` | `notion-restore-pages` | id from the input |
| Gmail `trash_message` / `trash_thread` | `untrash_*` | id from the input |
| Neon `delete_project` | `recover_project` | id from the input; check the recovery window first |

Alert-rule writes stay irrecoverable when the rules are managed as code
(Terraform or similar): an API write fights that pipeline, so the change belongs
in the code. Dashboard writes are compensatable only if the prior version is
captured before the call. Leave them as ask until that exists.

## Undo ledger

A `PostToolUse` hook (matcher `mcp__.*`) appends each compensatable call to
`~/.claude/ledger/<session_id>.jsonl`: time, tool, short input summary, and the
undo call with its arguments, using ids from `tool_response`. A session-end or
handover step prints it newest first. The guard never runs an undo itself. The
ledger lives outside any repo because sessions span repos. It holds ids and
summaries, never message bodies or credentials.

## Where the code goes

- **Engine** (verb split, defaults, decision, ledger writer): `hooks/guard.py`
  in this repo. Generic, with no org names, channel ids or hosts. This repo is
  public, so scrub before every push.
- **Override table and allowlists**: the private overlay, extending the
  existing `tool()` hook. Overrides are applied before the engine defaults.

## Failure modes

- **A crash reads as no decision.** `guard.py` returns silently on bad input,
  and empty stdout means the harness falls back to its own prompt. For MCP
  calls, catch exceptions in the engine and return ask.
- **Prompt fatigue.** Too many asks train click-through. Measure before
  enforcing (rollout step 2).
- **Verb misreads** (`update_enabled_skills`, `designer_tool`) fall to ask.
  That is the safe direction; fix them with overrides.

## Rollout

1. **Close the Slack gap now, separately.** Done 2026-10-17. The overlay
   matches the `__slack_send_message` and `__slack_schedule_message` suffixes,
   so any Slack connector is covered. Tested with hook JSON: old and current
   names were denied outside the allowlist; the allowlisted channel, drafts and
   reads were unaffected.
2. **Log only for a week.** Started 2026-10-17 (1.7.6): `hooks/mcp_classify.py`
   appends the class each call would get to `~/.claude/mcp-classify.jsonl`
   (tool name and class only, never the input). It has the verb rules and
   multiplexer list, but no override table or allowlist yet. Review the ask and
   unknown counts. The first week (2,017 calls) would have asked on 16%,
   mostly Chrome and a bulk Calendar edit. On 2026-10-24 a generic override
   table and a GET check for `grafana_api_request` went into the logger. Log a
   second week.
3. **Enforce** irrecoverable and unknown as ask.
4. **Turn on the ledger** for compensatable calls, and print it at session end.
5. **Refactor:** fold the Slack rule into the override table and delete the
   name-specific code.

## Tests

Extend `test_guard.py`, driving `guard.py` with real hook JSON built in Python,
never `echo` in a shell: mangled JSON gives empty stdout, which reads as allow.
Each class gets a case. Include known-bad controls: break the verb table and
confirm the tests fail. Both Slack names must be denied.

## Out of scope

Shell commands, which the existing guard covers. Judging whether an action is a
good idea; the classifier only judges whether it can be taken back.

## Open questions

- How does ask behave in auto mode: does the harness resolve it itself, or
  does it reach the human? If it auto-approves, irrecoverable calls need deny,
  with a message telling the agent to hand the call to the human.
- Ledger retention: keep per session, or prune after N days?
