# Web Review Kit

Private team toolkit for static HTML and build output: element, region and text comments, original screenshots, attachments, optimistic updates, offline export and shared HTTP review. The current checkout version is in [VERSION](VERSION). Runtime source lives only in `runtime/`; consumer copies are installed artifacts.

The first-release goal is parity with the original comment/selection/location, screenshot/attachment, offline export and shared review behavior, plus the existing Codex frozen-batch processing, progress, supplemental instructions, stop/retry and same-thread follow-up. Project configuration, the [web-review Skill](skills/web-review/SKILL.md) and a verified fixed-version install support reuse. Core usability must be validated in Morsea and one independent static project while preserving original data and task history.

Use the single installation root `/Users/charles/.local/share/web-review-kit` and the explicit candidate in [VERSION](VERSION), following the [installation guide](docs/releases.md). Installation does not implicitly change project pins, data or global agent configuration. Advanced update/rollback, cross-root relocation, old-candidate compatibility and multi-platform support are experimental or deferred; they are not first-release acceptance gates. Real Codex and user acceptance still require their own evidence; local protocol tests do not establish them.

## Configure and serve

Use Python 3.9+ on macOS. Build source JSX with the consumer's own build first; framework development servers, Vite/HMR and SSR are outside this version.

```sh
python3 /absolute/web-review-kit/web-review.py --project /absolute/consumer setup --web-root public --no-codex
python3 /absolute/web-review-kit/web-review.py --project /absolute/consumer serve
```

Setup writes only `review.config.json`. It preserves an existing project identity/pin and rejects conflicting explicit options with a diff. Serve reports its URL and reuses only the exact configured service; it does not replace an unrelated port/data owner. Open the returned URL and verify the injected review toolbar. Data and jobs must remain outside served output. Preserve the complete data directory, including screenshots, attachments and metadata.

Report four separate outcomes: **installed/discoverable** tool and Skill files; **configured** project identity/paths/pin/guidance; **bridge ready** configured local Codex prerequisites and successful doctor; **running** live matching service and verified toolbar. None implies the next. A local source checkout is not a verified release installation.

Before enabling a requested local Codex bridge, fill the consumer-owned `guidance.requiredFiles`, `sourceRoots`, `buildCommands`, and `checkCommands` in its configuration. Commands are argv arrays executed at the consumer root. Configure Codex executable/model and enabled state explicitly, then run `doctor`; it checks environment, App Server protocol and login without inference. Workers receive immutable executionConfig and frozen comments, use the bundled Skill directly and never recursively dispatch. The bridge uses `approvalPolicy=never` and `sandbox=danger-full-access` without changing global configuration. Enabling prerequisites does not authorize an unrequested real comment task.

```sh
python3 /absolute/web-review-kit/web-review.py --project /absolute/consumer doctor
```

## Process comments

For a configured installed project, use the [Skill helper](skills/web-review/scripts/review.py), which resolves `review.config.json.toolVersion` through `release_manager.resolve_project_release` and invokes only that version's CLI and workflow references:

```sh
python3 /absolute/skill/scripts/review.py --project /absolute/consumer --install-root /absolute/installation locate
```

Read the returned version-specific workflow path. Raw checkout CLI commands remain development interfaces: `version` reports actual and required versions plus whether this is a verified installation. Do not infer that a newer checkout is safe for an older configured pin.

Available CLI commands are `setup`, `doctor`, `serve`, `version`, `list`, `show`, `export`, and `mark-changed`. Existing `update`/`rollback` commands are experimental and deferred from first-release acceptance; use the fixed-version installation workflow. Commands return structured JSON or the service lifecycle result; errors distinguish unavailable configuration/capability (2) and version/project/concurrency conflicts (3).

```sh
python3 /absolute/toolkit/web-review.py --project /absolute/consumer show --id comment-ID
python3 /absolute/toolkit/web-review.py --project /absolute/consumer export --output /absolute/new/evidence-export
python3 /absolute/toolkit/web-review.py --project /absolute/consumer mark-changed --snapshot /absolute/frozen-comment.json --id comment-ID --resolution-file /absolute/resolution.txt
```

Freeze the individual successful `show` envelope before edits, inspect its screenshot/attachments, follow consumer source/build/check guidance and back up the complete data directory outside the workspace before the first write. Export preserves raw comments and own-service evidence with a separate URL map; it is not a complete data backup. `mark-changed` rereads the record, rejects a stale snapshot, preserves original fields/evidence, posts a nonempty resolution with Origin and expectedUpdate, and reads back. Never replace a stale snapshot and retry blindly. Technical completion is `changed`; acceptance is `resolved`.

An already dispatched worker consumes its frozen batch and executionConfig directly. The helper's `--request /absolute/job/request.json snapshot --id comment-ID --output /absolute/new/frozen.json` extracts one original record exclusively; the whole request is not a valid mark-changed snapshot. Every helper data command with `--request` targets the frozen request.reviewUrl even if current server configuration changes. Raw CLI data commands also accept global `--review-url URL`; ReviewClient verifies that endpoint's projectId before access. Other agents can use these public CLI/API operations in their current conversation; webpage activation is only promised for local Codex.

## Shared and offline review

For HTTPS sharing behind a proxy that preserves Host/path, configure `server.host=0.0.0.0`, an explicit basePath and HTTPS publicOrigins through setup/configuration, then serve. Shared mode disables Codex and does not expose local filesystem paths in public health. It is retained and tested through isolated local sharing; deployment is a separate task.

For an offline copy, place `review.js`, `review.css` and `html2canvas.min.js` together and add `<script src="review-assets/review.js" data-prototype-review></script>` in the HTML head. File entrypoints persist in browser storage and export JSON with attachments; original screenshots require HTTP. If an agent cannot reach the local machine, supply an exported evidence package or authorized HTTPS shared review URL; automatic bridging is not implied. Offline records require explicit supported import/reconciliation before live completion can be claimed.

The existing stopped-service import utility is retained for separately authorized maintenance. Formal data migration and production deployment are outside the first-release scope; preserve original data and evidence during integration.

## Verification

Python 3.9+, Ruby standard library and Google Chrome are required. Set `CHROME_BIN` if needed. Tests use synthetic data, isolated browser profiles and protocol substitutes; they never launch the real Codex executable. Generated artifacts are ignored.

```sh
PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'
ruby tests/browser/verify.rb
ruby tests/browser/verify-attachments.rb
ruby tests/browser/verify-shared.rb
```

The discovery suite includes the Codex browser protocol fixture; separately use `PYTHONPATH=runtime python3 tests/test_codex_browser.py`. Router boundary tests use isolated stub resolvers; release tests also exercise the real packaged resolver. They cover an older project pin with a newer host, incompatible/missing release rejection, frozen requests and isolated Skill discovery/invocation. See [source provenance](docs/source-map.md), [repository rules](AGENTS.md) and the Skill's [setup](skills/web-review/references/project-setup.md) and [comment workflow](skills/web-review/references/comment-workflow.md). This round formally validates macOS only.
