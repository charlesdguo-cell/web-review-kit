# Global Runtime Implementation Plan

> For agentic workers: use coordinated implementation and independent review; user authorized execution directly.

**Goal:** One global runtime default, optional project pins, and working Morsea annotations without duplicate project tool maintenance.
**Architecture:** Verified global current pointer resolves global projects. Concrete runtime freezes service/job execution; exact pins remain supported.
**Tech Stack:** Python 3.9 stdlib, existing Ruby/Chrome checks.
**Spec:** docs/superpowers/specs/2026-10-29-global-runtime-design.md

## Global Constraints
Preserve formal data/jobs, existing API/UI/contracts, Python 3.9; no real jobs, no remote publication/deployment, no installed-release hand edits. Local package version 0.1.0-rc.10.

## Review Focus
Missing/tampered current; fixed pins under newer default; default switch while frozen worker runs; installed vs checkout launch resolution; build/assets/service version agreement.

### Task 1: Toolkit global resolution
- [x] Extend runtime/project_config.py, runtime/release_manager.py, scripts/install.py, schema and setup with explicit global policy/current selection.
- [x] Adapt Skill helper, CLI/compat, service/doctor and frozen execution boundaries. Public helper locate supplies concrete releaseRoot/runtime path used by consumers.
- [x] Add meaningful temporary-package tests for global selection, explicit pin isolation, missing/tampered/conflicting selection, frozen workers after change and no config/data mutation.
- [x] Update bundled README/Skill/release docs, provenance and VERSION. Run focused and independent suites; independent code review.

### Task 2: Morsea adoption
- [x] External full backup and source/data/jobs hash baseline. Inspect live service ownership and task status read-only.
- [x] Replace redundant fixed links/manifest with global helper adapters; preserve legacy server invocation and build path. Update configuration to global and docs.
- [x] Package/install verified rc.10, activate global Skill/current using installer. No unrelated project changes.
- [x] Build isolated output; run temporary-data integration/browser checks including saved annotation without Agent and reload.
- [x] When no task active, stop only owned 8768 service normally, rebuild/restart, doctor and verify live toolbar/API read-only. Compare all protected hashes.

### Task 3: Final review and delivery
- [x] Independent reviewer checks concrete task/version integrity and integration boundaries; fix findings.
- [x] Report actual running URL, behavior, tests, and remaining limits. No commit/push/deploy unless separately requested.

## Decisions
2026-10-29: user directly authorized execution of the previously presented approach; no repeated approval gate. Work stays in current workspaces to preserve shared IDE context; edits scoped and existing dirty source snapshotted.

## Completion
2026-10-29: implementation and independent review passed. Local rc.10 globally activated; Morsea 8768 runs global with annotations. 2637 protected files unchanged, one empty annotation queue lock added. Consumer validation.html and toolkit implementation.md record exact evidence. No commit/push/remote release/deployment. Historical policy-mismatched requests reject continuation without record migration.
