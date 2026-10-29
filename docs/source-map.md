# Extraction source map

## 2026-10-29 review stylesheet startup

The user authorized a fix for review controls briefly appearing at the top left during page navigation or refresh. `runtime/review.js` now keeps its host hidden until the Shadow DOM stylesheet's load event. The listener is registered before the host is connected, covering cached loads; failure keeps unstyled controls hidden. Annotation layout and saved-view restoration wait for the same readiness signal, preserving the saved view after failure and avoiding an empty sidebar reserve or lost draft focus. A page input used during loading retains focus. Early event capture, comments, annotations and screenshots retain their existing APIs. Synthetic delayed, failed and cached stylesheet checks live in `tests/test_review_startup_browser.py` and `tests/browser/verify-review-startup.rb`; they use temporary pages and isolated headless Chrome, without consumer data or real Agent tasks.

The change is prepared as local candidate rc.12 so installed rc.10/rc.11 bytes remain immutable. Packaging does not itself activate a global release, restart a consumer, or publish remotely. Consumer adoption and its evidence are separate from this toolkit source change.

## 2026-10-29 default activation and rc.11 release

The user subsequently authorized default global activation on installation and publication of a new version. rc.11 carries the global-runtime implementation below plus the installer's default activation and explicit `--no-activate-global` opt-out. `--activate-global` remains supported, discovery still requires an explicit `--skill-link`, and project configuration/data are preserved. The rc.10 local package remains immutable. See the [release plan](superpowers/plans/2026-10-29-rc11-release.md); the earlier local-only scope described below records the preceding task, not this publication authorization.

## 2026-10-29 global runtime selection

User-authorized [design](superpowers/specs/2026-10-29-global-runtime-design.md) and [plan](superpowers/plans/2026-10-29-global-runtime.md): one verified global `current` release, project `toolVersion: global` or an explicit pin, concrete versions frozen for services and workers. Configuration, resolver, installer, CLI/Skill routing and runtime startup share this policy. No toolkit source copy is maintained in consumers; build and compatibility adapters resolve the packaged runtime. Tests use temporary installations and synthetic data. rc.10 is a local candidate; packaging/installing it does not imply remote publication or deployment.

## 2026-10-28 content annotation extension

Approved design: `docs/superpowers/specs/2026-10-28-selection-agent-comments-design.md`; implementation plan: `docs/superpowers/plans/2026-10-28-content-annotations.md`. User clarified that natural-selection content annotations are independent of the original review mode and comment batches.

`runtime/review.js` and `runtime/review.css` add this reading interaction, its own panel, quote anchors and offline export. `runtime/server.py` and `runtime/review_data.py` add separate annotation persistence/API and evidence export. New `runtime/annotation_tasks.py`, with scoped additions to `codex_tasks.py` and `codex_session.py`, reuses the original launcher and execution lock for persistent annotation conversations. `release_manager.py` includes the new runtime module in the deterministic source allowlist. No consumer, installed release, formal record or historical job was changed.

New synthetic tests are `tests/test_annotation_tasks.py`, `tests/test_annotations.py`, `tests/test_annotations_browser.py` and `tests/browser/verify-annotations.rb`; export coverage extends `tests/test_review_data.py`. The existing protocol fixture only adds opt-in distinct thread identifiers and resumes the supplied identifier; original default behavior remains. Browser tests use the existing isolated headless Chrome support. Source extraction hashes below remain historical; html2canvas and its license/isolation patch are unchanged.

The approved [sidebar design](superpowers/specs/2026-10-28-annotation-sidebar-design.md) and [implementation plan](superpowers/plans/2026-10-28-annotation-sidebar.md) replace the independent annotation panel with cards aligned to original text, compact in-card discussion and a per-composer Agent response switch. This supersedes the reverted overview/detail experiment. `review.js`/CSS own layout and offline behavior; the annotation/task/server modules add save-only replies, immutable response choice and saved context for later explicit Agent turns. `annotation-messages.json` is separate from worker-owned conversation snapshots. New coverage uses `tests/test_annotation_sidebar_browser.py` and `tests/browser/verify-annotation-sidebar.rb`; existing annotation protocol/browser tests retain their preservation assertions. Reference research used an authorized real Feishu document and official instructions; private content and screenshots remain ignored research artifacts and were not copied into fixtures or source.

The [sidebar validation record](validation-2026-10-28-annotation-sidebar.md) records the final 183-test discovery, browser regressions, scoped review fixes, preserved preview data and explicit integration limits. No packaged release or consumer copy was changed by this increment.

The subsequent [real Codex demo validation](validation-2026-10-28-real-codex-demo.md) uses an explicitly authorized independent synthetic consumer outside this repository. It verifies real questions, same-thread followup and an edit/build/check/optimistic-writeback cycle against the unchanged development runtime. Real data, jobs and screenshots remain private artifacts; no release or existing consumer upgrade occurred.

The user's subsequent refresh/disappearing-annotation feedback is addressed by the [refresh design](superpowers/specs/2026-10-28-annotation-refresh-design.md) and [implementation plan](superpowers/plans/2026-10-28-annotation-refresh.md). `review.js`/CSS add conservative paragraph display anchors, stable unlocated-card navigation and per-page view restoration with protected automatic reload. `server.py` injects the loaded build identity without changing record/task APIs. Synthetic regressions live in `test_annotation_anchors_browser.py`, `test_annotation_refresh_browser.py` and their three browser runners; the shared fixture helper gains optional configured page identity. The [validation record](validation-2026-10-28-annotation-refresh.md) records 186 passing tests, browser checks and bytewise preservation of all real-demo data/jobs; those records and tasks were read-only during verification.

The subsequent [control refinement](superpowers/plans/2026-10-28-annotation-controls.md) changes only annotation markup and scoped styles in `review.js`/CSS: a compact comment icon, concise send control, removal of redundant user bylines/empty draft metadata, and an explicit animated stop button beside progress. Existing actions, storage and task protocols are unchanged; focused checks use temporary synthetic states rather than real tasks.

The separately authorized [rc.8 publication and Charlee adoption](superpowers/plans/2026-10-28-rc8-release.md) packages these additions. `release_manager.py` recognizes the closed pre-annotation inventory only for rc.1–rc.7, retaining per-file hashes, actual inventory, tree hash, dependency and receipt checks; newer versions require the annotation module. Three release regressions cover historical helper routing without mutation, strict version gating and integrity rejection. Publication and consumer validation are recorded separately from the development evidence above.

The subsequent [speaker identity refinement](superpowers/plans/2026-10-28-annotation-identity.md) updates only annotation presentation in `review.js`/CSS: saved initial messages and followups show inline `我：` / `Agent：` prefixes, including the standalone export. Drafts retain their compact layout; stored text, export JSON, task and data APIs are unchanged. Existing sidebar assertions query the separate content span so their deduplication checks still compare the exact original text.

## Original extraction baseline

Baseline captured 2026-10-27 from the **current working tree**, not Git HEAD, of `morsea-prototype`. Source HEAD was `9ce898fa7178befa4ac830cdbd1577255981a971`; the working tree was dirty and was not committed or changed by extraction. No business component, production review record, screenshot or asset is required by this repository's tests.

Recovery evidence is external, private and limited to this extraction's recovery: `/Users/charles/.local/share/web-review-kit-adoption-backups/web-review-kit-20261027T152615`. It contains the full review-data directory, runtime/support/deploy snapshot, protected SHA-256 manifests, Git status and read-only service/job observations. It must not be published or automatically replayed over current data.

## File provenance

Hashes below are the source file SHA-256 at extraction. Runtime, dependency/license, merge tool, protocol fixture, service/task tests and browser support are byte-identical; adapted browser tests and paths are indicated.

| Source relative to Morsea | Destination | Adaptation | Source SHA-256 |
| --- | --- | --- | --- |
| `tools/review/server.py` | `runtime/server.py` | Unchanged runtime | `4eb0f21b50860d4a5f14b81a5ba5b98087c486f760070f21e71aea0b7a801a3a` |
| `tools/review/codex_tasks.py` | `runtime/codex_tasks.py` | Unchanged runtime | `ba5db752ba3a498531dc3f9c4e80d4d6f2795bfedcd304e0b9e982aa5de51dd0` |
| `tools/review/codex_session.py` | `runtime/codex_session.py` | Unchanged runtime | `2481e9c550d0780a7fa9ee444818b92921491263fdffd8da3e0a669005e2047f` |
| `tools/review/review.js` | `runtime/review.js` | Unchanged runtime | `0d8ce7cb756517c80b411e4a9a9ab811215d67f41be84ec19b889373ffa9bb8d` |
| `tools/review/review.css` | `runtime/review.css` | Unchanged runtime | `81d92133eb3817ff9f0cdb744ff5422af3b939b9d17be0886a7194ff6c1e300d` |
| `tools/review/html2canvas.min.js` | `runtime/html2canvas.min.js` | Unchanged runtime | `e13cf4fb0919313c321783fb67b51b18dd0e7e90d33ba9fc50706278f070d363` |
| `tools/review/LICENSE.html2canvas-pro` | `runtime/LICENSE.html2canvas-pro` | Unchanged runtime | `934c3e7d2b010f3eef0b7fa06899b73e4b82c296f898490958bd5c42654c459c` |
| `deploy/merge-review-data.py` | `runtime/merge_review_data.py` | Renamed file only | `c13da9dcb10006b51cc7ab96d54def38e75e0558b455c68bbea66a162ae36bd2` |
| `tools/review/test_server.py` | `tests/test_server.py` | Unchanged | `3892b362a89f53f0bae19b71e2c9ffe0162868317ed2d30ef5a0b0b644ff5719` |
| `tools/review/test_codex_tasks.py` | `tests/test_codex_tasks.py` | Unchanged | `ebc7be5a89001ef2dc97a57abd263a8b32eb3c084c30547dcf4a2a839a7a669d` |
| `tools/review/test_merge_review_data.py` | `tests/test_merge_review_data.py` | Standalone path / unittest entrypoint | `a70eb879d71953e2bae5cf26dcfbd233863295a4567c6ec9ab64fcfdae087f1b` |
| `tools/review/test_codex_browser.py` | `tests/test_codex_browser.py` | Standalone path / unittest entrypoint | `da5bb98d2ea794fe142cd4e266e232177aafab7ad0485159acff3bcaf1dc5b7c` |
| `tools/review/codex_app_server_fixture.py` | `tests/codex_app_server_fixture.py` | Unchanged | `5fbc5b5c38e30421c2381a68ea92647be1c1318c223168416b6365e4d6940699` |
| `tools/review/verify.rb` | `tests/browser/verify.rb` | Standalone resources; synthetic page equivalents | `9b8946fb82f4dbfbde88c9c2794e526cbbc4f573222f9b6d1897da9cd80b145d` |
| `tools/review/verify-codex.rb` | `tests/browser/verify-codex.rb` | Artifact root only | `b7111a6beafdf58955a7f053e9825f310206e1561f91dfdbf07d1381e819c45d` |
| `tools/review/verify-attachments.rb` | `tests/browser/verify-attachments.rb` | Standalone resources; synthetic page equivalents | `b0800637d5a322325efb68cc33c83c8e2933a7135614cc33df12bd7297984f7c` |
| `tools/review/verify-shared.rb` | `tests/browser/verify-shared.rb` | Standalone resources; synthetic page equivalents | `13810edd386b149cb555597c43cd795185420d74a78701eb969d338702ca9b43` |
| `tools/support/cdp.rb` | `tests/support/cdp.rb` | Unchanged support | `b962a609b3bc8df54af0e4b62535eae9d0247c5ef2e0f547aa1186bfd7b45263` |
| `tools/support/browser.rb` | `tests/support/browser.rb` | Unchanged support | `3951f87d5020e71ff8f7e470c2a1ea41c0d45a029d899a21fc890d2617a34d03` |

## Fixture separation

`tests/support/fixture_site.rb` is new synthetic support. It creates independent HTML, a deterministic gradient SVG and genuine deterministic PNG review evidence entirely inside temporary directories. It copies only review runtime assets for offline checks.

The source `tools/review/verify.rb` keeps its Morsea integration cases untouched. The standalone version replaces the source homepage settings/login and workbench regeneration/canvas/media scenarios with synthetic dialog isolation, pointer-drag isolation, negative-layer screenshot and transform-following cases. Generic element selection, parent/child, disabled buttons, links, region selection, text ranges, input protection, SVG, Esc, lost-response retry, persistence/status and offline checks remain. Region and text annotations are also saved to the independent service. This is not a claim of rerunning Morsea business regression.

The attachments check retains its paste, pure-image, preview, cancel, retry, export, limits, mobile and offline coverage, using the independent offline page. Shared checks replace formal-data copying and business navigation with seeded synthetic comments/screenshots and generic links, preserving prefix, two-browser synchronization, attachments, stale-edit conflict and index alias coverage. Codex browser integration now exposes its original script as a unittest plus direct entrypoint and explicitly locates the standalone Ruby script; it still uses only the original protocol substitute.

## Runtime and dependencies

- Python 3.9.6, standard library only; inherited `removeprefix`/`removesuffix` require Python 3.9+. No new Python 3.10+ syntax.
- Ruby 2.6.10, standard library only (CDP WebSocket client, PNG fixture uses `zlib`).
- Google Chrome 156.0.8078.48 on macOS arm64; isolated headless browser profiles, optional `CHROME_BIN`.
- html2canvas-pro **2.4.2**, fixed vendored build and MIT license copied unchanged. Its SHA-256 appears above. The inherited patch adds `node.ownerDocument.defaultView.getComputedStyle(node).isolation === 'isolate'` to the real stacking-context decision, preserving negative-z-index pseudo-element images over parent backgrounds. This check is exercised by the synthetic `.photo` fixture.
- No install, network fetch, package manager, API key or real Codex account is needed for tests. Task 1 GitHub discovery was read only. Candidate release provenance and later private publication are recorded separately in the release evidence; this extraction baseline is historical.

## Deferred baseline limitations

The inherited server `PROJECT` default still reflects its original `tools/review` nesting, and the legacy Codex prompt retains Morsea build/source instructions. Runtime hashes deliberately remain unchanged in Task 1. Use explicit `--root`/`--data` and the injectable APIs for this baseline; do not claim a portable real-task bridge before the configuration/bridge tasks. Existing global browser storage keys, service identity and concurrency behavior are likewise baseline contracts for later scoped tasks. User scope was narrowed to macOS formal acceptance only. Existing HTTPS shared behavior is checked locally; Linux installation/acceptance and server deployment are excluded from this round.
