# Real Codex annotation demo

User authorization: “你先在demo上真实接入codex我体验下 没问题我们就发布”. This explicitly authorizes real Codex tasks for the isolated demo. Publication remains pending the user's later acceptance.

## Scope

- Use the current source checkout and existing annotation bridge, with the installed, authenticated real Codex executable. Retain `approval_policy=never` and `sandbox_mode=danger-full-access`; do not alter global configuration or select a different model.
- Create a separate demo project outside the toolkit workspace, with its own source/build output, review data, jobs and project identity. Preserve the existing mock demo and all its records; do not resume fake thread IDs in real Codex or replay old requests.
- Configure actual source roots and build/check commands. Real editing is limited to this demo's `src/` content. No toolkit, business-project, global installation, release-version or remote publication changes are implicit.
- Keep real execution evidence private, outside tests and commits. Automated regression suites continue to use only synthetic protocol fixtures.

## Implementation and validation

- [x] Prepare demo source, project instructions and build/static/browser checks.
- [x] Configure the real executable and project guidance; run the supported doctor without a model turn and verify local health/API/browser controls.
- [x] Start a new real question through the annotation UI; verify persistent response and unchanged source.
- [x] Send a followup and verify it uses the same real thread.
- [x] Request one explicitly scoped demo text edit; verify source/build changes, checks and `changed` writeback with evidence preserved.
- [x] Confirm refresh preserves discussion, capture UI/runtime evidence, retain a usable real-demo URL and record remaining limits.

Results: [real demo validation](../../validation-2026-10-28-real-codex-demo.md). The live real demo is `http://127.0.0.1:62891/`; publication awaits the user's acceptance.

Only the root agent dispatches real tasks. Helpers may prepare files or perform read-only protocol review. Existing mock and unrelated real jobs remain untouched. If compatibility fixes to runtime are necessary, review the scoped change and run the documented independent regression before completion.
