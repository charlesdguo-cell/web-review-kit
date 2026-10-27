# Private candidate installation and pin changes

Python 3.9+; this candidate validates macOS only. User design acceptance and real Codex acceptance remain pending. The private source and prerelease repository is `charlesdguo-cell/web-review-kit`. Existing `gh` authentication supplies access; no token belongs in a bundle, project configuration or command argument.

## Bootstrap from an exact candidate

Choose an explicit absolute installation root. These illustrative shell variables are task-local and contain no credentials:

```sh
review_install="$HOME/Library/Application Support/web-review-kit"
review_bootstrap="$(mktemp -d)"
gh release download v0.1.0-rc.1 --repo charlesdguo-cell/web-review-kit --pattern 'web-review-kit-0.1.0-rc.1.tar.gz*' --dir "$review_bootstrap"
(cd "$review_bootstrap" && shasum -a 256 -c web-review-kit-0.1.0-rc.1.tar.gz.sha256)
tar -xzf "$review_bootstrap/web-review-kit-0.1.0-rc.1.tar.gz" -C "$review_bootstrap"
python3 "$review_bootstrap/scripts/install.py" --archive "$review_bootstrap/web-review-kit-0.1.0-rc.1.tar.gz" --install-root "$review_install"
```

Stop if download or checksum verification fails. Download only the authorized exact repository/tag; SHA-256 detects corruption, not malicious replacement by a repository publisher. Subsequent explicit downloads may use `scripts/install.py --github-version 0.1.0-rc.1 --install-root ...` from an already trusted package. It never chooses latest and reports missing private access. The installer returns `installRoot`, `releaseRoot`, and `skill`.

`INSTALL/releases/VERSION/` contains the complete `runtime/`, `skills/web-review/`, CLI, compatibility entry, docs and schemas. `INSTALL/receipts/VERSION.json` records the manifest hash. Repeating the identical install is idempotent; changed managed files, manifests or an existing version with different content cause conflicts. Releases are never overwritten. No global agent configuration, consumer pin, data or jobs are changed by installation.

## Discovery, setup and workers

For explicit project-local Codex discovery, append `--skill-link /absolute/consumer/.agents/skills/web-review` to the installer command. This creates a symlink into the chosen complete release. Existing links/files are preserved on conflict; changing discovery is an explicit operation. Other agents can invoke the helper by its returned absolute path. Detached Skill copies cannot resolve runtimes. The helper derives `INSTALL` only from a verified `INSTALL/releases/VERSION` layout and matching receipt; otherwise supply `--install-root` explicitly. It does not search a machine or choose newest.

```sh
python3 "$review_install/releases/0.1.0-rc.1/web-review.py" --project /absolute/consumer setup --web-root public --no-codex
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer locate
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer version
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer serve
```

Read the located workflow. Setup alone creates configuration; a requested usable review entry also requires serve, matching health and toolbar inspection. A comment-processing request never authorizes installation/upgrades. Configured packaged workers freeze verified `installRoot` and `skillPath`; their prompt supplies both and the immutable request. Use `--request /absolute/job/request.json` on helper locate and data commands. Source checkout workers have no installed root and are not packaged-worker acceptance evidence.

## Update and rollback

Install the explicitly selected target first. Stop the project's own service normally and wait for all jobs to finish; the tool never force-kills a service or worker. Then run either operation through the current pinned helper:

```sh
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer update --target "$review_install/releases/0.1.0-rc.1"
python3 /absolute/consumer/.agents/skills/web-review/scripts/review.py --project /absolute/consumer rollback --target /absolute/install/releases/EXACT-PREVIOUS-VERSION
```

Both atomically replace only `review.config.json.toolVersion`; other config fields remain, and no service/job starts. Data writer lock, job lock and persisted active job state block switching. Existing installed source/target releases must be intact. Frontend assets are served from the same resolved release as the backend; the old service must close before the pin changes. No shared mutable runtime directory or global current pointer exists. Each project has its own pin/data.

Schema v1 remains unchanged. Reads, doctor, install and activation do not create `meta.json`, rewrite comments or timestamps, or run migrations. Corrupt/foreign metadata and unsupported schemas fail closed without changing the original directory. There is no schema migration engine in this candidate: a required migration is rejected, never attempted implicitly. Back up full data outside the project before any future separately authorized migration. Rollback changes tool files/pin only and retains comments created after upgrade.

`version`, `doctor`, and health report actual `toolVersion`, project `requiredToolVersion`, and `versionMatches`. Doctor checks workflow compatibility; packaged execution verifies its manifest/receipt. A raw checkout with mismatched VERSION cannot claim the requested version or serve that project.

## Consumer legacy launcher

Task 8 can keep the consumer-owned `tools/review/README.md` and integration tests, and replace only the runtime launcher with a symlink:

```sh
ln -s /absolute/install/releases/0.1.0-rc.1/compat/server.py /absolute/consumer/tools/review/server.py
python3 /absolute/consumer/tools/review/server.py --open --codex
```

Back up and remove only the previously authorized launcher before creating the link; `ln` does not overwrite. The packaged adapter obtains the consumer from the unresolved symlink path, independent of cwd; explicit `--project` is also supported. It resolves that consumer's current pin before serving and retains `--root`, `--data`, `--port`, `--base-path`, `--public-origin`, `--bind-host`, `--codex-bin` as process-local overrides. For unconfigured isolated synthetic tests, use the verified package's `runtime/server.py --root ... --data ... --port ...` directly with Codex disabled. Consumer tests should import packaged runtime via the verified resolver, not preserve another runtime source tree. Compatibility is an installed package artifact; no toolkit source is maintained in the consumer.

## Maintainer packaging

```sh
python3 scripts/package.py --destination /absolute/output
PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_release_manager.py'
```

VERSION is the only release version input. Output contains a deterministic tar.gz, its SHA-256 sidecar and release-manifest.json. Closed file allowlist excludes project data, task logs, credentials, business assets and test artifacts. The manifest covers every shipped file, storage/export/workflow contracts, source tree digest and the fixed html2canvas patch/hash. Its own integrity is anchored by the archive checksum and local install receipt. Keep candidate tag, source commit, archive hash and remote private proof in the release evidence. Publication is a separate explicitly authorized action, not part of package/install.
