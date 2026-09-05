#!/usr/bin/env python3
"""PreToolUse guard for Bash. Reads hook JSON on stdin, prints a permission decision or nothing.

Denies: kubectl writes without --context, switching the global kube context, git push --force,
--no-verify, commits/pushes on protected branches, submodule pin bumps.
Asks: MR/PR merges, rm -rf outside scratch dirs.
"""
import json, os, re, subprocess, sys

PROTECTED = {"main", "master", "develop"}
KUBE_WRITE = {"apply", "create", "delete", "patch", "edit", "replace", "scale", "rollout", "cordon", "uncordon", "drain", "taint", "label", "annotate", "exec", "set", "expose", "run"}
SAFE_RM_PREFIXES = ("/tmp/claude",)
SEG = r"[^\n;|&]*"  # stay within one shell statement
GIT = r"\bgit\b(?:\s+-[Cc]\s+\S+|\s+--\S+)*\s+"  # git + global opts, then the subcommand


def out(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def git(d, *args):
    try:
        return subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def repo_dir(cmd, cwd):
    """Last `cd X` or `git -C X` in the command, else the session cwd."""
    for cd, gc in reversed(re.findall(r"(?:^|[;&|\n]\s*)cd\s+(\S+)|git\s+-C\s+(\S+)", cmd)):
        p = os.path.expanduser((cd or gc).strip("\"'"))
        if "$" in p:
            continue
        return p if os.path.isabs(p) else os.path.join(cwd, p)
    return cwd


def submodules(d):
    return {l.split("\t", 1)[1] for l in git(d, "ls-files", "--stage").splitlines() if l.startswith("160000")}


def strip_heredocs(cmd):
    return re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\1\s*$", "", cmd, flags=re.S | re.M)


def kubectl_verb(stmt):
    """Subcommand of the kubectl invocation in stmt, skipping global flags and $VARS."""
    toks = stmt.split()
    # kubectl must be the command itself, not a word inside a message or argument
    while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in ("sudo", "command", "$(", "(")
                    or (toks[0] == "timeout" and len(toks) > 1 and (toks.pop(1) or True))):
        toks.pop(0)
    if not toks or toks[0] != "kubectl":
        return None
    toks = toks[1:]
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("$"):
            i += 1
        elif t.startswith("-"):
            i += 1 if "=" in t or t in ("-v", "--insecure-skip-tls-verify") else 2
        else:
            if t == "rollout" and i + 1 < len(toks) and toks[i + 1] in ("status", "history"):
                return "rollout-read"
            return t
    return None


def kubectl_guard(cmd):
    if re.search(r"kubectl\s+config\s+use-context", cmd):
        out("deny", "Switching the global kube context is not allowed. Pass --context on each command instead.")
    for stmt in re.split(r"\n|&&|\|\||;|\|", strip_heredocs(cmd)):
        if "ssh " in stmt or "kubectl" not in stmt or kubectl_verb(stmt) not in KUBE_WRITE:
            continue
        if "--context" in stmt:
            continue
        if any(re.search(r"\b" + v + r"=[^\n]*--context", cmd) for v in re.findall(r"\$\{?(\w+)\}?", stmt)):
            continue
        out("deny", f"kubectl write without explicit --context: `{stmt.strip()[:120]}`. Add --context=<cluster>; never rely on the current context.")


def bash(cmd, cwd):
    d = repo_dir(cmd, cwd)
    if "kubectl" in cmd:
        kubectl_guard(cmd)
    commit = re.search(GIT + r"commit\b" + SEG, cmd)
    push = re.search(GIT + r"push\b" + SEG, cmd)
    add = re.search(GIT + r"add\b" + SEG, cmd)

    if push and re.search(r"(\s-f\b|--force)", push.group(0)):
        out("deny", "git push --force is not allowed. Push a new commit instead.")
    if (commit or push) and "--no-verify" in cmd:
        out("deny", "--no-verify is not allowed.")
    if push:
        raw = push.group(0).split()[push.group(0).split().index("push") + 1:]
        toks = [t for i, t in enumerate(raw) if not t.startswith("-") and (i == 0 or raw[i - 1] not in ("-o", "--push-option", "--receive-pack", "--repo"))]
        refspec = toks[1] if len(toks) > 1 else ""
        target = refspec.rsplit(":", 1)[-1].removeprefix("refs/heads/") if refspec else git(d, "branch", "--show-current")
        if target in PROTECTED:
            out("deny", f"Refusing to push to protected branch '{target}'. Push a feature branch and open an MR/PR.")
    if commit:
        br = git(d, "branch", "--show-current")
        if br in PROTECTED:
            out("deny", f"On '{br}' in {d}. Create a feature branch (or worktree) before committing.")
        subs = submodules(d)
        if subs:
            staged = set(git(d, "diff", "--cached", "--name-only").split())
            if re.search(r"(\s-a\w*\b|--all)", commit.group(0)):
                staged |= set(git(d, "diff", "--name-only").split())
            hit = sorted(staged & subs)
            if hit:
                out("deny", f"Commit would bump submodule pin(s) {hit}. Unstage them (git restore --staged <path>) unless the pin bump is intended.")
    if add:
        subs = submodules(d)
        if subs:
            toks = [t.strip("\"'").rstrip("/") for t in add.group(0).split()[add.group(0).split().index("add") + 1:]]
            if any(t in subs for t in toks):
                out("deny", "git add of a submodule path bumps its pin. Add it explicitly only when the pin bump is intended.")
            if any(t in ("-A", "--all", ".", "-u", "--update") for t in toks):
                dirty = set(git(d, "diff", "--name-only").split()) & subs
                if dirty:
                    out("deny", f"git add {toks} would stage submodule pin(s) {sorted(dirty)}. Add files explicitly.")

    if re.search(r"glab\s+mr\s+merge\b|\bgh\s+pr\s+merge\b", cmd) or re.search(r"glab\s+api\b" + SEG + r"merge_requests/\d+/merge\b", cmd):
        out("ask", "Merging is a human decision. Confirm this merge.")

    for m in re.finditer(r"\brm\s+(?:-\w*r\w*\s+|-\w*f\w*\s+|--recursive\s+|--force\s+)+(" + SEG + ")", cmd):
        flags = m.group(0)
        if not (re.search(r"-\w*r|--recursive", flags) and re.search(r"-\w*f|--force", flags)):
            continue
        for t in m.group(1).split():
            if t.startswith("-"):
                continue
            t = t.strip("\"'")
            if "$" in t:
                out("ask", f"rm -rf on a variable path ({t}); confirm.")
            p = t if os.path.isabs(t) else os.path.normpath(os.path.join(d, t))
            if not (p.startswith(SAFE_RM_PREFIXES) or "/worktrees/" in p):
                out("ask", f"rm -rf outside scratchpad/worktrees: {p}")

    if re.search(r"glab\s+api\b" + SEG + r"(?:--method|-X)\s*(?:PUT|POST)\b", cmd) and "--input" in cmd \
            and not re.search(r"content-type", cmd, re.I):
        out("deny", "glab api PUT/POST --input returns HTTP 415 (exit 0!) without --header \"Content-Type: application/json\". Add the header.")


def main():
    try:
        h = json.load(sys.stdin)
    except Exception:
        return
    if h.get("tool_name") == "Bash":
        bash((h.get("tool_input") or {}).get("command", ""), h.get("cwd") or os.getcwd())


if __name__ == "__main__":
    main()
