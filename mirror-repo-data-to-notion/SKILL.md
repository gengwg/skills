---
name: mirror-repo-data-to-notion
description: Use when mirroring git-managed structured data (inventory YAML, cluster lists, directories) into Notion for browsing/sharing, when deciding between a Notion database and a page, or when a Notion mirror has drifted from its source of truth
---

# Mirroring Repo Data into Notion

## Overview

Git stays the source of truth; Notion is a derived, human-browsable mirror. The design problem is not the copy — it's making drift detectable and the derivation obvious, so nobody edits the mirror thinking it's authoritative.

## Database vs page

- **Database** when the data is rows with attributes (an inventory: one row per item, columns for status/location/owner). You get filtering, sorting, per-row properties, and per-row updates on later syncs.
- **Page** when it's prose or a small table nobody will query. Cheaper, but every update is a rewrite.

If you'll ever ask "which rows have X?", it's a database.

## Mark the mirror as derived

Every mirror gets, at the top (page) or in the database description:

1. **"Derived from `<repo path>` — do not edit here; edit the source and re-sync."**
2. **The source commit hash** (and date) the mirror was built from. This is the drift detector: `git log -1 --format=%h -- <source file>` vs the stamp answers "is this stale?" in one comparison.

Without the stamp, "is this page current?" requires diffing every row against the source.

## Sync rules

- Map source fields → database properties once, then keep the mapping stable; renaming properties orphans old rows' values.
- Sync = upsert by a stable key (name/ID column), not delete-and-recreate — recreating rows breaks any links people made to them.
- Rows removed from the source: mark them (`status: removed`) rather than deleting, at least one cycle — someone may be linking to them.
- Update the commit stamp in the same write as the rows. A stamp updated without the rows (or vice versa) lies.

## The audit pass

Periodically (or when someone asks "is this page right?"):

1. Compare the stamped commit to the source file's current commit. Same → done.
2. If behind: diff the source between the two commits, apply the delta to the mirror, update the stamp.
3. Flag rows edited by hand in Notion (values that match neither commit) back to the team — that's someone treating the mirror as the source; the edit needs to move to git.

## Common mistakes

- No commit stamp — staleness becomes unknowable without a full diff.
- Delete-and-recreate syncs — breaks inbound links and loses manual annotations.
- Editing the Notion mirror directly "because it's faster" — the next sync silently reverts it.
- Mirroring data that changes hourly — a mirror is for slow-moving reference data; fast-moving state belongs in a dashboard reading the live source.
