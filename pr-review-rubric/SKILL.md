---
name: pr-review-rubric
description: Use when reviewing a pull request or merge request, or your own diff before opening one, especially Python or ML/inference code, and when asked whether a change looks AI-generated, vibe-coded, over-defensive, or not production grade.
---

# PR Review Rubric

## Overview

A review is four sections, in this order, each one required. Bug-finding alone is not a review: the reader also needs to know whether the change should exist, whether it does what it claims, and whether the author understood the code they submitted.

Adapted from zhaochenyang20/sglang-diffusion-routing#32.

## Review shape

1. **Verdict and justification.** One line verdict (approve / request changes). Then what the PR does and the mechanism underneath it (memory layout, host-device sync, KV cache lifetime, scheduling, concurrency). Say whether the change is needed at all, or solves a non-problem, duplicates something existing, or adds complexity for no gain.
2. **Findings**, most severe first. Each finding: severity tag, `file:line`, what breaks and the concrete input that breaks it, and the fix.
   - `[P0]` correctness: off-by-one, races, shape/dtype mismatch, resource leaks, broad `except` that swallows failures
   - `[P1]` performance: `.item()` / `.cpu()` / `.tolist()` per element in a hot path, Python loops over GPU data, O(n^2) list ops
   - `[P2]` maintainability: duplication over 5 lines, magic numbers, vague names (`data`, `result`, `info`), circular imports
   - `[P3]` style: missing or `Any` type hints, impure functions, debug leftovers
   - `[P4]` process: tests that assert nothing, test private helpers, or mock the thing under test; no verification script
3. **Goal completeness.** Compare the PR description to the diff claim by claim. Name each claim the diff does not deliver, each unhandled edge case, and each unstated assumption about callers.
4. **AI-generated code check.** A plain verdict (looks hand-written / likely unreviewed AI output / mixed) backed by the specific lines. Signals:
   - `try/except Exception` around a large block, then log and continue
   - `hasattr` / `getattr` / `isinstance` chains guarding cases that cannot happen
   - `Any` or `if TYPE_CHECKING:` used to get past the type checker; `del unused_arg` to silence lint
   - one or two line `_helper` functions called once; `_` prefix on everything
   - docstrings that restate the signature (Args: request: The request object)
   - a constant defined in one module and imported once elsewhere
   - tests built to exercise the defensive branch instead of the feature

If no section has issues, say why the code is good. Never a bare LGTM.

## Fixes to recommend

Suggest the simpler code, never more protection. Inline single-use helpers. Delete guards for impossible cases. Replace `hasattr`/`getattr` with a typed field and a default on the type, not another `getattr`. Narrow `except` to the one error that is expected, or remove it. Pass defaults down from the top instead of re-declaring them in lower layers.

## Common mistakes

| Mistake | Instead |
|---|---|
| Skipping sections 1, 3 or 4 because the bug list is long | All four, every time; the bug list is only section 2 |
| Suggesting `getattr(x, "a", None) or DEFAULT` to fix a `hasattr` check | Put the field and default on the request type |
| "Possibly AI-generated" with no evidence | Quote the lines that show it, or say it looks hand-written |
| Nitpicking formatting a linter would catch | Leave it to the linter |
