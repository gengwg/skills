---
name: slack-mcp-drafting-pitfalls
description: Use when writing a Slack message, reply, or file upload for someone through a Slack MCP connector, including "put it in Slack", "reply in the thread", "ping X", or anything aimed at an externally shared (Slack Connect) channel. Also when a Slack draft, mention, reaction or upload fails or does nothing.
---

# Slack MCP Drafting Pitfalls

## Overview

A message in Slack goes out under the person's name and cannot be pulled back through the connector. Draft it, get every detail right the first time, and expect shared channels to block more than they allow.

## Rules

1. **Draft, don't send.** "Put it in Slack", "reply there", "ping her" all mean a draft in the target channel or thread. Send only when the person says "send" or "post" after seeing the draft.
2. **Look up every mention.** Resolve each person with a user search and write `<@USERID>` from the result. Never guess or reuse an ID from memory. A display name that matches two people needs the person to pick.
3. **One shot per channel.** The draft tool keeps one attached draft per channel and cannot edit it. A second draft fails (`draft_already_exists` / `attached_draft_exists`), or returns success with no `draft_id` and creates nothing. Treat a response without a `draft_id` as a failure. To fix a draft, tell the person what to change by hand, or ask them to delete it and draft again.
4. **Keep the text in a local file** before drafting, so "I deleted it, redraft" is a copy, not a rewrite.

## Slack Connect (externally shared) channels

| Action | Through the connector |
|---|---|
| Draft | Works |
| Send a message | Blocked: `mcp_externally_shared_channel_restricted` |
| Add a reaction | Blocked, same error |
| Attach `.gz` (and some other types) | Rejected: "Files of this type can't be shared in conversations using Slack Connect" |

So a workflow triggered by a reaction (an emoji that opens a ticket on the other side) needs the person to click it. Say so and link the message. Ship logs as plain text or a `.txt` file, or through the other company's portal.

## Common mistakes

- Sending because the request said "put it in Slack".
- Typing a mention from memory, then having to redraft because it tagged the wrong person.
- Calling a draft created when the response had no `draft_id`.
- Retrying a reaction or send in a shared channel instead of handing that step to the person.
- Attaching a compressed archive in a shared channel.
