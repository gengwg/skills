---
name: slack-feedback-to-issues
description: Turn bug reports in a Slack feedback channel into GitLab issues without duplicates, confirming each one with the user, then keep watching the channel for new reports. Use when asked to "file issues from the feedback channel", "triage Slack bug reports", "make sure every report in #channel has a ticket", to watch a channel and ticket new reports, or to set up or fix a scheduled bot that does this.
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
- **Interactive or scheduled.** Interactive (the default) means the user is present and confirms each issue. A scheduled run (a daily job, an unattended bot) has nobody to confirm with. There, file directly only if the person who set up the job explicitly said to; otherwise post the drafts for a human to file.

## Procedure

### 0. Check GitLab access first

```sh
glab auth status
glab issue list -R <group/project> -P 1
```

Do this before reading Slack, so a broken token is found in seconds rather than after drafting every issue. Never print the token (no `glab auth status -t`).

If access is broken, still do steps 1 to 3 and post the drafts, but lead the post with the blocker and name who can fix it. On a scheduled job, don't repeat an identical blocker note run after run; say how many runs in a row it has failed, so the gap is visible.

### 1. Read the channel newest first

Read top-level messages from newest to oldest. Recent reports are the ones least likely to have an issue already, so this front-loads the useful work. For each thread, read the replies too: a later reply often says "fixed", "duplicate of" or links an issue.

Feedback often arrives as separate top-level messages, not threads: one person posts an idea, others add to it over the next few days. Group messages about the same request into one issue and list each message link as an origin. Keep related-but-different items as separate issues that link to each other.

Skip messages that are not bug reports or feature requests (questions, announcements, thanks). Say which ones you skipped and why.

### 2. Learn the project's conventions

Before drafting anything, look at a few existing issues filed from this channel:

```sh
glab issue list -R <group/project> --label "<label>" --per-page 10
glab issue view <N> -R <group/project>
```

Copy their title style, description layout and labels. If the label the user named returns nothing, list the project's labels (`glab label list -R <group/project>`) and find the real one before continuing.

Projects often split feedback into a bug label and a feature label, and may also have an intake label (e.g. `triage`) that puts new issues in front of whoever plans the work. Pick the bug or feature label per item, and add the intake label if the user or the job's instructions asked for it.

### 3. Check for an existing issue

For each report, search open and closed issues by the key terms (error message, feature, component):

```sh
glab issue list -R <group/project> --search "<terms>" --all
```

Also search for the Slack thread URL itself, since an issue that already links the thread is a certain match. Don't rely on that alone: people file issues by hand from the same feedback, often without the Slack link or the usual labels, so a title search is still needed.

- **Match found:** skip it, and note which issue covers it.
- **Several Slack threads, one bug:** file one issue and add the other thread links to it in a comment. Never file a second issue for the same bug.
- **Unsure:** show the user both and ask.

### 4. Confirm, then create

For each report that needs an issue, show the user the Slack link, a one-line summary, the draft title, the labels, and any near-matches you found. Create it only after the user says yes to that specific issue. A yes for one is not a yes for the rest. In a scheduled run, apply the rule from Inputs instead: file only with explicit standing permission, otherwise post the draft.

```sh
glab issue create -R <group/project> --title "<title>" --label "<label>" --description "<body with Slack thread link>"
```

Then reply with the issue URL.

End each run with one summary in the channel (a thread under the run's first message keeps the channel quiet): the new items found, the issues filed with links, the duplicates skipped and which issue covers them, and any drafts still waiting for a human.

### 5. Watch for new reports

Once the backlog is done, check the channel on an interval (every 30 minutes by default) and handle new threads the same way, confirmation included.

Save state between checks so old messages are not re-read: the timestamp of the newest message processed, plus a map of thread to issue. Keep it in a small file in the workspace (e.g. `tmp/slack-feedback-state.json`). On each check, read only messages newer than the saved timestamp, then update it.

Stop watching when the user says so, and say that you stopped.

## Traps

- **Replies change the picture.** A thread that looks like a new bug may already say "tracked in #123" three replies down. Read the whole thread before searching.
- **Closed issues count.** A closed issue for the same bug means either it regressed (comment on it or reference it) or it is already fixed. Ask; don't silently file a new one.
- **Don't copy private data blindly.** Slack threads can contain tokens, customer names or internal hostnames. If the project is public, summarize instead of pasting.
