---
name: medium-post
description: Use when publishing, drafting, or updating a Medium post/article/story from markdown, or when Medium blocks automation (Cloudflare "Attention Required", "you have been blocked", publish limit errors)
---

# Publishing to Medium

## Overview

Medium has no usable API (integration tokens discontinued) and hard-blocks CDP-driven browsers. The ONLY working automation path is the Claude-in-Chrome extension inside the user's normal browser, logged into Medium.

## Preconditions

1. Chrome extension connected (`tabs_context_mcp` succeeds). If not, ask user to install/connect claude.ai/chrome.
2. User logged into Medium in that Chrome. If medium.com/new-story shows "Welcome back" sign-in, ask user to log in — never do it for them.
3. Do NOT try agent-browser/CDP/headless — Medium's Cloudflare returns "Sorry, you have been blocked" regardless of headed/headless/real profile. Don't attempt to evade.

## Content rules (markdown → Medium)

- No tables — Medium doesn't render them. Convert to bullets before publishing.
- The document's own top-level `# H1` is the Medium title — strip it from the body, or it duplicates as title + first heading.
- Convert body to HTML: `<h1>` for sections, `<p>`, `<ul><li>`, `<strong>`, `<em>`, `<code>`. Medium normalizes on paste.

## Publish flow

1. New tab → `https://medium.com/new-story`, wait 4s.
2. Click title area, type the title. Body markdown typed as text does NOT convert — inject via synthetic paste with javascript_tool:
   ```js
   const dt = new DataTransfer();
   dt.setData('text/html', html);
   dt.setData('text/plain', 'x');
   document.activeElement.dispatchEvent(new ClipboardEvent('paste',
     {clipboardData: dt, bubbles: true, cancelable: true}));
   ```
3. **Verify the title survived**: screenshot and check the Title line isn't empty — the paste can silently eat it. If empty, click the title line and retype.
4. Click Publish (top right) → dialog opens. In the dialog:
   - Uncheck "Paywall this story" if free post wanted (defaults checked). Zoom to verify the checkbox actually toggled — clicks miss.
   - Topics: type a word, WAIT for the suggestion dropdown, CLICK a suggestion. Commas and Enter as key events do NOT tokenize (comma types a literal comma character). Only dropdown clicks work. Skip topics if dropdown misbehaves — they can be added post-publish via story ⋯ menu → Change topics.
5. Click Publish. Confirm via tab URL flipping to `<user>.medium.com/<slug>` (screenshot may fail there — subdomain lacks extension permission; that's success, not an error).

## Post-publish edits

Edit URL: `medium.com/p/<id>/edit` (stays on medium.com, permissions OK). The ⋯ menu there has: Manage paywall setting, Change topics.

## Known limits

| Symptom | Meaning |
|---|---|
| "maximum of two stories in the past 24 hours" | Account rate limit. Draft is saved; publish later. |
| Screenshot "Permission denied for this action on this domain" | Extension lacks per-site permission (e.g. user subdomain). Not fatal. |
| Tag field shows "Tags only support letters..." | You typed commas as text. Use suggestion clicks. |
