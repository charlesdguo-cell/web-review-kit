# Global Web Review runtime

User approved on 2026-10-29: maintain the toolkit globally; projects retain configuration and data. Existing running work must keep its concrete version. Morsea adopts this locally and receives content annotations.

## Design
- Global installation has one explicit `current` symlink to a verified release. No highest-version search or downloads during resolution. A deliberate installer `--activate-global` operation updates it atomically. Global Skill discovery points through current; conflicting unmanaged paths are preserved.
- Project `toolVersion: global` follows this default; explicit versions retain existing pin behavior. New setup defaults to global only through a verified installation with a current selection; source-checkout setup remains pinned for development.
- Loaded runtime/config, service and frozen tasks carry a concrete version. Changing current affects the next invocation/restart, not a running task. A frozen helper request resolves its recorded release even if current moved, while verifying project identity, requested policy, receipt and Skill. No automatic job dispatch.
- Missing/tampered/default-outside-installation fails clearly; no guessing. Old rc.1-rc.9 manifests still verify unchanged.
- Python 3.9 stdlib, macOS validation, existing data/API/offline/shared contracts preserved. Local rc.10 package only; no remote publication/deployment.

## Approaches
A global Skill alone leaves runtime pins unchanged. Updating each project repeats maintenance. Selected approach: one global default with optional project pins, unified resolution for CLI/build/runtime and immutable per-task version.

## Morsea
Remove project Skill and redundant fixed release links/manifest, retaining minimal compatibility launch/build adapters to the global helper. Preserve project identity, 8768, storage keys, data/jobs and build/check guidance. Back up all formal review data and task records externally before service switch; verify hashes. Build and test against temporary data before replacing the local service. Existing unrelated dirty source files stay byte-identical.
