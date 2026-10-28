# Global installation and optional project pins

Use Python 3.9+ on macOS and the installation root **`~/.local/share/web-review-kit`**. This release is **`0.1.0-rc.11`**. It adds one global runtime default and activates it by default during installation. The preceding rc.10 was a local candidate; it is retained unchanged on machines that installed it. Verify remote availability through the exact GitHub release rather than inferring publication from a local VERSION file.

rc.9 added inline `我：` / `Agent：` annotation authorship. rc.8 introduced independent selected-text content annotations, the aligned sidebar, persistent Agent discussions and protected page refresh. Historical rc.1–rc.9 packages retain their exact inventories, hashes and receipts.

## Install and select the global default

Use an explicitly selected local archive. Installation validates the closed manifest and records a receipt; identical repeat installation is safe. Existing modified releases and unmanaged discovery paths are preserved and rejected.

```sh
python3 /absolute/verified-bundle/scripts/install.py \
  --archive /absolute/web-review-kit-0.1.0-rc.11.tar.gz \
  --install-root "$HOME/.local/share/web-review-kit" \
  --skill-link "$HOME/.agents/skills/web-review"
```

Installation selects the verified release via `INSTALL/current` by default; `--activate-global` is still accepted but no longer required. With the explicit `--skill-link` above, the Skill points at `INSTALL/current/skills/web-review`. A verified old fixed-release Skill link from the same installation may be converted to this stable link; an unrelated link or actual directory is a conflict. Selection validates the target and discovery destination before switching.

Use `--no-activate-global` to install a release without changing `current` (for example, to retain a version for an explicit project pin). With that opt-out, an explicit `--skill-link` targets the installed fixed release and preserves conflicting existing links. Omitting `--skill-link` leaves discovery paths untouched in either mode. The two activation flags are mutually exclusive.

This operation never edits a consumer configuration or review record, restarts services, or starts jobs. Global agent settings are not modified. Each running service/task continues with its concrete startup release; newly invoked commands and restarted services use the new default. Keep previous releases installed while their services or frozen tasks still need them.

Download the exact version from private repository `charlesdguo-cell/web-review-kit` using the host's existing `gh` login, verify the accompanying SHA-256 file, and use that archive's installer. Older installers do not provide the new default. No credentials are bundled.

```sh
(
set -eu
review_download=$(mktemp -d)
gh release download v0.1.0-rc.11 --repo charlesdguo-cell/web-review-kit \
  --pattern 'web-review-kit-0.1.0-rc.11.tar.gz*' --dir "$review_download"
cd "$review_download"
shasum -a 256 -c web-review-kit-0.1.0-rc.11.tar.gz.sha256
mkdir bundle
tar -xzf web-review-kit-0.1.0-rc.11.tar.gz -C bundle
python3 bundle/scripts/install.py \
  --archive "$review_download/web-review-kit-0.1.0-rc.11.tar.gz" \
  --install-root "$HOME/.local/share/web-review-kit" \
  --skill-link "$HOME/.agents/skills/web-review"
)
```

The subshell stops if download or checksum validation fails. A Skill file alone is not a complete installation; this bundle supplies the verified runtime and its helper together. When installing historical rc.1–rc.9 bundles with this installer, pass `--no-activate-global`: those bundles support exact pins but do not declare global-selection capability.

## Global Skill

The global `~/.agents/skills/web-review` is sufficient across projects. Consumers do not need their own Skill copy, runtime copy or fixed-version links. The packaged Skill includes default comment delivery for HTML reports, static webpages, prototypes and demos, preserving offline reading and explicit opt-outs.

Codex discovers Skills automatically; restart Codex if the entry is missing. Verify discovery and use the helper's `locate`/`version` results, rather than inferring the active runtime from the Skill's visible text. `current` must reference a verified release under this installation with manifest capability `runtimeSelection: {"global": 1}`; missing, unsupported or tampered selection fails explicitly. Historical releases without that capability remain available for explicit pins. The resolver never scans for the newest release or downloads a fallback.

## Configure and use a project

```sh
review_helper="$HOME/.agents/skills/web-review/scripts/review.py"
python3 "$review_helper" --project /absolute/consumer setup --web-root public
python3 "$review_helper" --project /absolute/consumer locate
python3 "$review_helper" --project /absolute/consumer version
python3 "$review_helper" --project /absolute/consumer doctor
python3 "$review_helper" --project /absolute/consumer serve
```

New setup through an installation with a selected default writes `"toolVersion": "global"`. An exact version such as `"0.1.0-rc.9"` remains an optional project override. Existing configurations are preserved; adopting global mode is an explicit project configuration change. Source-checkout setup stays pinned to its development version. Keep project identity, web/data/jobs directories, port, storage keys and source/build/check guidance in `review.config.json`.

The helper resolves one concrete release for each invocation and returns `releaseRoot`, `runtimeRoot`, `installRoot`, `toolVersion` and `toolVersionPolicy`. Builds copy offline assets from that concrete runtime. Consumers that retain a legacy launch command may use a thin adapter: locate once, then run that release's `compat/server.py --project /absolute/consumer` with the existing flags. No consumer-managed installation manifest is necessary. Frozen deployment bundles must record a concrete version rather than depending on a developer's global default.

Setup writes configuration only. It never launches a service or processes comments. Local setup enables Codex by default; fill the real source/build/check guidance, resolve the executable and run doctor. Before reporting complete setup verify doctor `ready=true`, matching live health with `codexEnabled=true`, bridge API `available=true` and the actual toolbar. Use `--no-codex` for explicit comments-only use. Shared/offline review keeps Codex disabled.

Keep schema-v1 data in its existing directory, including screenshots, attachments and historical jobs. Reads, doctor and service startup do not migrate data or rewrite record timestamps. Back up the complete data directory externally before consumer adoption. Stop only the owned service normally and verify there are no active/pending tasks before restarting it; startup must not be used to dispatch previously queued work accidentally.

## Frozen tasks and explicit pins

Workers receive a verified concrete release, absolute Skill path, install root and immutable request. The helper's `--request` resolves that frozen release before consulting the global default, and verifies identity/policy, receipt and Skill. Changing `current` cannot retarget that worker. Its App Server environment carries `WEB_REVIEW_HELPER` for the verified concrete helper and `WEB_REVIEW_REQUEST_PATH` for its saved request. Helper `locate` validates this context for build resolution (including annotation tasks); it never broadens data-command authorization. Consumer build adapters should inherit these variables. Synthetic fixtures for a different project must clear inherited request context instead of reusing a real task contract. Explicit project pins continue to select their own release regardless of the global default.

An already running service retains its loaded runtime and static resources until restarted. A global change during startup is rejected when the selected release no longer matches. Restart/build together when adopting a new default so HTTP and offline deliverables use the same release. No hot replacement or automatic restart is performed.

The older per-project `update`/`rollback` commands remain experimental. They require normal service/job shutdown and verify installation identity. Cross-root relocation, automatic network updates, data migration and production deployment remain outside this feature. Comment processing never grants permission to change global selection, project policy or entrypoints.

## Packaging and validation

Use `python3 scripts/package.py --destination /absolute/output`; VERSION is the only version input. The deterministic closed manifest covers runtime/Skill files, hashes, schema/workflow contracts, browser export v2 and the unchanged html2canvas dependency/license/patch. Use the new bundle's installer for global activation; old installers do not implement this option.

Run the independent Python discovery and relevant isolated headless browser suites from README. Global-selection tests use temporary installations, synthetic projects and frozen requests; they do not modify real review data or launch real Codex jobs. Local checks do not establish real-model behavior, remote publication, deployment or user acceptance.
