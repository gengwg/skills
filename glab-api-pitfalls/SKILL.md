---
name: glab-api-pitfalls
description: Use when scripting GitLab writes with the glab CLI (glab api PUT/POST, glab mr update/close/note, glab issue update) from an agent or CI shell, especially when sending a body from a file, when the shell cwd is a different repo than the target, when citing MRs or issues across projects, or when a glab command hangs or returns success but the change did not land.
---

# Skill: glab-api-pitfalls

## Purpose

Every trap here is a write that exits 0 and does the wrong thing: a literal
`@file` string stored as a description, a description blanked by an empty
substitution, a note posted on the same-numbered MR in another repo, a
cross-project reference linking a stranger's MR. None of them fail loudly.
Treat every glab write as unverified until a read-back shows the intended
content on the intended object.

## 1. `-f key=@file` sends the literal string

`-f` is `--raw-field`: a plain string. `-F` (`--field`) is the one that
reads `@file` (and infers JSON types). Checked on glab 1.115 with
`GLAB_DEBUG_HTTP=1`: `-f search=@f` sent `search=%40%2Fpath`, `-F` sent the
file's content. The response echoes the bad body, so
the only symptom is a description that now reads `@/path/to/file`.

```bash
glab api -X PUT "projects/<group>%2F<project>/merge_requests/<iid>" -F description=@body.md
```

`-F` also type-infers values that look like JSON, numbers or booleans. Whether
that reaches file contents in a JSON body is unverified, so for a body that
starts with `[` or `{`, or for several fields at once, build the JSON with jq
and send it whole:

```bash
jq -n --rawfile b body.md '{description:$b}' > req.json
glab api -X PUT "projects/<enc>/merge_requests/<iid>" -H 'Content-Type: application/json' --input req.json
```

## 2. An empty `$(cat file)` wipes the field

`-f "description=$(cat "$FILE")"` after the step that should have written
`$FILE` failed sends `description=` and GitLab accepts it. `&&` chains stop
at the first failure; a PUT on its own line still runs. Guard the write on
the file having content, and avoid `$TMPDIR`, which can be unset and resolve
`$TMPDIR/x` to `/x`:

```bash
[ -s "$FILE" ] && glab api -X PUT ... -F description=@"$FILE"
```

## 3. The project comes from the shell's cwd

`:fullpath`, `glab mr close N`, `glab mr update N`, `glab mr note N` and
friends resolve the project from the git remote of the current directory.
In an agent shell the cwd persists between calls, so one `cd other-repo &&`
retargets every later command. MR and issue numbers overlap across repos, so
the wrong-repo call usually succeeds against a real, unrelated MR.

Always name the project. Use `-R group/project` on subcommands and the
URL-encoded path (`group%2Fproject`) in `glab api` paths. Never use
`:fullpath` from a shell whose cwd you did not set in the same command.

## 4. Bare `!NNN` and `#NNN` in text resolve against the host project

Writing "deploy-tools !471" inside an issue of the `infra` project links
infra!471. The prose word is invisible to the parser, and the Related MRs
panel still looks populated. Write the full reference across projects:
`group/subgroup/project!471`. Verify with
`glab api "projects/<enc>/issues/<iid>/related_merge_requests"` and read
`references.full` on each row. The `mentioned in` system notes on the wrong
MRs cannot be deleted afterwards, so get it right in the first save.

## 5. Save the old value, then read back after every write

```bash
glab api "projects/<enc>/merge_requests/<iid>" | jq -r .description > old.md   # before
glab api "projects/<enc>/merge_requests/<iid>" | jq -r .description | diff - body.md   # after
glab api "projects/<enc>/merge_requests/<iid>" | jq -r '[.state, .merge_commit_sha] | @tsv'
```

Diff the whole body against the source; a truncated read-back cannot show
that eighty lines landed. Expect at most a trailing-newline difference.

`state=opened` with `merge_when_pipeline_succeeds=true` is not merged; a
later push or conflict cancels the auto-merge and glab does not say so. Want
`state=merged` with a real `merge_commit_sha`.

## 6. Non-TTY behaviour

Observed from an agent shell (glab 1.1xx):

| Command | Non-TTY | Workaround |
|---|---|---|
| `glab mr create` | hangs | wrap in `timeout`, then confirm with `glab mr list -R ...` |
| `glab ci view`, `glab ci status -b` | need a TTY | `glab ci list -R ...` |
| `glab api -X POST/PUT` | can hang on the response | add `--silent`, then read back |
| `glab mr view --comments` | works, incomplete | `glab api .../discussions` for full threads |

A write that hung may still have landed: read back before retrying, or the
retry posts a duplicate note. Sandboxed shells can also kill glab outright (`apply-seccomp ... Permission
denied`); a poll loop built on it then reports nothing rather than failing.

## Common mistakes

- `-f` where `-F` or `--input` was meant.
- Writing a description from a substitution without `[ -s "$FILE" ]`.
- Relying on cwd for the project; trusting that `!364` exists means it is
  the right `!364`.
- Citing another project's MR by bare number.
- Taking exit 0 or the echoed response as proof; read the object back.
