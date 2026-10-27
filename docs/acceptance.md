# Core acceptance · 2026-10-27

## rc.4 distribution follow-up · 2026-10-27

`0.1.0-rc.4` distributes the HTML report/page/prototype/demo delivery default inside the standard `web-review` Skill and documents global installation. Maintainers and teammates use the identical complete release; the temporary source-checkout wrapper and personal AGENTS.md delivery rule are no longer needed. Existing configured projects keep their pins and frozen tasks. All runtime files remain byte-identical to rc.3; no data/schema migration or real Codex task was run for this follow-up.

Verification: complete unittest discovery **140 OK in 81.863s**, isolated original browser suite **29 passed**, and a clean isolated installation from the rc.4 archive with no personal AGENTS.md. The clean check verified repeat install, the global link to the complete release, a fresh rc.4 project, matching HTTP health, the actual toolbar, saved synthetic comment with original screenshot, and unchanged standalone HTML bytes. One read-only behavioral review checked HTML delivery, old project pins, snippets, explicit opt-out and frozen-worker routing.

The first clean-check script used a synthetic input event without crossing the toolbar's shadow boundary. It timed out; the script was corrected to use real browser text input and passed. Runtime code was unchanged. Commands/results and screenshot are retained locally under `artifacts/releases/0.1.0-rc.4/`; no generated comment/evidence is included in Git or the package.

The rc.3 acceptance below remains the original snapshot, rather than a claim that all existing consumers have been upgraded.

The first-release gate is original comment and Codex parity plus reusable project configuration, Skill discovery and an exact private release installation. The candidate remains **0.1.0-rc.3**, source `9196c9477b3665cbe658c7df40c934854ffb61a2`. This acceptance work adds documentation and test harnesses; it does not change the 31 packaged files or publish a new candidate. User acceptance remains pending.

## Verified local combination

| Component | Actually exercised |
| --- | --- |
| OS / architecture | macOS 26.5.1 / Apple Silicon arm64 |
| Runtime | Python 3.9.6; Ruby 2.6.10 |
| Browser | Google Chrome 156.0.8078.48, separate temporary profiles |
| Tool install | Private GitHub rc.3, `/Users/charles/.local/share/web-review-kit`; same-version reinstall and explicit project-local Skill link |
| Product bridge | Codex CLI 0.162.1 App Server; actual authenticated OpenAI `gpt-6.1-sol`, inherited `ultra` reasoning |
| Permissions | Per-worker `approvalPolicy=never`, `sandbox=danger-full-access`; no global setting change |

This table records a tested combination, not a promise about other machines, accounts, models, browser engines or future versions. Doctor's handshake/auth check alone is not inference evidence.

## Independent review project

Current workspace path below reflects the user-requested relocation on 2026-10-27. Acceptance results and comment statuses describe the original test snapshot; later user runs may change them. Comments, attachments and task history were retained. Completed-job request location fields were updated, with original requests and hash records kept under `~/.local/share/web-review-kit-acceptance-backups/validation-relocation-20261027T131320Z/`.

`/Users/charles/.local/share/web-review-kit-validation` is a separate synthetic two-page Field Notes demo. It has its own AGENTS, README, review guidance, `src/`, built `public/`, `review-data/`, `.review/jobs/`, browser namespace and stable port. Text, SVG and the two-second WAV were generated locally. No Morsea business content, assets or comments were copied.

Open **http://127.0.0.1:8791/** and follow its README's five-minute review. Check the title `Field collection`, eyebrow `Independent static project`, filter, detail navigation, modal and playable audio. Open the comment list to inspect #1's original screenshot and PNG attachment. It is `changed`; #2 was created during the first worker run and remains `open`. Do not accept these on the user's behalf.

The matching Morsea service remains http://127.0.0.1:8768/. Task 9 only reads its health/comments/current task and hashes its existing data/jobs. It must not dispatch, steer, stop, retry, resume or write comments there. Local before/after preservation proof lives only in the validation project's ignored artifacts.

## Real versus fixture coverage

| Behavior | Evidence type |
| --- | --- |
| Browser selection → screenshot + attachment → saved comment → actual worker → source/build/check → guarded `changed` writeback | **Real browser and product Codex**, V only |
| Required AGENTS/README/guidance and pinned Skill consumed; source limited to own `src/` | **Real worker command events**, frozen executionConfig and resulting source diff |
| Running-time supplement applied to current #1 | **Real browser send and real worker result** |
| Running-time #2 stays outside immutable request and remains open | **Real browser save and persisted request/record comparisons** |
| Completed conversation followed up in same thread/job | **Real product Codex**; explanation-only follow-up excludes #2 |
| Stop, retry, lost-send response, draft/refresh recovery and old-task resume | Existing **protocol substitutes** and browser fixture; no claim of real cancellation/retry inference |
| Element/parent/region/text selection, anchor tracking, input/modal isolation, lost-save retry, offline persistence | Existing isolated Chrome synthetic fixture |
| Paste/file image handling, screenshots, attachment retry/preservation/limits and offline export | Existing isolated Chrome synthetic fixture |
| HTTPS prefix, two browser synchronization, stale-edit conflict and evidence preservation | **Real local TLS proxy and isolated Chrome**, temporary synthetic data; self-signed certificate accepted only by test clients (CDP and a local Python TLS context) |
| HTTPS asset bytes, media Range and HEAD | Actual installed rc.3 HTTP server through local TLS proxy |
| Two live consumer identities and preserved Morsea records/jobs | Live read-only APIs plus before/after SHA-256 inventories |

No inference/model substitute is counted as real Codex. No design acceptance is inferred from these checks.

## Actual results

- Complete unittest discovery: **140 tests OK, 80.519s**, one final run; it includes 26 Codex browser checks using the existing protocol substitute.
- Original comment/selection/offline browser suite: **29 checks passed**. Original attachment suite: **13 checks passed**.
- Isolated HTTPS: **11 contract checks plus 6 browser checks passed**.
- Retained real project: **19 preservation/identity/worker-evidence checks and 7 read-only browser checks passed**.
- All **31 published package files** remain byte-identical in both W and the installed rc.3 bundle.

The initial real-path harness completed the actual worker/writeback/continuation checks, then its extra programmatic audio play was rejected by Chrome's user-gesture policy. No inference was rerun: a read-only browser check with a trusted pointer click verified actual playback. The first TLS harness also logged a transient startup connection refusal; backend readiness now precedes proxy requests and the corrected isolated check passed. Both are acceptance-harness issues, not runtime changes.

## Acceptance harnesses

These manual scripts are deliberately outside ordinary unittest discovery. `real_core.rb` refuses nonempty comments and requires an explicit real-worker opt-in plus the exact authorized V root. It is a first-run acceptance harness, not an automatic regression against the retained user-review data. Do not delete/reset evidence to rerun it.

```sh
# Only after setting up the independent blank synthetic project with the documented fixed pin:
ALLOW_REAL_CODEX=1 VALIDATION_PROJECT=/Users/charles/.local/share/web-review-kit-validation ruby tests/acceptance/real_core.rb
# Separate scratch shared project, self-signed certificate and proxy; cleans up its own processes/data:
VALIDATION_PROJECT=/Users/charles/.local/share/web-review-kit-validation python3 tests/acceptance/shared_https.py
# Read-only retained-evidence verification; use the actual worker's saved external backup path:
VALIDATION_PROJECT=/Users/charles/.local/share/web-review-kit-validation WORKER_EVIDENCE_BACKUP=/absolute/worker-backup python3 tests/acceptance/inspect_core.py
# Read-only retained UI and actual audio playback through a trusted pointer gesture:
VALIDATION_PROJECT=/Users/charles/.local/share/web-review-kit-validation ruby tests/acceptance/retained_browser.rb
# Standard isolated fixture checks (never real inference):
PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'
ruby tests/browser/verify.rb
ruby tests/browser/verify-attachments.rb
```

The detailed command results, real job/thread IDs, screenshot locations and service PIDs are recorded in the implementation task's Task 9 report and V's `artifacts/acceptance/`. Test artifacts, real requests/events, user data and private preservation snapshots are excluded from Git and release packages.

## Scope and limits

Production/Linux deployment, public certificates, system trust installation, formal data migration, automatic upgrade/rollback, cross-root relocation and old-candidate compatibility sweeps are deferred. Existing advanced implementations remain experimental and are not first-release gates. Shared/offline review keeps Codex disabled. Ordinary installation, configuration and doctor checks do not mean a service or real task has run.

The local TLS check is a temporary loopback proxy, not a production deployment or validation of a team's actual proxy configuration. The real workflow uses one small synthetic batch and one explanation follow-up; it does not establish reliability for arbitrary large tasks, cancellation during every tool phase or all model/provider combinations. The original runtime can log a BrokenPipeError when a browser aborts media delivery; no runtime logging changes were made for acceptance.
