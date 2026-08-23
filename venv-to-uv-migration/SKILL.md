---
name: venv-to-uv-migration
description: Use when migrating a Python-tooling repo from venv+pip to uv, when a venv lands on an unsupported interpreter (OS Python newer than the tooling's ceiling), or when deciding between a uv-built .venv and fully stateless `uv run`
---

# Migrating a Repo from venv to uv

## Overview

Two distinct migrations hide under "switch to uv": replacing the *tooling* that builds a persistent venv, and deleting the persistent venv entirely in favor of stateless `uv run`. They fix different problems; pick deliberately.

## Why move off `python -m venv` + pip at all

- **Interpreter drift**: the OS ships a Python newer than your tooling supports (e.g. ansible-core 2.18's controller ceiling is 3.13; newer distros ship 3.14). `python3 -m venv` silently lands on the unsupported one. `.python-version` + `uv python install` pins the interpreter, downloaded into `~/.local` — no apt, no sudo.
- **PEP 668**: modern distros block system-wide `pip install` anyway.
- Machines without `python3-venv` and without sudo stop being blockers.

## The two end states

**uv-built persistent `.venv`** — same activation workflow, faster and interpreter-pinned. Right for team repos with mixed tooling habits (discoverability: people expect a venv). Traps:
- `uv venv` refuses to replace an existing venv without `--clear` — a stale wrong-interpreter venv survives a "rebuild".
- `uv pip sync` can silently drop packages the requirements imply; prefer `uv pip install -r`.

**Fully stateless `uv run`** — no venv at all:

```sh
uv run --with-requirements path/to/requirements.txt -- <tool> ...
```

This deletes an entire failure *class*, not a step: "activation doesn't stick in non-interactive shells", "bare `venv/bin/...` relative paths break after `cd`", "stale venv survived a rebuild" all exist because a persistent venv is state, and state drifts. Stateless runs re-enforce the pins on every invocation. Right for solo-maintained or agent-driven repos. Costs to record: the incantation is long (a local alias helps, docs still carry it); first run on a fresh machine downloads ~100MB with no explicit setup step; uv itself becomes a hard dependency.

## When the pins live in a submodule

Don't create a root `pyproject.toml`/`uv.lock` that mirrors a submodule's `requirements.txt` — that's a second source of truth that drifts on every submodule bump. `--with-requirements <submodule>/requirements.txt` keeps the submodule authoritative. A Makefile target that just runs the incantation once serves as cache pre-warm ("setup").

## Project resolution — check for hijack

`uv run` walks up from the cwd to the nearest `pyproject.toml`/`.python-version`. Two consequences to verify, not assume:

- A subdir *without* project files inherits the repo root's pin — good.
- A subdir *with* its own `pyproject.toml` makes `uv run` sync **that** project instead — if you invoke from inside vendored/submodule dirs, confirm they carry no project files, or pass `--no-project` (there is no project to point `--project` at in the stateless design).

## Migration mechanics

1. **Pin the interpreter first** — create `.python-version` at the repo root with the highest Python your pinned tooling supports (read the tool's support matrix, not the OS default). This, not the uv swap, is what fixes the wrong-interpreter crash: without a pin, `uv run` happily resolves the same system Python that was broken before. The pin's value derives from the pinned requirements, so re-check it on every submodule/requirements bump — it's the one piece of duplicated truth you can't avoid.
2. **Then substitute invocations.** The riskiest edits are the mechanical substitutions in docs and scripts, specifically **command-substitution contexts** — `VAR=$(venv/bin/tool ...)`, `for h in $(...)` — where quoting and line continuations must survive the longer replacement. Spot-check every one.
3. **Anchor the requirements path per invocation directory.** `--with-requirements` is cwd-relative: docs that say "cd into `<subdir>/` first" need `requirements.txt`, scripts running from the root need `<subdir>/requirements.txt`, and agent docs are safest with an explicit `"$REPO_ROOT/<subdir>/requirements.txt"`. Write the form that matches where each doc tells the reader to stand.
4. Keep `venv/` entries in `.gitignore` and linter excludes: stale venv dirs on operator machines should stay ignored, not resurface as lint noise.
5. Leave CI-image flows that install via pip alone if the image drives them, and leave historical records/logs untouched — migrate invocations, not history.

## Verify before calling it done

- `uv run ... --version` from **each directory the docs tell people to run from**: right tool version, right Python. For cwd-sensitive tools (ansible: `config file = ...` in `ansible --version` output) confirm the config resolution still lands on the intended file — this is the load-bearing check.
- Syntax-check / dry-run one real workload per invocation directory (e.g. `ansible-playbook --syntax-check` against a real inventory).
- `bash -n` and lint every script you edited.

## Common mistakes

- "Rebuilding" a venv with `uv venv` and keeping the old interpreter — missing `--clear`.
- Duplicating submodule pins into a root lock file.
- Replacing 40 invocation sites and only testing one — the breakage hides in `$(...)` quoting.
- Testing only from the repo root when the runbooks say to run from a subdir.
- Framing the choice as venv vs uv — uv can build the venv; the real choice is persistent state vs stateless runs.
- Swapping invocations to `uv run` without creating `.python-version` — the wrong-interpreter crash survives the migration intact.
