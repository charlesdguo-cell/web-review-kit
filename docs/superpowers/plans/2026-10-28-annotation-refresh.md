# Annotation Refresh Implementation Plan

> **For agentic workers:** Use coordinated subagent implementation and independent review. This fixes the user's reported failures in the already authorized annotation demo. Preserve dirty work; do not commit or publish.

**Goal:** Keep annotations discoverable and preserve the reading context when an Agent's verified edit refreshes the page.

**Architecture:** Add conservative block-level display anchors alongside immutable exact-text evidence. Persist per-page view state and reload only after a newly completed edit changes the loaded build, with input protection.

**Tech Stack:** Existing vanilla JS/CSS, Python standard library and isolated Ruby/CDP Chrome checks.

**Spec:** `docs/superpowers/specs/2026-10-28-annotation-refresh-design.md`.

## Constraints and review focus

- `runtime/` remains unique source; preserve original review APIs, evidence, attachment, offline/shared and task contracts.
- No real task dispatch, stop, retry, steering or data migration. Preserve `never` / `danger-full-access`; no global config changes.
- Exact text versus block identity must remain distinct; deleted/replaced/ambiguous containers must not receive false highlights.
- Reload must not drop inputs, replay requests, loop, cross page identities or respond to old completed jobs.
- Scroll restoration and orphan layout must be stable after repeated scrolling and in the narrow drawer.

## Tasks

- [x] Back up current runtime/test sources and complete demo data/jobs externally; retain a baseline manifest.
- [x] Add synthetic regressions demonstrating missing block markers and lost refresh state before runtime changes.
- [x] Add block fallback, stable unlocated-card placement and navigation in `runtime/review.js`/CSS; preserve exact-range checks.
- [x] Add loaded-build metadata in `runtime/server.py`; implement scoped completion detection, protected reload and per-page session view restoration in `runtime/review.js`.
- [x] Verify targeted browser scenarios with synthetic status/build transitions and no real tasks.
- [x] Run full discovery and original review/attachment/shared browser checks; independently review changes and address findings.
- [x] Refresh only the real demo's current assets/service as necessary with no active tasks, preserve all data/jobs bytewise and verify live annotations read-only.
- [x] Record actual results and leave the demo available for user acceptance; do not publish.

Results: [validation record](../../validation-2026-10-28-annotation-refresh.md). Full discovery passed 186 tests; all 34 existing real-demo data/job files remained byte-identical. Real demo stays at `http://127.0.0.1:62891/`.
