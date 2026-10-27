# Connect a static project

This workflow belongs to workflowVersion 1 of its release. Installation and private release retrieval are separate from project setup. First install the exact authorized candidate using the bundled [release guide](../../../docs/releases.md), which documents private GitHub bootstrap, checksum validation, explicit install root and optional project-local Skill discovery. Installation returns the absolute `installRoot`; the complete installed helper can also derive it from its verified release directory. Do not guess a machine path, choose latest or download a missing pin during comment processing. For “connect webpage review”, provide a running URL when the user requests a usable entry; configuration-only requests stop after setup. Toolbar/health verification is required before reporting running.

HTML reports, static webpages, prototypes and demos delivered for user inspection use this workflow by default under the Skill's delivery rule. Explicit opt-outs and project constraints take precedence. Keep the offline artifact and provide a verified HTTP comment URL; no personal global AGENTS.md edit is needed. An existing frozen worker consumes its batch instead of setting up a new review entry.

Read the consumer's AGENTS.md and project instructions. Confirm the static HTML/build-output directory, source roots, build/check commands, host/port and whether local Codex bridging was requested. Source JSX must be built by the consumer first. This version does not integrate Vite/HMR, Next.js or SSR.

For a new unconfigured project, an explicitly selected toolkit checkout/bundle supports:

```sh
python3 /absolute/toolkit/web-review.py --project /absolute/consumer setup --web-root public --no-codex
```

Setup creates `review.config.json` only. It does not install a Skill, launch a service or process comments. Existing conflicting configuration returns a diff; preserve the projectId, pin and data and resolve the explicit mismatch. For configured projects use `scripts/review.py --project ... --install-root ... locate`, read that release's `setupWorkflow`, and route CLI commands through that helper.

Set consumer-owned `guidance.requiredFiles`, `sourceRoots`, `buildCommands`, and `checkCommands` in `review.config.json` before enabling worker execution. Paths are relative to the project root unless absolute; commands are argv arrays executed with that root as cwd. Empty defaults do not establish permission to alter arbitrary files or prove that builds/checks are unnecessary. Determine the project's actual contract from its instructions and scope, and record it explicitly. Data/jobs remain outside served output; choose an unused port rather than replacing another service.

When the user requests a running review entrypoint, call the pinned `serve` command, verify returned URL/health has the configured projectId, and inspect an HTML page for its injected toolbar using an isolated browser profile. Retain the service lifecycle needed for the user's use. Report the actual process/service state. If the request is configuration only, stop after configuration without serving or processing comments.

For a requested local Codex bridge, configure the executable and optional model explicitly. The authorized worker permissions are `approvalPolicy=never` and `sandbox=danger-full-access`; never modify global settings. Run pinned `doctor`: it checks availability/protocol/auth without inference. `ready=true` is prerequisite readiness, not a running service or successful real job. Then verify the local service's enabled bridge; real job execution requires its own requested comment task. Shared HTTPS and offline review keep Codex disabled.

| State to report | Evidence |
| --- | --- |
| Installed/discoverable | Tool and Skill files found; installation integrity only if actually verified |
| Project configured | Setup output and preserved review.config.json identity/pin/paths/guidance |
| Bridge ready | Codex enabled locally, readable pinned Skill, configured executable, doctor ready result |
| Service running | Live matching health, returned URL and actual injected toolbar inspection |

Other agents use public `list`, `show`, `export`, and `mark-changed` commands or the same HTTP API. There is no promise of webpage activation for them. If local data cannot be reached from the current agent, obtain an exported evidence package (`export --output` to a new directory) or an authorized HTTPS shared URL. Export preserves raw comments plus an evidence URL-to-file map; it is not a full data-directory backup. Do not pretend this is automatic local-machine bridging. Offline records need explicit reconciliation through the supported import workflow before claiming live writeback.
