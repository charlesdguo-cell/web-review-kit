# Process reviews with frozen evidence

This is workflowVersion 1. Follow the **selected release's** workflow. All commands below use the helper from the discovered Skill with `--project /absolute/consumer --install-root /absolute/installation` before the command. `locate` names the exact runtime and references. Missing/incompatible releases stop processing; do not swap in another version.

Use the installer's returned absolute `installRoot`, or the worker's frozen `executionConfig.installRoot`. With a complete installed Skill symlink the helper can derive that same verified root; omit the flag only in that case. Bootstrap/discovery is documented in [releases](../../../docs/releases.md); a missing installation during comment work must be reported, never repaired by an unrequested download or upgrade.

## Establish the batch and consumer contract

Current conversation: read `review.config.json`, project AGENTS.md and `guidance.requiredFiles`; use its `sourceRoots`, `buildCommands`, `checkCommands`, running URL and data path. Call `show --id comment-ID` once for each user-selected record and save the entire successful JSON envelope to a new external temporary snapshot file. Verify `ok=true`, projectId and the requested comment id before using it. Do not overwrite that snapshot on later reads. `list` may discover explicitly requested scope, but do not silently add more work.

Existing worker: read the existing request file, not a task launcher. Pass `--request /absolute/job/request.json` before every helper command. `project`, `data`, `reviewUrl`, `comments[]`, and `executionConfig` are the frozen execution contract. Its `guidance`, `codex`, `projectId`, `toolVersion`, absolute `skillPath` remain authoritative for this batch; do not replace them with a later project configuration. The helper stops if project identity, pin or skill changes. Read consumer AGENTS.md and the frozen requiredFiles. The request URL is authoritative even when current config host/port/basePath has changed; never redirect the batch blindly to the newly configured endpoint. CLI data operations check that URL's health projectId before accessing comments.

Extract each worker snapshot without fetching/replacing it:

```sh
python3 /absolute/skill/scripts/review.py --project /absolute/consumer --install-root /absolute/installation --request /absolute/job/request.json snapshot --id comment-ID --output /absolute/new/frozen-comment-ID.json
```

This creates a single `{projectId, toolVersion, comment}` envelope from the original comments array and refuses to overwrite an existing file. Do not pass the whole request to `mark-changed --snapshot`; that command accepts one raw comment or one `show`/snapshot envelope. Do not start another worker, Codex, subagent or task-start API call. Process only the frozen batch, ordered by number and dependencies; comments arriving later wait for a new request.

## Evidence, scope and implementation

Read every frozen body, status, anchor, original screenshot and attachment. View the actual evidence, not metadata alone. Resolve local evidence from the frozen data directory, or access its own-service URL and exported evidence map; retain the originals and raw fields. If evidence/data is unavailable, obtain an export or authorized shared URL as explained in project-setup. Do not claim an unreachable machine has been bridged or a partial export is a full backup.

Before working on each item, fetch `show --id` from the same service and compare the full record to its frozen snapshot, including status, body, anchor, attachments and updatedAt. An item no longer open or changed since freezing is skipped with its reason; continue independent items. Do not refresh a stale snapshot's timestamp to manufacture permission to overwrite it.

Inspect the related consumer interaction rules and source. Make the authorized incremental fix inside sourceRoots; preserve existing uncommitted work. When existing behavior already satisfies the request, verify it and record “已有实现，已复核”. Conflicting product requirements, missing source/build guidance or incomplete work stay open with a concrete reason. Broad product redesign, toolkit changes, commit/push/deploy are separate authorization scopes.

Run the configured build commands and checks appropriate to the change. Browser automation defaults to **headless** with isolated profiles and temporary review data. Prefer the consumer's existing headless checks. When choosing another runner, verify the effective mode (including reused sessions/configuration); do not add `--headed` or open temporary test URLs in the system browser for automatic checks. A visible browser is appropriate when the user explicitly requests to see the page or must perform an interactive step such as login. Save logs/screenshots and other evidence, then close only the sessions and temporary test servers created for this check. Keep the formal review service and the user's existing windows running.

Distinguish targeted validation, full regression and user design acceptance. Record actual results and failures; no fabricated checks or blanket completion based on a process exit.

## Reliable writeback and readback

Before the first review write, copy the **complete data directory**, including screenshots/attachments/metadata, to a new location outside the consumer workspace, preserving fields and timestamps. Keep the frozen request/snapshots. Export alone is not this backup. If the data directory is inaccessible, obtain a complete backup through its owner before live writeback; a shared view alone does not supply it.

Only verified items receive a nonempty resolution describing the change and actual checks. Save that resolution in UTF-8, then invoke:

```sh
python3 /absolute/skill/scripts/review.py --project /absolute/consumer --install-root /absolute/installation --request /absolute/job/request.json mark-changed --snapshot /absolute/frozen-comment-ID.json --id comment-ID --resolution-file /absolute/resolution-ID.txt
```

For current-conversation processing omit `--request`; if using an explicitly identified shared service, provide `--review-url https://authorized-service/base` before the command. The endpoint must report the configured projectId. This does not bypass access authentication or grant a missing network connection.

`mark-changed` rereads and compares the original snapshot, preserves all its evidence/extension fields, posts only the changed status/resolution using the fresh matching updatedAt as expectedUpdate with matching Origin, and reads back. A conflict returns exit 3: stop this item's write, preserve the original snapshot and report the conflict. Never replace it with current data and retry blindly. Only an identical already-successful submission is idempotent after a lost response.

Before finishing, call `show --id` again for each involved item and confirm verified items are `changed` with the expected resolution and intact originals; account for every skipped or unfinished item without changing it. Never mark `resolved` for technical completion. Return per-item changed/skipped/open results, what changed, actual checks, unresolved reasons and viewing URL; process completion and passing tests do not establish user acceptance.
