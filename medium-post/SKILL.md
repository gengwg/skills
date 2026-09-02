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
2. Click the title line, type the title, then press **Enter** to move into the body. Pasting while focus is still on the title merges the whole article into the title line.
3. Body markdown typed as text does NOT convert — inject via synthetic paste with javascript_tool:
   ```js
   const dt = new DataTransfer();
   dt.setData('text/html', html);
   dt.setData('text/plain', 'x');
   document.activeElement.dispatchEvent(new ClipboardEvent('paste',
     {clipboardData: dt, bubbles: true, cancelable: true}));
   ```
   **The OS clipboard is not a shortcut here.** Loading the HTML with
   `xclip -t text/html` and sending `ctrl+v` does nothing: CDP-dispatched key
   events don't invoke Chrome's paste command. Synthetic `ClipboardEvent` is the
   only way in. Click into the body first and confirm
   `document.activeElement.className` contains `postArticle-content` — the
   dispatch silently no-ops against the wrong element.

   For anything over ~2KB, don't hand-transcribe the HTML into the JS string.
   Have a script emit pre-escaped `window.__h = "..."` / `window.__h += "..."`
   chunks, paste each verbatim, then dispatch using `window.__h`. Each call
   returns the running length, so compare the total against the source before
   dispatching. Note the source's *character* count, not `wc -c` — em dashes and
   other non-ASCII make bytes exceed characters.
4. **Verify the title survived**: `ctrl+Home`, screenshot, check the Title line holds only the title. If the paste ate or merged it, `ctrl+a` + Delete and redo from step 2.
5. Click Publish (top right). **The first click after page load often doesn't register** — if no dialog, click once more (don't double-click; that opens then closes it). In the dialog set "Paywall this story" (defaults checked) and zoom to verify the toggle took — clicks on it miss often. **Skip topics here** — see below.
6. Click Publish. Confirm via tab URL flipping to `<user>.medium.com/<slug>` (screenshot may fail there — subdomain lacks extension permission; that's success, not an error).

## Topics — always add them after publishing

The topic field **in the publish dialog is broken for automation**: suggestions appear, but clicking one (by coordinate or element ref) leaves the field empty and no chip is created. Commas and Enter don't tokenize either (a comma types the word "comma"). Don't fight it — publish without topics.

The post-publish editor's own topic UI works reliably. Go to `medium.com/p/<id>/edit` → ⋯ menu → **Change topics**, then per topic: click "Add a topic…", type, wait for the dropdown, click the suggestion — a chip appears immediately. Repeat up to 5, then click **Save**. (This popover has a Save button; the publish dialog's field does not.)

Match the suggestion that actually exists rather than the label you had in mind — e.g. there is no "AI Agents" topic, and "Note Taking" resolves to `Notetaking`.

## Post-publish edits

Edit URL: `medium.com/p/<id>/edit` (stays on medium.com, permissions OK). The ⋯ menu there has: Manage paywall setting, Change topics, Change display title/subtitle, Manage unlisted setting.

## Known limits

| Symptom | Meaning |
|---|---|
| "maximum of two stories in the past 24 hours" | Account rate limit, rolling window. Draft is saved; publish later. |
| Same error when using "Schedule for later" | Scheduling counts against the quota **when you schedule**, not on the target date. It is not a way around the cap — wait for the oldest publish to age out. |
| Screenshot "Permission denied for this action on this domain" | Extension lacks per-site permission (e.g. user subdomain). Not fatal. |
| Screenshot "CDP sendCommand Page.captureScreenshot timed out" | Renderer is stalled, usually right after the editor loads. **Input sent during the stall is lost** — a title typed then is silently gone. Wait 3s, re-screenshot, and redo the step rather than assuming it landed. |
| Tag field shows "Tags only support letters..." | You typed commas as text. Add topics post-publish instead. |

The 2/24h limit is server-side anti-spam with no bypass. Reports suggest it's tiered (members and older accounts get more headroom) and that Medium changes the numbers, but there's no setting to raise it.
