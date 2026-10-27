# Default local Codex bridge implementation plan

**Goal:** Local review setup includes Codex bridging by default; shared review and explicit opt-out remain comments-only. Publish rc.5 and install the same GitHub package globally on this machine.

**Approved scope:** User requested “改组件 然后发布”. Work only in Web Review Kit and its global installation. Do not change consumer projects, running services, formal comments or real jobs. The previous diagnosis and confirmed complete Codex bridge requirement define this change.

**Architecture:** Derive the new-project bridge default from the final server settings, after applying setup options. Preserve existing configuration and explicit flags. Skill setup fills actual project guidance, resolves the CLI, runs doctor and verifies the live bridge toolbar/API. Enabling a bridge never dispatches a comment batch automatically.

**Stack:** Python 3.9 standard library, Ruby/isolated Chrome, existing Codex protocol fixtures and read-only real App Server doctor.

## Steps

- [x] Add failing CLI checks for local default bridge/API, shared default off, explicit opt-out preserved, and shared explicit enable rejected.
- [x] Set the default only for new configurations with no explicit Codex option; retain config conflict behavior. Keep comment-only test fixtures explicitly opted out.
- [x] Update the distributed Skill, setup workflow and installation examples to require local bridge readiness and actual UI/API verification. Keep shared/offline and user opt-outs explicit; use plain user-facing progress.
- [x] Run the independent unittest suite and relevant browser checks. Package rc.5; exercise fresh installed defaults, real read-only doctor, actual toolbar/bridge API and screenshot/comment preservation with synthetic data. No real model task.
- [ ] Review the scoped change, commit/push, publish a versioned GitHub release, download that release and install its global Skill using the standard installer. Verify package identity and global routing; leave existing projects untouched.

## Review focus

- Shared server settings must default off even when provided without a Codex flag.
- Explicit `--no-codex` and old disabled configurations remain disabled on repeat setup.
- Missing CLI/auth must be reported, not silently treated as a complete bridge.
- Default service exposes the bridge API without starting a model job.
- Release installation must contain the same Skill/runtime as teammates receive; never hot-edit an installed release.
