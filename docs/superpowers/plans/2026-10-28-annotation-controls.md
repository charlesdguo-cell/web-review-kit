# Annotation control refinement

User request: simplify the unattractive annotation button, remove the distracting “你” label, and make the running-task stop action look like an actual button with restrained motion. This is a scoped refinement of the accepted sidebar, not a new flow or release.

- Keep the existing annotation palette, typography, card alignment and all `data-action`/API contracts.
- Use a compact comment icon for the selection trigger and a consistent arrow send control; keep accessible names/tooltips and explicit retry-confirmation text.
- Remove redundant visible user bylines. A new draft goes directly from its quotation to the input, retaining the upper-right close button without an empty metadata row/divider.
- Put progress and controls in one activity row. Render stop as a clearly bounded square-in-circle button with a subtle rotating ring, visible while running even when its card is inactive. Keep stopping disabled and respect reduced motion.
- Keep pointer focus restrained, keyboard focus visible, dark/narrow layouts usable, and touch targets generous. No data, worker, permission or installed-package change.

## Work and validation

- [x] Back up current source and retain read-only demo data/job hashes.
- [x] Refine `runtime/review.js` and annotation-scoped CSS, preserving polling node stability and original actions.
- [x] Inspect isolated synthetic screenshots and verify keyboard/pointer/stop/disabled/reduced-motion behavior; use no real tasks and add no redundant permanent test for this cosmetic change.
- [x] Run the documented full regression and relevant browser checks, then complete scoped independent review.
- [x] Refresh the retained demo assets, verify original records/jobs remain intact and record results without publishing.

Results: [sidebar validation follow-up](../../validation-2026-10-28-annotation-sidebar.md#follow-up-annotation-control-refinement). Full discovery passed 186 tests in 215.356s; 23 focused visual checks passed. The same real demo remains available at `http://127.0.0.1:62891/`, with all 43 original data/job files byte-identical.
