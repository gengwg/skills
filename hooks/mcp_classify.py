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


def classify(name):
    """Class for an mcp__<server>__<tool> name, and the token that decided it."""
    tool = name.split("__", 2)[-1].lower()
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
        cls, why = classify(name)
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session": h.get("session_id", ""), "tool": name, "class": cls, "why": why}
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
