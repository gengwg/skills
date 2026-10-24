#!/usr/bin/env python3
"""PostToolUse hook: log the class each MCP call would get, without gating it.

Rollout step 2 of mcp-classifier-design.md. Appends one line per call to
~/.claude/mcp-classify.jsonl. Never prints and never fails the call.
"""
import json, os, re, sys, time

LOG = os.path.expanduser("~/.claude/mcp-classify.jsonl")

# One tool that can do anything, so its name says nothing about its effect.
MULTIPLEXERS = {"grafana_api_request", "mutate", "batch", "browser_exec", "javascript_tool"}
IRRECOVERABLE = {"send", "post", "reply", "forward", "share", "publish", "schedule",
                 "delete", "trash", "drop", "revoke", "rotate", "reset"}
WRITE = {"create", "update", "write", "add", "set", "install", "mutate", "patch"}
READ = {"get", "list", "search", "query", "read", "fetch", "describe", "explain",
        "inspect", "find", "analyze"}
# (service, tool) pairs whose verb misleads, applied before the verb rules. The
# service matches as a substring of the server so prefix renames still match.
OVERRIDES = {
    ("chrome", "navigate"): "inside", ("chrome", "tabs_context_mcp"): "inside",
    ("chrome", "tabs_create_mcp"): "inside", ("chrome", "tabs_close_mcp"): "inside",
    ("grafana", "ask_assistant"): "inside", ("calendar", "suggest_time"): "inside",
    ("", "authenticate"): "inside",
    # A click or form fill can submit anything.
    ("chrome", "computer"): "multiplexer", ("chrome", "form_input"): "multiplexer",
    # The design's starting set: each has a known undo.
    ("grafana", "alerting_silences_write"): "compensatable",
    ("calendar", "create_event"): "compensatable",
    ("notion", "notion-create-pages"): "compensatable",
    ("notion", "notion-delete-pages"): "compensatable",
    ("gmail", "trash_message"): "compensatable", ("gmail", "trash_thread"): "compensatable",
    ("neon", "delete_project"): "compensatable",
}


def classify(name, inp=None):
    """Class for an mcp__<server>__<tool> call, and the token that decided it."""
    _, server, tool = name.lower().split("__", 2)
    for (service, t), cls in OVERRIDES.items():
        if t == tool and service in server:
            return cls, "override"
    if tool == "grafana_api_request" and (inp or {}).get("method", "GET").upper() == "GET":
        return "inside", "GET"
    if tool in MULTIPLEXERS:
        return "multiplexer", tool
    words = re.split(r"[_\-]", tool)
    if "draft" in words:
        return "inside", "draft"
    for vocab, cls in ((IRRECOVERABLE, "irrecoverable"), (WRITE, "irrecoverable"), (READ, "inside")):
        hit = next((w for w in words if w in vocab), None)
        if hit:
            return cls, hit
    return "unknown", ""


def main():
    try:
        h = json.load(sys.stdin)
        name = h.get("tool_name", "")
        if not name.startswith("mcp__"):
            return
        cls, why = classify(name, h.get("tool_input"))
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session": h.get("session_id", ""), "tool": name, "class": cls, "why": why}
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
