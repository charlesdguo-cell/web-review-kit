---
name: web-review
description: Use when creating or delivering an HTML report, static webpage, interactive prototype or demo for user review (HTML 报告、网页、原型、演示), connecting webpage comments, or handling review comments and frozen worker batches. Provide a review entry by default for HTML deliverables; respect explicit requests to skip comments.
---

# Web Review

Use the consumer project's pinned tool and accompanying workflow. Preserve original review evidence; technical completion is `changed`, while `resolved` requires user acceptance.

For HTML reports, static webpages, interactive prototypes and demos delivered for the user to inspect, provide a working comment entry by default and keep the original artifact readable offline. Respect explicit requests to skip comments and project-specific delivery constraints. Code snippets and non-HTML documents do not require review setup. This default belongs to the distributed Skill; no personal AGENTS.md rule or source-checkout wrapper is required.

For an HTML deliverable, read the consumer's instructions, use its existing review configuration or connect its actual HTML/build-output directory, and follow the project-setup workflow. Local Codex use includes the bridge by default: configure the real source/build/check guidance and executable, run doctor, then verify the page, matching health, bridge API and actual Codex control in the toolbar. Shared/offline review and an explicit Codex opt-out use comments only. Keep standalone HTML/offline assets intact and return the review URL and offline file link. Missing CLI, login or handshake must be reported; a comment toolbar alone is not a complete local Codex setup. Preparing the bridge never dispatches pending comments automatically.

Describe progress through the comment being handled, the problem found and the actual result. Keep tool-version and workflow mechanics for troubleshooting when relevant.

Run automated browser checks headlessly, using isolated profiles and temporary review data. Prefer the project's existing headless check entrypoints; verify effective headless mode when choosing another tool. Visible browsers are for explicit user viewing requests or user-assisted steps such as login. Save evidence, then close only the browser sessions and temporary test servers created for the check; retain the user's review service and existing windows.

An already dispatched worker follows only its frozen batch and executionConfig; HTML delivery defaults do not expand that task.

| Entry | Observable input | Read next |
| --- | --- | --- |
| Deliver HTML | HTML report, static webpage, prototype or demo for user inspection | Follow project setup using the existing pin, or this installed bundle for an unconfigured project |
| Connect a project | User requests review setup, no frozen worker request | [project-setup](references/project-setup.md) |
| Current conversation | User names comments to handle here | Locate the pinned release, then read its `commentWorkflow` |
| Existing worker | Already dispatched with frozen comments/request.json | Locate with `--request`, then read its `commentWorkflow`; consume this batch directly |

Installation/bootstrap and global or project-local discovery commands are in the same release's [release guide](../../docs/releases.md). Prefer the global discovery link for use across projects. Install returns the verified absolute `installRoot`; keep it with the installation instructions. A discovered symlink remains attached to its complete `INSTALL/releases/VERSION` bundle, allowing the helper to derive that exact root with receipt verification. It never searches for a newest version. A configured packaged worker also receives `executionConfig.installRoot`, `skillPath` and the absolute frozen request path in its prompt.

For a configured project, run the bundled helper through Python (omit `--install-root` only when using the verified layout above):

```sh
python3 /absolute/path/to/skills/web-review/scripts/review.py --project /absolute/consumer --install-root /absolute/installation locate
```

Use the returned absolute `setupWorkflow` or `commentWorkflow` path from that release, rather than the host's newer references. Subsequent explicit CLI operations use this same helper and project/install root. For an existing worker, add `--request /absolute/job/request.json` before `locate` and every data command. It checks the frozen identity/version/skill path, retains request guidance and targets request.reviewUrl. If the worker prompt contains the request inline only, preserve it verbatim in a temporary file before using the helper.

Missing resolver, missing pinned release or incompatible `workflowVersion` is a stopping condition: report the missing capability. Do not fall back to host/latest, download, update the pin, or dispatch a job to solve it. Only first setup without a configuration may use the explicitly selected host bundle.

An existing worker must not start another Codex, subagent or review task. Both processing modes limit work to authorized incremental fixes and the consumer's source/build/check guidance. The toolkit itself and global agent configuration are outside a consumer review fix.

Report these outcomes separately: **installed** means tool/Skill files are discoverable; **configured** means project configuration exists; **bridge ready** requires its configured prerequisites and doctor success; **running** requires a live service with matching project identity and the toolbar verified. No earlier outcome implies a later one. Other agents can use the public CLI/API and exported evidence in their current conversation; automatic webpage dispatch is a local Codex capability.
