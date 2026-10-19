#!/usr/bin/env python3
"""PreToolUse guard for Bash. Reads hook JSON on stdin, prints a permission decision or nothing.

Denies: kubectl writes without --context, switching the global kube context, git push --force,
--no-verify, commits/pushes on protected branches, submodule pin bumps, Co-Authored-By
trailers in Kubernetes-org repos (EasyCLA).
Asks: GitLab MR merges, rm -rf outside scratch dirs.
"""
import json, os, re, subprocess, sys

PROTECTED = {"main", "master", "develop"}
KUBE_WRITE = {"apply", "create", "delete", "patch", "edit", "replace", "scale", "rollout", "cordon", "uncordon", "drain", "taint", "label", "annotate", "exec", "set", "expose", "run"}
SAFE_RM_PREFIXES = ("/tmp/claude",)
SEG = r"[^\n;|&]*"  # stay within one shell statement
GIT = r"\bgit\b(?:\s+-[Cc]\s+\S+|\s+--\S+)*\s+"  # git + global opts, then the subcommand
CMD_START = r"\s*\(?\s*(?:\w+=\S*\s+)*"
SWITCH = GIT + r"(?:switch\s+(?:(?:-[cC]|--create|--force-create)\s+)?|checkout\s+-[bB]\s+)(?!-)([\w./-]+)"
# EasyCLA fails any co-author it cannot match to a GitHub account with a signed CLA.
CLA_REMOTE = re.compile(r"github\.com[:/]kubernetes(?:-[\w-]+)?/", re.I)
TRAILER = re.compile(r"^\s*co-authored-by:", re.I | re.M)


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


def resolve(p, base, env=None):
    """Absolute path for a cd / git -C target. Falls back to `base` when it cannot be
    known, which fails CLOSED: the guard then judges the session's repo, so a real
    commit on a protected branch is still caught."""
    p = os.path.expanduser(p.strip("\"'"))
    # `cd "$S/tt/work"` after `S=/tmp/...` is a repo the guard CAN know, and getting it
    # wrong denied commits in a throwaway repo because the session sat on develop.
    if env:
        p = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: env.get(m.group(1) or m.group(2), "\0"), p)
    if "$" in p or "\0" in p:
        return base
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def statements(cmd, cwd):
    """(statement, repo dir, branch) triples. `cd` carries forward; `git -C` applies to its own
    statement only. branch is set when the command itself decides it: a `git switch` earlier in
    the same repo and `&&`-chained to this statement, or "" inside an ssh remote command, whose
    branch lives on another host. None means ask git."""
    env, branches, quote = {}, {}, None
    parts = re.split(r"(\n|&&|\|\||;)", cmd)
    for stmt, sep in zip(parts[0::2], ["&&"] + parts[1::2]):
        # Past `;`, `||` or a newline an earlier switch may have failed and this still runs.
        # A switch onto a protected branch is kept: failing closed there is the point.
        if sep != "&&":
            branches = {k: v for k, v in branches.items() if v in PROTECTED}
        # The split cuts `ssh host 'cd x && git commit'` apart; track the open quote.
        if quote:
            if stmt.count(quote) % 2:
                quote = None
            yield stmt, cwd, ""
            continue
        m = re.match(r"\s*(?:\w+=\S*\s+)*ssh\b[^'\"]*(['\"])", stmt)
        if m:
            if stmt[m.start(1):].count(m.group(1)) % 2:
                quote = m.group(1)
            yield stmt, cwd, ""
            continue
        # Plain VAR=value assignments only, so a path built from them resolves. An
        # env-prefixed command (SSH_AUTH_SOCK=... git push) lands here too; harmless.
        for k, v in re.findall(r"(?:^|\s)(\w+)=(\S*)", stmt):
            env[k] = v.strip("\"'")
        m = re.match(r"\s*\(?\s*cd\s+(\S+)", stmt)
        if m:
            cwd = resolve(m.group(1), cwd, env)
        gc = re.search(r"\bgit\s+-[Cc]\s+(\S+)", stmt)
        d = resolve(gc.group(1), cwd, env) if gc else cwd
        yield stmt, d, branches.get(d)
        sw = re.match(CMD_START + SWITCH, stmt)
        if sw:
            branches[d] = sw.group(1)
        elif re.match(CMD_START + GIT + r"(?:switch|checkout)\b", stmt):
            branches.pop(d, None)  # `switch -`, `checkout <branch>`: ask git again


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


def git_guard(stmt, d, br=None):
    commit = re.search(GIT + r"commit\b" + SEG, stmt)
    push = re.search(GIT + r"push\b" + SEG, stmt)
    add = re.search(GIT + r"add\b" + SEG, stmt)

    if push and re.search(r"(\s-f\b|--force)", push.group(0)):
        out("deny", "git push --force is not allowed. Push a new commit instead.")
    if (commit or push) and "--no-verify" in stmt:
        out("deny", "--no-verify is not allowed.")
    if push:
        raw = push.group(0).split()[push.group(0).split().index("push") + 1:]
        toks = [t for i, t in enumerate(raw) if not t.startswith("-") and (i == 0 or raw[i - 1] not in ("-o", "--push-option", "--receive-pack", "--repo"))]
        refspec = toks[1] if len(toks) > 1 else ""
        if br is None:
            br = git(d, "branch", "--show-current")
        target = refspec.strip("\"'").rsplit(":", 1)[-1].removeprefix("refs/heads/") if refspec else br
        if target in PROTECTED:
            out("deny", f"Refusing to push to protected branch '{target}'. Push a feature branch and open an MR/PR.")
    if commit:
        if br is None:
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


def cla_fork(remotes):
    """A clone of only your fork has no Kubernetes remote, so ask GitHub for each fork's parent."""
    for repo in set(re.findall(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s", remotes)):
        try:
            parent = subprocess.run(["gh", "api", f"repos/{repo}", "--jq", ".parent.full_name // empty"],
                                    capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            continue
        if CLA_REMOTE.search(f"github.com/{parent}"):
            return True
    return False


def cla_guard(stmt, d, raw):
    commit = re.search(GIT + r"commit\b", stmt)
    push = re.search(GIT + r"push\b", stmt)
    if not (commit or push):
        return
    # A commit's message can sit in a heredoc, so read the raw command. A push checks every
    # commit not yet on a remote, which also catches trailers added by other tools.
    msg = raw if commit else git(d, "log", "--format=%B", "HEAD", "--not", "--remotes")
    if not TRAILER.search(msg):
        return
    remotes = git(d, "remote", "-v")
    if CLA_REMOTE.search(remotes) or (push and cla_fork(remotes)):
        out("deny", "EasyCLA rejects Co-Authored-By trailers it cannot match to a CLA signer. "
                    "Remove the trailer (keep Signed-off-by).")


def rm_guard(stmt, d):
    for m in re.finditer(r"\brm\s+((?:-\w+\s+|--recursive\s+|--force\s+)+)(" + SEG + ")", stmt):
        flags = m.group(1)  # flags only; paths like alert-relay/ contain a bare "-r"
        if not (re.search(r"-\w*r|--recursive", flags) and re.search(r"-\w*f|--force", flags)):
            continue
        for t in m.group(2).split():
            if t.startswith("-"):
                continue
            t = t.strip("\"'")
            if "$" in t:
                out("ask", f"rm -rf on a variable path ({t}); confirm.")
            # The shell expands braces, substitutions, subshells and ~-/~+ into paths
            # this check never sees (a decoy tmp/ in {~,a/tmp/b} would pass), so ask.
            if re.search(r"[{}()<>`]", t) or ("~" in t and t != "~" and not t.startswith("~/")):
                out("ask", f"rm -rf on a path the shell rewrites ({t}); confirm.")
            p = os.path.normpath(os.path.join(d, os.path.expanduser(t)))
            # Inside a tmp/ under $HOME is project scratch, but only for plain path
            # tokens (anything else may be rewritten by the shell), judged on the real
            # path so a pre-existing symlinked or decoy tmp segment cannot widen it
            # (resolve the full path: a trailing symlink with "/" deletes its target's
            # contents). tmp itself, /tmp, /var/tmp and paths outside $HOME stay guarded.
            # Resolve only plain tokens under $HOME: realpath can stall on a hung mount
            # or raise on odd input, and either would fail the hook open.
            in_tmp = False
            if re.fullmatch(r"(~/)?[\w.@+/-]*\*?", t) and p.startswith(os.path.expanduser("~") + os.sep):
                try:
                    home = os.path.realpath(os.path.expanduser("~")) + os.sep
                    real = os.path.realpath(p)
                    in_tmp = real.startswith(home) and "tmp" in real[len(home):].split(os.sep)[:-1]
                except (OSError, ValueError):
                    in_tmp = False
            if not (p.startswith(SAFE_RM_PREFIXES) or "/worktrees/" in p or in_tmp):
                out("ask", f"rm -rf outside scratchpad/worktrees: {p}")


LOCAL_RULES = os.path.expanduser("~/.claude/hooks/guard_local.py")
_local = None


def local(hook, *args):
    """Private rules from ~/.claude/hooks/guard_local.py, if present. It may define
    tool(name, inp), command(cmd, raw) and statement(stmt, d), each returning
    (decision, reason) or None. It may `import guard` for git(), SEG, GIT."""
    global _local
    if _local is None:
        _local = False
        if os.path.isfile(LOCAL_RULES):
            import importlib.util
            spec = importlib.util.spec_from_file_location("guard_local", LOCAL_RULES)
            _local = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_local)
    fn = getattr(_local, hook, None) if _local else None
    r = fn(*args) if fn else None
    if r:
        out(*r)


def bash(cmd, cwd):
    raw = cmd
    cmd = strip_heredocs(cmd)  # heredoc bodies are data, not commands
    local("command", cmd, raw)
    if "kubectl" in cmd:
        kubectl_guard(cmd)
    for stmt, d, br in statements(cmd, cwd):
        local("statement", stmt, d)
        git_guard(stmt, d, br)
        cla_guard(stmt, d, raw)
        rm_guard(stmt, d)

        # GitLab only: team repos. GitHub PRs here are personal repos, merged on request.
        if re.search(r"glab\s+mr\s+merge\b", stmt) or re.search(r"glab\s+api\b" + SEG + r"merge_requests/\d+/merge\b", stmt):
            out("ask", "Merging is a human decision. Confirm this merge.")

        if re.search(r"glab\s+api\b" + SEG + r"(?:--method|-X)\s*(?:PUT|POST)\b", stmt) and "--input" in stmt \
                and not re.search(r"content-type", stmt, re.I):
            out("deny", "glab api PUT/POST --input returns HTTP 415 (exit 0!) without --header \"Content-Type: application/json\". Add the header.")


def main():
    try:
        h = json.load(sys.stdin)
    except Exception:
        return
    tool, inp = h.get("tool_name", ""), h.get("tool_input") or {}
    local("tool", tool, inp)
    if tool == "Bash":
        bash(inp.get("command", ""), h.get("cwd") or os.getcwd())


if __name__ == "__main__":
    main()
