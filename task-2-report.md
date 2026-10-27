# Task 2 implementation report

Status: implemented and verified locally, pending independent review. Base: `32860e30ec8e175df885f1898070326cce520dfe`. Workspace: `/Users/charles/Documents/codex/web-review-kit`. Python: 3.9.6, standard library only. No Morsea files, business fixtures, real jobs, remote settings, global Git/Codex configuration, browser UI, or later task-owned runtime files were changed.

## Files and interfaces

- `runtime/project_config.py`: exact shared `ProjectConfig` dataclass fields (`project_id`, `tool_version`, four `Path` roots/directories, `server`, `page_identity`, `browser_storage`, `guidance`, `codex`). Public `load_project_config(project_root: Path) -> ProjectConfig`; setup helper `setup_project(project_root: Path, options: dict)`; `ConfigError` with `exit_code`, `code`, optional `diff`; `CONFIG_VERSION=1`, `TOOL_VERSION` from the existing `VERSION`.
- `web-review.py`: thin `--project <root> setup|serve|version` entrypoint. Setup supports `--web-root`, `--data-dir`, `--jobs-dir`, `--host`, `--port`, `--base-path`, repeatable `--public-origin`, `--codex`/`--no-codex`, `--codex-bin`, `--model`. Other first-release commands belong to subsequent tasks and are not stubbed here.
- `schemas/project-config.schema.json`: explicit v1 JSON contract, path strings, argv arrays, shared-mode restrictions, fixed permission pair, optional model.
- `runtime/server.py`: appends optional `project_config=None` to the original `make_server` arguments; adds `serve_project(config: ProjectConfig) -> None` and configured health helper. Original unconfigured health and existing review routes remain compatible.
- `tests/test_project_config.py`, `tests/test_cli.py`: synthetic external projects and protocol-free service tests only.
- `task-2-report.md`: this report.

## Behavior and boundaries

All four runtime paths resolve relative to the project root, including Unicode, spaces and symlink project entrypoints. Writable config retains supplied relative paths. Host defaults to `127.0.0.1`; the configured listener supports explicit `0.0.0.0` shared mode only with HTTPS origins and a nonempty basePath. Shared mode rejects Codex. Configuration validates command lists as nonempty argv arrays, never shell strings; no browser request can choose a path or command. Codex permissions must be `approvalPolicy=never`, `sandbox=danger-full-access`. No model override is synthesized.

Setup creates only `review.config.json` using exclusive creation, never starts a service/task or creates review/job directories. Same explicit options leave the config byte-for-byte unchanged, preserving projectId and toolVersion pin even if the running toolkit has another version. Different existing options return exit 3, `configuration_conflict`, and a field-keyed `{existing, requested}` diff; no overwrite. Invalid or unsupported configuration returns exit 2. JSON command results carry `ok`, `projectId`, `toolVersion`, and either command output or an error code. Version reports the executing toolkit version; setup and service identity report the project pin.

Configured local health adds `projectId`, `toolVersion`, `schemaVersion=1`, a SHA-256 configuration identity, validated server settings, and Codex enabled mode, while retaining `root`/`data`. Shared health has the identity/build fields and no local directory values. A service is reusable only when full normalized configuration identity, paths and runtime mode match; mismatched runtime arguments are rejected. Port conflicts do not terminate or attach to the existing process. The synthetic CLI launch process is owned and terminated by its test.

The existing `CodexTasks` can be constructed with configured target project/data/jobs/executable when enabled; its prompt/session/model propagation remains explicitly owned by Task 5. No real Codex job was launched, and this report makes no claim of the generalized bridge or real-task acceptance. Config's model field is preserved for that later bridge. Original legacy `runtime/server.py` CLI remains a compatibility entrypoint; project-scoped use goes through `web-review.py`.

## RED evidence

Before adding implementation:

- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*config*.py'`: failed, one import error: `ModuleNotFoundError: No module named 'project_config'`.
- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_cli.py'`: failed, same missing-module import error.

The first test set pinned external project directories, Unicode/symlinks, unsupported versions, command/permission/shared validation, repeat setup, conflict diffs, real service identity checks and legacy/shared health. Additional checks after implementation cover default host, explicit model, actual project CLI startup, and wrong runtime port/executor rejection.

## GREEN evidence

- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*config*.py'`: 8 tests, OK (0.009s).
- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_cli.py'`: 10 tests, OK (4.118s).
- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_server.py'`: 37 tests, OK (29.104s), including inherited shared service, preservation/conflict, attachments and 64-connection burst cases.
- `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_codex_tasks.py'`: 15 tests, OK (18.514s), existing protocol substitute only. Full log: `/tmp/web-review-task2-codex-tests.log` (untracked temporary evidence).
- `python3 -m py_compile web-review.py runtime/project_config.py runtime/server.py`: exit 0.
- `python3 -m json.tool schemas/project-config.schema.json`: exit 0.
- `git diff --check`: exit 0.

Total targeted Python tests: 70 passed. No browser tests rerun because no overlay/UI source changed; the full all-tests discovery includes the browser protocol integration and was deliberately not rerun for this scoped configuration change. Static HTTP CLI startup and shared health are covered directly with isolated synthetic projects. No production deployment, installation, package publication, business migration or design acceptance is claimed.
