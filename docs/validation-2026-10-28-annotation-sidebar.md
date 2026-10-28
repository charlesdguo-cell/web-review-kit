# Annotation sidebar validation — 2026-10-28

The user approved the [sidebar design](superpowers/specs/2026-10-28-annotation-sidebar-design.md) with “好的 开搞”. This local increment implements original-text-aligned cards and the per-composer Agent response switch. It supersedes the reverted overview/detail experiment. It does not publish a release or upgrade consumers.

## Implemented behavior

- A continuous 320px desktop sidebar follows native document scrolling. The active card aligns with its quote; adjacent cards avoid it in both directions. Current-page counts, document-order navigation, all/resolved filters and an empty-viewport jump keep annotations discoverable.
- Quotes and cards activate together. Long replies expand in place; one active composer retains drafts, focus and IME state across polling. Keyed DOM reconciliation includes newly arriving earlier annotations and unsent drafts, preserving document order in the drawer and keyboard traversal.
- Compact cards display the root once and the final reply once per turn. Screenshots, status actions and export remain available. Narrow layouts use the same cards in a drawer; light/dark colors are annotation-scoped.
- The bottom Agent switch defaults on for each new composer. Off sends save initial annotations and followups without queuing, starting or steering a task. Turning it on does not backfill old notes. Later explicit sends receive saved context while treating only the current message as the new instruction.
- `annotation-messages.json` holds immutable followup intent separately from worker snapshots. Public reads and exports merge saved replies. Legacy confirmation uses canonical private intent before redaction; a retry before the first thread exists refreshes saved context without changing its original current request.
- Original review mode, comments, evidence, shared/offline behavior and the shared project execution lock remain separate and covered by regression checks.

## Final verification

All tests use synthetic projects, temporary data, isolated headless Chrome and the protocol substitute. No real Codex job was launched or changed.

| Check | Final result |
| --- | --- |
| `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'` | **183 tests passed**, 142.233s |
| Sidebar browser fixture, included in discovery | **41 checks passed**, zero runtime exceptions |
| Original annotation browser fixture, included in discovery | **36 checks passed**, zero runtime exceptions |
| Existing Codex browser fixture, included in discovery | **26 checks passed**, zero runtime exceptions |
| `ruby tests/browser/verify.rb` | **29 checks passed** |
| `ruby tests/browser/verify-attachments.rb` | **13 checks passed** |
| `ruby tests/browser/verify-shared.rb` | **9 checks passed** |
| `node --check runtime/review.js`, Ruby runner syntax, `git diff --check` | Passed |

The sidebar fixture measures original text and its card moving **300px / 300px**, with a fixed header. It covers adjacent/overlapping/long cards, all/resolved/page boundaries, lost-response confirmation, no backfill, equal-text messages retaining distinct identities, exact body-style restoration, native selection, IME/polling, actual CDP touch taps, dark text/quote contrast, and shared/offline saves. The final insertion regression verifies ordering while preserving the active composing field.

Independent backend review found two retry edge cases; both were fixed and passed scoped re-review. Independent UI review found the late-arrival DOM-order issue; the fix and regression were checked in the final independent review. That review identified no remaining actionable blocker. A suspected reading-position issue was not reproduced: the measured text position remained within 1px.

Development runs exposed readiness races in the browser fixture, one test-only dark-color regex error and one CDP socket disconnect. The fixture corrections and final complete discovery passed; those earlier diagnostic runs are not reported as successful validation.

Evidence remains in ignored `artifacts/annotation-sidebar-*.log`, `artifacts/annotation-sidebar-*-review.md`, `artifacts/annotation-sidebar-verified-source.json`, and `artifacts/validation-annotation-sidebar/`. Five fixture screenshots were visually inspected: desktop, adjacent active card, expanded reply, narrow drawer and dark theme. The fixed html2canvas dependency is byte-identical to the pre-increment backup; its license/isolation patch are unchanged.

## Retained local preview and preservation

Preview: **http://127.0.0.1:62890/**. It uses synthetic text and protocol-generated replies for interaction review. The server was restarted on the same port only after its three synthetic jobs had completed; current runtime assets are served.

The complete preview data and jobs directories were backed up outside the workspace before restart. All three annotations, original messages/results/timestamps, screenshots and job files were preserved. Of 31 original persisted files, 28 remain byte-identical. Three derived public conversation snapshots gained only `hasAgent`, `initialMessageId` and assistant `turnId` fields; their existing content is identical after removing those additive fields. No prior snapshot was replayed over the live service.

A final read-only browser check confirmed three aligned cards, 320px sidebar width, one active composer, default-on switch and inactive legacy review mode. This check did not submit, retry, stop or resolve any annotation. The full data comparison and screenshot are retained in ignored artifacts.

## Validation boundaries

Formal coverage is macOS Chrome, ordinary static document layouts and responsive drawers. Opt-in layout/scroll-root adapters and arbitrary complex consumer layouts require their own integration verification. Touch input was browser-emulated, not physical-device testing. Protocol substitutes do not establish real-model intent accuracy or real multi-turn commentary/final classification. Shared behavior was checked with isolated local services, not a deployed HTTPS endpoint. Visual acceptance remains with the user; this is not production readiness, deployment, migration or consumer-upgrade authorization.

## Follow-up: draft close button

At the user's request, the separate “放弃草稿” row was removed and the same discard action moved to a × button at the draft card's upper right. The quote reserves room for the button, its accessible name remains “放弃草稿”, and existing send/pending-confirmation guards still apply. Collapsing the whole sidebar continues to preserve nonempty drafts.

Fresh full discovery after this small UI change passed **183 tests in 142.062s**, including both annotation browser fixtures. A separate temporary synthetic-page check verified the close button at 1440px and 390px, quote clearance, removal of the old row and actual click-to-discard without saving an annotation. Both screenshots were inspected. Independent scoped code review, JavaScript syntax and diff checks passed. No new persistent tests, backend changes or demo-data edits were needed; the existing local preview serves the updated assets. Evidence: `artifacts/annotation-draft-close-unittest.log` and `artifacts/annotation-draft-close-{1440,390}.png`.

## Follow-up: menus disappearing during synchronization

Reproduced the user's report before changing runtime: the open card menu and its focused action were replaced after two background annotation reads. The metadata renderer compared live `innerHTML` with closed-menu markup; native `details.open` changed that HTML, so the 1.5-second refresh rebuilt the menu. Clicking an inactive card's summary also entered the card-activation path.

Metadata now updates author, status and action attributes in stable nodes. Open menus and focus survive unchanged polls, streaming replies and metadata updates. Menu interactions do not activate another card or scroll the original text. Repeated ellipsis clicks, explicit choices, outside clicks and Escape deliberately close menus; Escape restores summary focus and leaves the sidebar open. A scoped reviewer identified a related async status-action race, fixed by capturing the clicked target before awaiting the fresh optimistic read.

Added 11 meaningful cases to the existing synthetic sidebar runner. The baseline failed the polling case; the fixed runner passed **52 checks**, including the held-read/concurrent-status case. Final documented verification passed **183 tests in 158.958s**, plus **29 original review**, **13 attachment** and **9 shared** browser checks. Browser results contain no runtime exceptions; syntax, whitespace and scoped code review passed. A read-only check on the retained preview also confirmed menu/focus preservation across two polls and Escape behavior. Preview assets were refreshed; no preview annotations or jobs were modified.

Evidence: `artifacts/annotation-menu-baseline.log`, `annotation-menu-fixed.log`, `annotation-menu-full-unittest.log`, `annotation-menu-{legacy,attachments,shared}.log`, `annotation-menu-runtime.diff`, `annotation-menu-verified-source.json` and `annotation-menu-preview.json` (all under ignored `artifacts/`).

## User acceptance and real Agent readiness

After the menu fix, the user confirmed “验收通过” and asked whether the feature was ready for use because Agent processing was still mocked. The current retained preview remains a protocol-substitute service (`artifacts/annotation-demo/fake-codex`). Annotation storage and the production bridge implementation exist, but this increment has not yet established a real-model question/reply or edit/build/check/writeback run. User acceptance of the demonstrated interaction does not supply that missing execution evidence or automatically upgrade installed consumer releases.

Subsequent authorized work established that real-model evidence on a separate demo at **http://127.0.0.1:62891/**: real question, same-thread followup, a single-sentence edit, successful build/check/browser commands and preserved-evidence `changed` writeback. The original mock service and all 51 persisted data/job files remain unchanged. See the [real Codex validation record](validation-2026-10-28-real-codex-demo.md). The user is now trying the real demo; publication and consumer upgrades remain pending.

## Follow-up: annotation control refinement

The user requested a simpler annotation button, removal of the distracting “你” row, and a recognizable stop button with restrained motion. The [scoped plan](superpowers/plans/2026-10-28-annotation-controls.md) changes annotation markup/styles only, preserving the existing actions, storage and worker APIs.

The selection trigger is now a comment icon with an accessible name and tooltip; send uses the concise visible label “发送” and an arrow. User bylines are removed from annotation cards, while saved dates, Agent labels and accessible reply roles remain. The draft's empty metadata row and redundant divider are removed: measured quote-to-input spacing decreases from **53px to 12px**, and metadata height from **20px to 0px**. The upper-right close button remains.

Progress and stop share one activity row. Stop is a bounded circular control containing a square, with a subtle rotating ring. It remains visible on an inactive running card, becomes disabled with a clear name while stopping, and stops animating under reduced-motion preferences. Desktop selection/stop targets measure **36px / 32px**; coarse-pointer targets measure **44px / 44px**. Pointer focus is restrained and keyboard focus remains visible.

Independent synthetic browser verification passed **23 checks**, including SVG-inner-target clicks, keyboard Enter, stop-node/focus retention across two polls, a single stop request, disabled repeat prevention, reduced motion, light/dark and narrow layouts. These focused checks used only temporary synthetic snapshots and an intercepted stop response: no real or substitute Agent worker was started. Final screenshots were inspected. An early dark screenshot used transient inline body styling and was recaptured with a stable synthetic theme plus explicit dark assertions; it is not used as dark-theme evidence. A brief drawer observation during screenshot capture was not reproducible after capture settled; no unrelated layout change was made.

Fresh documented verification passed **186 tests in 215.356s**, plus **29 original review**, **13 attachment** and **9 shared** browser checks. Syntax, whitespace and scoped independent source review passed. No redundant permanent test was added for this cosmetic increment; the full regression exercises the unchanged action contracts.

The retained real demo at **http://127.0.0.1:62891/** now serves the updated runtime assets. Build/static and desktop/narrow render checks passed. A fresh isolated browser verified the compact draft on that service without submitting it. All **43 existing data/job files** remain byte-identical; all four conversations remain complete. The server and real tasks were not restarted or controlled, and no release/consumer upgrade occurred. An open browser needs a reload to load these assets; visual acceptance remains with the user.

Evidence: ignored `artifacts/annotation-controls-visual/` (before/after metrics, settled screenshots, 23 checks and isolation evidence), `artifacts/annotation-controls-{baseline,verified-source}.json`, `annotation-controls-runtime.diff`, `annotation-controls-full-unittest.log` and `annotation-controls-{legacy,attachments,shared}.log`. The similarly named historical `artifacts/validation-annotation-controls/` belongs to the superseded overview-panel experiment and was not used as this increment's evidence.
