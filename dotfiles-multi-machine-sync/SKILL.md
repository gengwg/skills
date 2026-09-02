---
name: dotfiles-multi-machine-sync
description: Use when setting up a dotfiles repo, syncing shell/editor/ssh config across machines, migrating a legacy config repo to symlinked dotfiles, or when a second machine's first pull collides with existing files
---

# Dotfiles Across Machines

## Overview

One git repo, symlinked into place by an idempotent installer. The installer — not the docs — encodes every machine-specific decision, so a new machine is `git clone && ./install.sh && exec zsh`.

## Installer rules (the core)

Write `install.sh` with a single `link src dst` helper and these behaviors:

1. **Never overwrite**: an existing regular file moves to `<name>.orig`, never deleted.
   ```bash
   link() {
     local src=$repo/$1 dst=$2
     mkdir -p "$(dirname "$dst")"
     if [[ -L $dst ]]; then
       [[ $(readlink -f "$dst") == "$src" ]] && { echo "ok $dst"; return; }
       rm "$dst"
     elif [[ -e $dst ]]; then
       mv "$dst" "$dst.orig"; echo "backup $dst -> $dst.orig"
     fi
     ln -s "$src" "$dst"; echo "linked $dst -> $src"
   }
   ```
2. **Idempotent**: re-running prints `ok` lines and changes nothing. Re-run after moving the repo.
3. **Opt-in for machine-local files**: some files legitimately differ per machine (`~/.ssh/config`). Skip them if a real file exists; adopting the repo copy is an explicit act (`rm ~/.ssh/config && ./install.sh`), never automatic. This must be in place BEFORE running the installer on a second machine. In code — a guard before `link`, not a `link` variant:
   ```bash
   if [[ -e $HOME/.ssh/config && ! -L $HOME/.ssh/config ]]; then
     echo "skipped $HOME/.ssh/config (machine-local -- rm it to adopt the repo copy)"
   else
     link ssh/config "$HOME/.ssh/config"
   fi
   ```
4. **Copy, don't symlink, when the consumer requires a real file** — e.g. syncthing reads `.stignore` from the folder root and doesn't sync it; each machine needs its own copy. A wrong/missing ignore rule syncs exactly what it was meant to exclude.
5. **Fix permissions the tool demands**: ssh refuses group-writable config; repo umask checks files out 664 → `chmod 600` after linking. Same idea for `~/.ssh` (700).
6. **Alias files point at the installed sibling, not the repo**: e.g. `CLAUDE.md -> ~/.claude/AGENTS.md` (one copy of content, ever).

## Secrets and machine-local config

Never commit secrets. Ship `*.example` templates (`secrets.zsh.example`, `zshrc.local.example`) that the real zshrc sources if present:
```zsh
[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
```

## Second-machine adoption order

1. Commit + push from machine 1.
2. On machine 2: `git clone` (a plain `git pull` into a dir with untracked files collides — clone fresh or `git stash -u` first).
3. Run `./install.sh`, read the `backup`/`skipped` lines — they are the diff between machines.
4. `exec zsh`; diff any `.orig` files for local bits worth folding back into the repo.

## Extras that pay off

- **SSH-aware prompt**: a prompt segment showing `user@host` only over SSH makes remote shells visually distinct. Tune it down if too loud.
- **SSH key hygiene while you're there**: list keys per machine, retire unused ones, one key per machine rather than one key everywhere.
- **PATH dedup**: `typeset -U path` in zsh kills duplicate entries from re-sourced configs.

## Common mistakes

- Running the installer on machine 2 before the opt-in rule exists — it clobbers machine-local ssh config.
- Symlinking a file the consuming tool must own as a real file (syncthing `.stignore`).
- **Replacing a real directory with a symlink *inside* a Syncthing-replicated folder.** Syncthing does not track symlinks, so the swap reads as a deletion and propagates — the other machine loses the content. Tempting when a subtree is also a git clone and you want one copy instead of two; don't. Check `syncthing/config.xml` for the folder paths first, and confirm with `curl -H "X-API-Key: $KEY" 'localhost:8384/rest/db/status?folder=<id>'` — a non-zero `globalDeleted` right after the change is the tell. Recovery is to restore the real directories; sync re-adds them.
- Editing `~/.zshrc` directly on one machine "just for now" — it's a symlink; the change is already in the repo working tree. Commit or revert, don't fork.
