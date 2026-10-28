# Annotation refresh and retained-location validation

Date: 2026-10-28. Implements the user's report that a real edit did not refresh the page and its original annotation appeared to disappear. Scope: the [refresh design](superpowers/specs/2026-10-28-annotation-refresh-design.md) and [plan](superpowers/plans/2026-10-28-annotation-refresh.md), retaining the already accepted sidebar. No release or consumer upgrade was performed.

## Reproduced cause and behavior

The real demo contained all three saved annotations. A rewritten quote could no longer satisfy exact Range matching, so its highlight/number vanished and its card moved below the visible discussion. Reload also reset the sidebar and active conversation. Annotation polling ignored the changed build.

The original exact-text matcher remains unchanged. A separate display-location resolver recognizes a unique stable block ID or a unique original container supported by surviving context. It displays a dashed paragraph marker and aligns the discussion to that block without claiming the new words are the original quote. Missing, ambiguous or positional replacement containers retain their conversation, original quote and screenshot at a stable fallback location. Navigation brings those cards into view; repeated scrolling no longer moves their document position or grows the page indefinitely. Changed-location notices remain visible alongside Agent progress/failure status.

The server injects the loaded build into the review script. A newly changed annotation on the current page must have a completed Agent turn and a different build before automatic refresh is scheduled. Old completed work, ordinary answers and other-page edits do not trigger it. Drafts, pending requests, IME, body-form editing, review editing and ongoing sends defer refresh; the compact update action also preserves those inputs. Session storage must succeed before automatic navigation.

Sidebar state, active card, filters, expanded replies and reading/drawer positions are saved per project and canonical page. Restoration runs once after data/style/layout readiness. Query/hash identity changes rebuild the completion baseline and read their own view state; an epoch prevents a stale asynchronous restoration from applying to another identity. No request is replayed or dispatched by reload.

## Final verification

All automated regression fixtures use synthetic pages, temporary data and isolated headless Chrome. No real Codex task was started, stopped, retried, resumed or steered during this fix.

| Check | Result |
| --- | --- |
| Full documented discovery | **186 tests passed in 209.853s** |
| New anchor browser fixture, included above | **19 checks**, zero runtime exceptions, no Agent turns |
| New refresh browser fixture, included above | **33 checks**, zero runtime exceptions, no Agent turns |
| Same-document identity fixture, included above | **8 checks**, zero runtime exceptions, no Agent turns |
| Existing annotation and sidebar fixtures, included above | **36 / 52 checks passed** |
| `ruby tests/browser/verify.rb` | **29 checks passed** |
| `ruby tests/browser/verify-attachments.rb` | **13 checks passed** |
| `ruby tests/browser/verify-shared.rb` | **9 checks passed** |
| JavaScript/Ruby syntax and `git diff --check` | Passed |

Before implementation, the synthetic anchor test failed because the rewritten stable block had no marker, and the refresh test failed because the sidebar/current composer disappeared after real browser reload. A second anchor regression exposed whitespace-only prefix handling; ignoring insignificant whitespace in block identity fixed that case while retaining strict exact matching. Existing browser tests were updated to avoid toggling an already restored sidebar closed; their preservation assertions remain.

Independent review found a supported page-identity boundary: a fixed storage key would mix views after same-document hash/query navigation. The final implementation and dedicated hashchange/pushState/popstate regression address it; the reviewer found no remaining blocker. Temporary fixture mistakes involving missing screenshot data, an invalid message ID and a non-composed synthetic input event were corrected and are not counted as product passes.

## Retained real demo

**http://127.0.0.1:62891/** remains running with the real Codex configuration. Only its idle review service was restarted to load the server metadata addition; no task-control operation was sent. Generated runtime assets were rebuilt from the toolkit source. The only source-content edit made by this fix changes the demo's instruction to describe automatic refresh; the user's edited heading and other text remain intact.

A fresh read-only live browser check found **three cards and two changed-paragraph markers**, with the user's heading annotation aligned to its surviving container at the same vertical position. Desktop and narrow reloads retained that active discussion, with zero runtime exceptions. The injected build matched the served build; the demo's static check and 1440px/390px read-only render check passed.

All **34 pre-existing review-data and job files remained byte-identical**, and no new job was created. Complete data/job/source/output backups reside outside the consumer workspace, recorded by `artifacts/annotation-refresh-baseline.json`. The previous mock service is still available. html2canvas, its license and isolation patch are unchanged.

Private evidence remains in ignored `artifacts/annotation-{anchor,refresh}-*.log`, `artifacts/validation-annotation-{anchors,refresh,refresh-identity}/`, `artifacts/annotation-refresh-live/` and `artifacts/annotation-refresh-verified-source.json`. Runtime changes were compared with the external pre-fix working-tree backup, preserving earlier uncommitted work.

Automatic edit-triggered navigation was verified with isolated synthetic build/status transitions. This fix did not dispatch another real-model edit; the user's existing completed real conversations supplied read-only preservation and anchoring evidence. An already open browser needs one manual reload to load the repaired runtime. Formal coverage remains macOS Chrome and the documented static-page layout contract; publication remains pending user acceptance.
