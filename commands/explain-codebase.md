---
description: Explain a codebase to a newcomer — structure, what matters, what to read next
argument-hint: [path or subsystem, defaults to the whole repo]
---

Explain this codebase to a newcomer. Scope: $ARGUMENTS (empty means the whole
repository).

Read before answering: the README, the dependency/build manifest, the entry
points, and the directory layout. Where the docs and the code disagree, the
code wins — say so.

Cover:

- **Structure** — what lives where, and what each directory is responsible for.
- **What matters** — the few files, types, or conventions a newcomer breaks
  things by not knowing. Cite them as `path:line`.
- **How it runs** — entry point to output, plus the build, test, and run
  commands that actually exist here.
- **What to read next** — a short ordered list, easiest first.

Keep it to what you verified in the repo. Name what you could not work out
rather than filling it in.
