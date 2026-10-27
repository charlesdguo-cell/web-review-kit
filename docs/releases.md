# Private candidate installation and pin changes

Python 3.9+; this candidate validates macOS only. User design acceptance and real Codex acceptance remain pending. The private source and prerelease repository is `charlesdguo-cell/web-review-kit`. Existing `gh` authentication supplies access; no token belongs in a bundle, project configuration or command argument.

## Bootstrap from an exact candidate

Choose an explicit absolute installation root. These illustrative shell variables are task-local and contain no credentials:

```sh
review_install="$HOME/Library/Application Support/web-review-kit"
review_bootstrap="$(mktemp -d)"
gh release download v0.1.0-rc.2 --repo charlesdguo-cell/web-review-kit --pattern 'web-review-kit-0.1.0-rc.2.tar.gz*' --dir "$review_bootstrap"
(cd "$review_bootstrap" && shasum -a 256 -c web-review-kit-0.1.0-rc.2.tar.gz.sha256)
tar -xzf "$review_bootstrap/web-review-kit-0.1.0-rc.2.tar.gz" -C "$review_bootstrap"
python3 "$review_bootstrap/scripts/install.py" --archive "$review_bootstrap/web-review-kit-0.1.0-rc.2.tar.gz" --install-root "$review_install"
```

Stop if download or checksum verification fails. Download only the authorized exact repository/tag; SHA-256 detects corruption, not malicious replacement by a repository publisher. Subsequent explicit downloads may use `scripts/install.py --github-version 0.1.0-rc.2 --install-root ...` from an already trusted package. It never chooses latest and reports missing private access. The installer returns `installRoot`, `releaseRoot`, and `skill`.

`INSTALL/releases/VERSION/` contains the complete `runtime/`, `skills/web-review/`, CLI, compatibility entry, docs and schemas. `INSTALL/receipts/VERSION.json` records the manifest hash. Repeating the identical install is idempotent; changed managed files, manifests or an existing version with different content cause conflicts. Releases are never overwritten. No global agent configuration, consumer pin, data or jobs are changed by installation.

## Discovery, setup and workers

For explicit project-local Codex discovery, append `--skill-link /absolute/consumer/.agents/skills/web-review` to the installer command. This creates a symlink into the chosen complete release. Existing links/files are preserved on conflict; changing discovery is an explicit operation. Other agents can invoke the helper by its returned absolute path. Detached Skill copies cannot resolve runtimes. The helper derives `INSTALL` only from a verified `INSTALL/releases/VERSION` layout and matching receipt; otherwise supply `--install-root` explicitly. It does not search a machine or choose newest.

```sh
python3 "$review_install/releases/0.1.0-rc.2/web-review.py" --project /absolute/consumer setup --web-root public --no-codex
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer locate
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer version
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer serve
```

Read the located workflow. Setup alone creates configuration; a requested usable review entry also requires serve, matching health and toolbar inspection. A comment-processing request never authorizes installation/upgrades. Configured packaged workers freeze verified `installRoot` and `skillPath`; their prompt supplies both and the immutable request. Use `--request /absolute/job/request.json` on helper locate and data commands. Source checkout workers have no installed root and are not packaged-worker acceptance evidence.

## Update and rollback

Install the explicitly selected target first. Stop the project's own service normally and wait for all jobs to finish; the tool never force-kills a service or worker. Then run either operation through the current pinned helper:

```sh
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer update --target "$review_install/releases/0.1.0-rc.2"
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer rollback --target /absolute/install/releases/EXACT-PREVIOUS-VERSION
```

The installed calling runtime determines the installation root. Targets from another root, including attempts to override that root, are rejected before pin changes. The existing pinned release in that root must also verify. Source checkout/API callers must supply explicit root context: `activate_release(config, target, install_root=Path("/absolute/install"))`, or `web-review.py --project /absolute/consumer update --target /absolute/install/releases/VERSION --install-root /absolute/install`. The target never supplies this context. Missing current pins require a separately planned adoption, not an implicit cross-root switch.

Both atomically replace only `review.config.json.toolVersion`; other config fields remain, and no service/job starts. Data writer lock, job lock and persisted active job state block switching. Existing installed source/target releases must be intact. Frontend assets are served from the same resolved release as the backend; the old service must close before the pin changes. No shared mutable runtime directory or global current pointer exists. Each project has its own pin/data.

Schema v1 remains unchanged. Reads, doctor, install and activation do not create `meta.json`, rewrite comments or timestamps, or run migrations. Corrupt/foreign metadata and unsupported schemas fail closed without changing the original directory. There is no schema migration engine in this candidate: a required migration is rejected, never attempted implicitly. Back up full data outside the project before any future separately authorized migration. Rollback changes tool files/pin only and retains comments created after upgrade.

`version`, `doctor`, and health report actual `toolVersion`, project `requiredToolVersion`, and `versionMatches`. Doctor checks workflow compatibility; packaged execution verifies its manifest/receipt. A raw checkout with mismatched VERSION cannot claim the requested version or serve that project.

## Consumer legacy launcher

Task 8 can keep the consumer-owned `tools/review/README.md` and integration tests, and replace only the runtime launcher with a symlink:

```sh
ln -s /absolute/install/releases/0.1.0-rc.2/compat/server.py /absolute/consumer/tools/review/server.py
python3 /absolute/consumer/tools/review/server.py --open --codex
```

Back up and remove only the previously authorized launcher before creating the link; `ln` does not overwrite. The packaged adapter obtains the consumer from the unresolved symlink path, independent of cwd; explicit `--project` is also supported. It resolves that consumer's current pin before serving and retains `--root`, `--data`, `--port`, `--base-path`, `--public-origin`, `--bind-host`, `--codex-bin` as process-local overrides. For unconfigured isolated synthetic tests, use the verified package's `runtime/server.py --root ... --data ... --port ...` directly with Codex disabled. Consumer tests should import packaged runtime via the verified resolver, not preserve another runtime source tree. Compatibility is an installed package artifact; no toolkit source is maintained in the consumer.

## Maintainer packaging

```sh
python3 scripts/package.py --destination /absolute/output
PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_release_manager.py'
```

VERSION is the only release version input. Output contains a deterministic tar.gz, its SHA-256 sidecar and release-manifest.json. Closed file allowlist excludes project data, task logs, credentials, business assets and test artifacts. The manifest covers every shipped file, storage/workflow contracts and `exportFormats: [2]` for the actual versioned browser `prototype-review` envelope, source tree digest and the fixed html2canvas patch/hash. Its own integrity is anchored by the archive checksum and local install receipt. Keep candidate tag, source commit, archive hash and remote private proof in the release evidence. Publication is a separate explicitly authorized action, not part of package/install.


## Transition from the immutable rc.1 candidate

Published rc.1 incorrectly declared browser export v1, although its browser already exported v2. rc.2 declares v2; CLI evidence export remains a bare comments array plus a separate evidence map with no version field. The rc.2 verifier recognizes rc.1 only by its exact original manifest SHA-256 `50cc67d2ca9c36b066253721f87ccd41b5be6f9c522e851803cc5a2656b3fc88`; historical bytes remain unchanged. This is a narrow transition exception, not acceptance of v1 metadata on other releases.

The old rc.1 helper and compat verifier cannot read rc.2's corrected metadata. For a fresh consumer (including Task 8), install and register rc.2 directly. For an existing rc.1 consumer, install rc.2 into the **same absolute root** and use rc.2's CLI directly to activate the project; explicitly replace only a discovery/compat symlink that you have verified points to the old managed release, with a symlink to rc.2. Do not leave rc.1 entrypoints after activation. This is an explicit host-entry replacement, not a root relocation; a newer rc.2 host can resolve an older rc.1 pin. Installer `--skill-link` still refuses any conflicting path and never silently retargets or overwrites it.

Example managed-link replacement (only after checking each symlink with `readlink` against the known rc.1 release):

```sh
readlink /absolute/consumer/.agents/skills/web-review
readlink /absolute/consumer/tools/review/server.py
# Once both are confirmed symlinks to this installation's rc.1, explicitly replace them:
unlink /absolute/consumer/.agents/skills/web-review
ln -s /absolute/install/releases/0.1.0-rc.2/skills/web-review /absolute/consumer/.agents/skills/web-review
unlink /absolute/consumer/tools/review/server.py
ln -s /absolute/install/releases/0.1.0-rc.2/compat/server.py /absolute/consumer/tools/review/server.py
python3 /absolute/install/releases/0.1.0-rc.2/web-review.py --project /absolute/consumer update --target /absolute/install/releases/0.1.0-rc.2
```

Do not run `unlink` on an unmanaged path or ordinary file; stop and preserve it. Stop the consumer service and let active jobs finish before switching. Keep rc.1's version directory/archive/tag for evidence and rollback. An rc.2 helper can route a rolled-back rc.1 pin, but subsequent updates must use rc.2's direct CLI because rc.1's own update implementation still predates these fixes.
