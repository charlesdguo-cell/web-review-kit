---
name: web-review
description: Use when connecting a static HTML project to Web Review Kit, handling specified webpage comments in the current conversation, or consuming an already dispatched worker's frozen request.json batch. Not for broad unauthorized product redesign.
---

# Web Review

Use the consumer project's pinned tool and accompanying workflow. Preserve original review evidence; technical completion is `changed`, while `resolved` requires user acceptance.

| Entry | Observable input | Read next |
| --- | --- | --- |
| Connect a project | User requests review setup, no frozen worker request | [project-setup](references/project-setup.md) |
| Current conversation | User names comments to handle here | Locate the pinned release, then read its `commentWorkflow` |
| Existing worker | Already dispatched with frozen comments/request.json | Locate with `--request`, then read its `commentWorkflow`; consume this batch directly |

For a configured project, run the bundled helper through Python:

```sh
python3 /absolute/path/to/skills/web-review/scripts/review.py --project /absolute/consumer --install-root /absolute/installation locate
```

Use the returned absolute `setupWorkflow` or `commentWorkflow` path from that release, rather than the host's newer references. Subsequent explicit CLI operations use this same helper and project/install root. For an existing worker, add `--request /absolute/job/request.json` before `locate` and every data command. It checks the frozen identity/version/skill path, retains request guidance and targets request.reviewUrl. If the worker prompt contains the request inline only, preserve it verbatim in a temporary file before using the helper.

Missing resolver, missing pinned release or incompatible `workflowVersion` is a stopping condition: report the missing capability. Do not fall back to host/latest, download, update the pin, or dispatch a job to solve it. Only first setup without a configuration may use the explicitly selected host bundle.

An existing worker must not start another Codex, subagent or review task. Both processing modes limit work to authorized incremental fixes and the consumer's source/build/check guidance. The toolkit itself and global agent configuration are outside a consumer review fix.

Report these outcomes separately: **installed** means tool/Skill files are discoverable; **configured** means project configuration exists; **bridge ready** requires its configured prerequisites and doctor success; **running** requires a live service with matching project identity and the toolbar verified. No earlier outcome implies a later one. Other agents can use the public CLI/API and exported evidence in their current conversation; automatic webpage dispatch is a local Codex capability.
