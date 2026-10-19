---
name: medium-post
description: Use when publishing, drafting, or updating a Medium post/article/story from markdown, when adding images or screenshots to one, or when Medium blocks automation (Cloudflare "Attention Required", "you have been blocked", publish limit errors)
---

# Publishing to Medium

## Overview

Medium has no usable API (integration tokens discontinued) and hard-blocks CDP-driven browsers. The ONLY working automation path is the Claude-in-Chrome extension inside the user's normal browser, logged into Medium.

## Preconditions

1. Chrome extension connected (`tabs_context_mcp` succeeds). If not, ask user to install/connect claude.ai/chrome.
2. User logged into Medium in that Chrome. If medium.com/new-story shows "Welcome back" sign-in, ask user to log in — never do it for them.
3. Do NOT try agent-browser/CDP/headless — Medium's Cloudflare returns "Sorry, you have been blocked" regardless of headed/headless/real profile. Don't attempt to evade.

## Before writing: is it already published?

Use `medium.com/me/stories`, Published tab (the direct `?tab=posts-published`
URL can bounce to Drafts). It lazy-loads about 25 stories, and a JS
`scrollTo` loop does not load more. Scroll with real wheel events (the
extension's `scroll` action) until the count stops growing, and check it
against the tab's own total. A short list makes everything past it read as
"not yet published".

## Content rules (markdown → Medium)

- No tables — Medium doesn't render them. Convert to bullets before publishing.
- The document's own top-level `# H1` is the Medium title — strip it from the body, or it duplicates as title + first heading.
- Remove blank lines inside `<pre>`: paste splits a code block at each one into separate blocks.
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
4. **Verify the title survived** without a screenshot:
   ```js
   const t = document.querySelector('.graf--title');
   ({text: t.textContent, empty: t.classList.contains('graf--empty')})
   ```
   An empty title after the paste is the startup stall eating the typed
   title (see Known limits): click the title line and type it again. If the
   paste merged into the title instead, `ctrl+a` + Delete and redo from step 2.
5. Click Publish (top right). **The first click after page load often doesn't register** — if no dialog, click once more (don't double-click; that opens then closes it). In the dialog set "Paywall this story" (defaults checked) and zoom to verify the toggle took — clicks on it miss often. **Skip topics here** — see below.
6. Click Publish. Confirm via tab URL flipping to `<user>.medium.com/<slug>` (screenshot may fail there — subdomain lacks extension permission; that's success, not an error).

## Topics — always add them after publishing

The topic field **in the publish dialog is broken for automation**: suggestions appear, but clicking one (by coordinate or element ref) leaves the field empty and no chip is created. Commas and Enter don't tokenize either (a comma types the word "comma"). Don't fight it — publish without topics.

The post-publish editor's own topic UI works reliably. Go to `medium.com/p/<id>/edit` → ⋯ menu → **Change topics**, then per topic: click "Add a topic…", type, wait for the dropdown, click the suggestion — a chip appears immediately. Repeat up to 5, then click **Save**. (This popover has a Save button; the publish dialog's field does not.)

Match the suggestion that actually exists rather than the label you had in mind — e.g. there is no "AI Agents" topic, and "Note Taking" resolves to `Notetaking`.

## Fixing the title in the editor

"Change display title/subtitle" in the ⋯ menu sets the preview title, not
the title line. To fix stray text in the title line, select only the
title's own text with a Range, type the title, then rerun the step 4 check:

```js
const t = document.querySelector('.graf--title');
const r = document.createRange(); r.selectNodeContents(t);
const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
```

Never triple-click the title: the selection runs into the first paragraph,
and typing merges that paragraph into the title. If it happens, put the
caret at the end of the real title (a collapsed Range in `.graf--title` at
the title's length) and press Enter. The split-off paragraph comes back as an
`h3` heading; put the caret inside it and press `ctrl+alt+1` to turn it back
into a paragraph. Then check the title text, the first paragraph, and that
the `h3` count matches the source.

Coordinates for clicks: `getBoundingClientRect()` returns CSS pixels; scale
by `screenshotWidth / window.innerWidth` before clicking.

## Post-publish edits

Edit URL: `medium.com/p/<id>/edit` (stays on medium.com, permissions OK). The ⋯ menu there has: Manage paywall setting, Change topics, Change display title/subtitle, Manage unlisted setting. Body edits (text, images) go live only after **Save and publish**.

## Images

The page holds no `input[type=file]` until you click Medium's add-image button, and that click opens the native file picker, which browser automation can't drive. Intercept it first, so the input lands in the page where `file_upload` can reach it:

1. `javascript_tool`:
   ```js
   HTMLInputElement.prototype.click = function () {
     if (this.type !== 'file') return HTMLElement.prototype.click.call(this);
     this.id = '__fi'; this.style.display = 'block';
     if (!this.isConnected) document.body.appendChild(this);
   };
   ```
2. Put the caret at the end of the target paragraph (a collapsed Range in `javascript_tool`), then press `Return` for an empty line.
3. Click the inline "+" button on that line, then its add-image button.
4. `find` the input with id `__fi` and `file_upload` the local path to its ref.
5. After about 3 s, check a new `figure img` follows the target paragraph, then remove `#__fi`. Repeat from step 2 for each image.

Crop or blur screenshots before uploading: names, emails and signatures in them go public with the post.

## Known limits

| Symptom | Meaning |
|---|---|
| "maximum of two stories in the past 24 hours" | Account rate limit, rolling window. Draft is saved; publish later. |
| Same error when using "Schedule for later" | Scheduling counts against the quota **when you schedule**, not on the target date. It is not a way around the cap — wait for the oldest publish to age out. |
| Screenshot "Permission denied for this action on this domain" | Extension lacks per-site permission (e.g. user subdomain). Not fatal. |
| Screenshot "CDP sendCommand Page.captureScreenshot timed out" | Renderer is stalled, usually right after the editor loads. **Input sent during the stall is lost** — a title typed then is silently gone. Wait 3s, re-screenshot, and redo the step rather than assuming it landed. If input keeps dropping, reload the draft's own `medium.com/p/<id>/edit` URL (the draft autosaves); `new-story` starts over. |
| A topic you typed shows up in the title | The topic popover had closed, so the click landed on the title line. Fix it as in "Fixing the title in the editor". |
| Tag field shows "Tags only support letters..." | You typed commas as text. Add topics post-publish instead. |

The 2/24h limit is server-side anti-spam with no bypass. Reports suggest it's tiered (members and older accounts get more headroom) and that Medium changes the numbers, but there's no setting to raise it.
