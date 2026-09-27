---
name: slack-feedback-to-issues
description: Turn bug reports in a Slack feedback channel into GitLab issues without duplicates, confirming each one with the user, then keep watching the channel for new reports. Use when asked to "file issues from the feedback channel", "triage Slack bug reports", "make sure every report in #channel has a ticket", or to watch a channel and ticket new reports.
---

# Skill: slack-feedback-to-issues

## Purpose

Every bug report posted in a Slack feedback channel should end up as exactly one GitLab issue that links back to the thread. The user decides what deserves a ticket; the agent does the searching, matching and drafting.

Needs read access to Slack (a Slack connector or API) and `glab` authenticated for the GitLab project.

## Inputs

Ask for anything missing:

- The Slack channel URL or ID.
- The GitLab project (`group/project`).
- The label used for these reports, if the user knows it. Treat a guessed label as a hint, not a fact; step 2 verifies it.

## Procedure

### 1. Read the channel newest first

Read top-level messages from newest to oldest. Recent reports are the ones least likely to have an issue already, so this front-loads the useful work. For each thread, read the replies too: a later reply often says "fixed", "duplicate of" or links an issue.

Skip messages that are not bug reports (questions, announcements, thanks). Say which ones you skipped and why.

### 2. Learn the project's conventions

Before drafting anything, look at a few existing issues filed from this channel:

```sh
glab issue list -R <group/project> --label "<label>" --per-page 10
glab issue view <N> -R <group/project>
```

Copy their title style, description layout and labels. If the label the user named returns nothing, list the project's labels (`glab label list -R <group/project>`) and find the real one before continuing.

### 3. Check for an existing issue

For each report, search open and closed issues by the key terms (error message, feature, component):

```sh
glab issue list -R <group/project> --search "<terms>" --all
```

Also search for the Slack thread URL itself, since an issue that already links the thread is a certain match.

- **Match found:** skip it, and note which issue covers it.
- **Several Slack threads, one bug:** file one issue and add the other thread links to it in a comment. Never file a second issue for the same bug.
- **Unsure:** show the user both and ask.

### 4. Confirm, then create

For each report that needs an issue, show the user the Slack link, a one-line summary, the draft title, the labels, and any near-matches you found. Create it only after the user says yes to that specific issue. A yes for one is not a yes for the rest.

```sh
glab issue create -R <group/project> --title "<title>" --label "<label>" --description "<body with Slack thread link>"
```

Then reply with the issue URL.

### 5. Watch for new reports

Once the backlog is done, check the channel on an interval (every 30 minutes by default) and handle new threads the same way, confirmation included.

Save state between checks so old messages are not re-read: the timestamp of the newest message processed, plus a map of thread to issue. Keep it in a small file in the workspace (e.g. `tmp/slack-feedback-state.json`). On each check, read only messages newer than the saved timestamp, then update it.

Stop watching when the user says so, and say that you stopped.

## Traps

- **Replies change the picture.** A thread that looks like a new bug may already say "tracked in #123" three replies down. Read the whole thread before searching.
- **Closed issues count.** A closed issue for the same bug means either it regressed (comment on it or reference it) or it is already fixed. Ask; don't silently file a new one.
- **Don't copy private data blindly.** Slack threads can contain tokens, customer names or internal hostnames. If the project is public, summarize instead of pasting.
