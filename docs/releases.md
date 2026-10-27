# Fixed-version installation for the first release

The first release preserves existing review and Codex behavior while adding project configuration, a reusable Skill and a verified fixed-version installation. Validate it in Morsea and one independent static project; preserve original comments, evidence and task history. Formal data migration, production deployment, multi-platform support and advanced version management are outside this release's acceptance scope.

Use Python 3.9+ on macOS and the single installation root **`/Users/charles/.local/share/web-review-kit`**. The next candidate is **`0.1.0-rc.3`**. VERSION alone does not mean it has been published; run the download commands only after candidate publication is recorded.

## Install the exact candidate

The repository is private: `charlesdguo-cell/web-review-kit`. Download uses the host's existing `gh` login; credentials are never bundled.

```sh
review_install=/Users/charles/.local/share/web-review-kit
review_bootstrap="$(mktemp -d)"
gh release download v0.1.0-rc.3 --repo charlesdguo-cell/web-review-kit --pattern 'web-review-kit-0.1.0-rc.3.tar.gz*' --dir "$review_bootstrap"
(cd "$review_bootstrap" && shasum -a 256 -c web-review-kit-0.1.0-rc.3.tar.gz.sha256)
tar -xzf "$review_bootstrap/web-review-kit-0.1.0-rc.3.tar.gz" -C "$review_bootstrap"
python3 "$review_bootstrap/scripts/install.py" --archive "$review_bootstrap/web-review-kit-0.1.0-rc.3.tar.gz" --install-root "$review_install"
```

Stop on any download or checksum failure. The installer returns absolute `installRoot`, `releaseRoot` and `skill` paths. Runtime, frontend assets and Skill live together under `releases/0.1.0-rc.3/`; a receipt records the manifest hash. Identical repeat installation is safe; local managed-file changes or conflicting content are rejected. Installation does not change project pins/data/jobs, start services, or modify global agent configuration.

## Configure and use a project

For explicit project-local discovery, append `--skill-link /absolute/consumer/.agents/skills/web-review` to the installer command. Existing paths are preserved on conflict. Alternatively invoke the installed helper directly; keep the complete release layout rather than copying the Skill alone.

```sh
review_release=/Users/charles/.local/share/web-review-kit/releases/0.1.0-rc.3
python3 "$review_release/web-review.py" --project /absolute/consumer setup --web-root public --no-codex
python3 "$review_release/skills/web-review/scripts/review.py" --project /absolute/consumer locate
python3 "$review_release/skills/web-review/scripts/review.py" --project /absolute/consumer version
python3 "$review_release/skills/web-review/scripts/review.py" --project /absolute/consumer serve
```

Setup writes project configuration only. Read the located workflow, verify matching health and the actual toolbar before reporting a running review URL. Before enabling the requested local Codex bridge, fill consumer-owned source/build/check guidance and run doctor. Workers receive the verified install root, pinned Skill and frozen request path; they consume the original batch without dispatching another task. `version`, doctor and health distinguish actual runtime version from the project's required version.

Keep schema-v1 data in its existing directory. Ordinary installation, reads, doctor and service startup do not activate metadata, rewrite timestamps or migrate comments. Preserve screenshots, attachments and old tasks. Browser export remains `prototype-review` v2; CLI evidence export is an unversioned raw comments array plus an evidence map.

## Existing consumer launcher

Keep consumer-owned README and integration tests. After the authorized backup and preservation of the original launcher, link only `tools/review/server.py` to the packaged entry:

```sh
ln -s /Users/charles/.local/share/web-review-kit/releases/0.1.0-rc.3/compat/server.py /absolute/consumer/tools/review/server.py
python3 /absolute/consumer/tools/review/server.py --open --codex
```

The adapter infers the consumer from the unresolved symlink path even outside its cwd; `--project` is also supported. It retains legacy root/data/port flags as process-local overrides. Unconfigured synthetic tests may directly use the verified package's `runtime/server.py --root ... --data ... --port ...` with Codex disabled. Import the packaged runtime in consumer tests; do not maintain another runtime source copy.

## Experimental capabilities deferred from first-release acceptance

The existing update/rollback code and historical candidate compatibility are retained as experimental implementation, not the recommended first-release workflow. Automatic upgrades, rollback hardening, cross-root relocation and old-candidate transitions are deferred to separate work. Do not use comment processing as permission to change versions or entrypoints.

The completed small guard binds installed-helper update/rollback to its own verified root before dispatch; mismatching global or command-level roots are rejected. Source/API activation requires explicit `install_root`, and services/jobs must be stopped normally. Cross-root relocation is unsupported. Do not overwrite unmanaged discovery paths. rc.1 and rc.2 archives/tags remain historical evidence; no additional legacy compatibility is required for this first-release gate.

Maintainer packaging uses `python3 scripts/package.py --destination /absolute/output`; VERSION is the only version input. The closed manifest covers shipped files, hashes, schema/workflow contracts, browser export v2 and the fixed html2canvas patch. Packaging and local tests do not imply publication, consumer integration, real Codex success or user acceptance.
