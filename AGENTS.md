# Web Review Kit collaboration rules

Read `README.md`, `docs/source-map.md` and the applicable approved implementation task before changing the toolkit.

- `runtime/` is the unique toolkit runtime source. Consumer copies are installed artifacts, not parallel implementations. Preserve public review UI/API, attachment, offline and shared contracts unless an approved task explicitly changes them.
- This is a private team package for static HTML and build output. This round formally validates macOS only, retaining HTTPS shared review through isolated local checks. Do not add Linux installation/acceptance, server deployment, framework dev servers, Windows promises or new agent launchers implicitly.
- Keep tests in `tests/`, synthetic pages and protocol substitutes in test support. Browser support must launch isolated Chrome profiles. Never read business components or copy formal comments, screenshots, attachments or private assets into fixtures or commits.
- Back up the complete review data directory outside the consumer workspace before migrations or recovery. Preserve fields, anchors, screenshots, attachments and timestamps. Updates use a freshly read `updatedAt` as `expectedUpdate`; mark verified implementation `changed`, leave acceptance to the user. Never replay an old snapshot over a live service.
- Do not start, stop, retry, steer, resume or mutate real Codex jobs while testing extraction. Inspect persisted status read only. Existing historical task records remain in the original project.
- The inherited local bridge's authorized permission pair is `approval_policy=never` and `sandbox_mode=danger-full-access`; do not alter global Codex configuration. Shared and offline review must not activate Codex.
- Run the documented independent test suite and relevant browser checks before claiming success. Report actual checks and limitations; interaction verification does not imply design acceptance or production readiness.
- Keep source provenance and fixed dependency hashes current. Preserve the html2canvas license and the documented isolation stacking-context patch on upgrade.
- Data, browser profiles, jobs, logs, backups and artifacts are excluded from Git. Releases must use a versioned manifest and deterministic package after the corresponding packaging task exists. Do not infer remote publication, consumer upgrades, migration or deployment authorization from local implementation work.
