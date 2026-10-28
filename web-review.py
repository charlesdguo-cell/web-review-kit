#!/usr/bin/env python3
"""Thin project-scoped entrypoint for the Web Review Kit."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from project_config import ConfigError, TOOL_VERSION, load_project_config, setup_project
from server import serve_project
from review_data import ReviewClient, ReviewDataError
from data_lock import DataLockError
from data_version import DataVersionError
from release_manager import ReleaseError, activate_release, installed_root, validate_runtime, resolve_frozen_release


def runtime_status(config=None, frozen=False):
    root = Path(__file__).resolve().parent
    required = config.tool_version if config else None
    workflow = json.loads((root / 'skills/web-review/workflow.json').read_text())
    compatible = type(workflow.get('workflowVersion')) is int and workflow['workflowVersion'] == 1
    installed = False
    if (root / 'release-manifest.json').exists():
        installed_root(root)
        installed = True
    if config and config.version_policy == 'global':
        validate_runtime(config, release=root, follow_current=not frozen)
    return {'requiredToolVersion': required, 'versionMatches': required in (None, TOOL_VERSION),
            'toolVersionPolicy': config.version_policy if config else None,
            'workflowVersion': workflow.get('workflowVersion'), 'workflowCompatible': compatible,
            'verifiedInstallation': installed}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ConfigError(message, code='invalid_arguments')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--review-url', help='Explicit review service base URL; data operations verify its projectId')
    parser.add_argument('--request', type=Path, help='Frozen worker request; binds its recorded installed runtime and endpoint')
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    setup = commands.add_parser('setup', help='Create project configuration; local Codex is enabled by default')
    for flag in ('web-root', 'data-dir', 'jobs-dir', 'host', 'base-path', 'codex-bin', 'model'):
        setup.add_argument('--' + flag)
    setup.add_argument('--port', type=int)
    setup.add_argument('--public-origin', action='append')
    toggle = setup.add_mutually_exclusive_group()
    toggle.add_argument('--codex', action='store_true', default=None, help='Enable local Codex bridging explicitly')
    toggle.add_argument('--no-codex', dest='codex', action='store_false', help='Use comments only; shared mode defaults to this')
    commands.add_parser('serve', help='Serve the configured project')
    commands.add_parser('version', help='Report toolkit version')
    commands.add_parser('doctor', help='Check environment, protocol and auth without inference')
    for name in ('update', 'rollback'):
        switch = commands.add_parser(name, help='Activate an explicitly installed release while service/jobs are stopped')
        switch.add_argument('--target', type=Path, required=True)
        switch.add_argument('--install-root', type=Path, help='Required for source checkout activation; installed callers derive and enforce their own root')
    commands.add_parser('list', help='List reviews from the configured service')
    show = commands.add_parser('show', help='Read a frozen review snapshot')
    show.add_argument('--id', required=True)
    export = commands.add_parser('export', help='Export raw reviews and own-service evidence')
    export.add_argument('--output', type=Path, required=True)
    mark = commands.add_parser('mark-changed', help='Write verified implementation with frozen evidence')
    mark.add_argument('--snapshot', type=Path, required=True)
    mark.add_argument('--id', required=True)
    mark.add_argument('--resolution-file', type=Path, required=True)
    config = None
    result = {'ok': False, 'projectId': None, 'toolVersion': TOOL_VERSION}
    try:
        args = parser.parse_args(argv)
        frozen = None
        if args.request is not None:
            if args.command not in ('version', 'list', 'show', 'export', 'mark-changed'):
                raise ConfigError('--request is supported only for existing worker data/version operations', code='invalid_arguments')
            frozen = json.loads(args.request.read_text())
            host = Path(__file__).resolve().parent
            install = installed_root(host)
            if (not isinstance(frozen, dict) or not isinstance(frozen.get('executionConfig'), dict) or
                    not isinstance(frozen.get('reviewUrl'), str) or not frozen['reviewUrl'].strip()):
                raise ReleaseError('Incomplete frozen worker request', 'request_conflict')
            if resolve_frozen_release(args.project, install, frozen['executionConfig'], frozen.get('project')) != host:
                raise ReleaseError('Frozen worker runtime differs from this CLI', 'request_conflict')
            if args.review_url is not None and args.review_url.rstrip('/') != frozen['reviewUrl'].rstrip('/'):
                raise ReleaseError('Review URL differs from the frozen request', 'request_conflict')
            if args.command != 'version':
                args.review_url = frozen['reviewUrl']
        if args.review_url is not None and args.command not in ('list', 'show', 'export', 'mark-changed'):
            raise ConfigError('--review-url is supported only for review data operations', code='invalid_arguments')
        if args.command == 'version':
            if (args.project / 'review.config.json').exists():
                config = load_project_config(args.project)
            value = {'command': 'version', **runtime_status(config, frozen=frozen is not None)}
        elif args.command == 'setup':
            result.update(runtime_status())
            if (args.project / 'review.config.json').exists():
                config = load_project_config(args.project)
                if config.version_policy == 'global':
                    runtime_status(config)
            config, created = setup_project(args.project, vars(args))
            value = {'command': 'setup', 'created': created}
        else:
            config = load_project_config(args.project)
            status = runtime_status(config, frozen=frozen is not None)
            result.update(status)
            if args.command in ('update', 'rollback'):
                value = activate_release(config, args.target, install_root=args.install_root)
                value.update(command=args.command, runningToolVersion=TOOL_VERSION)
                print(json.dumps(value, ensure_ascii=False), flush=True)
                return 0
            if args.command != 'doctor' and (not status['versionMatches'] or not status['workflowCompatible']):
                raise ReleaseError('Runtime version/workflow differs from project requirement', 'version_conflict')
            if args.command == 'serve':
                serve_project(config)
                return 0
            if args.command == 'doctor':
                from codex_doctor import doctor
                value = {'command': 'doctor', **doctor(config)}
                result.update(ok=value['ready'], projectId=config.project_id, **value)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                return 0 if value['ready'] else 2
            base_url = args.review_url if args.review_url is not None else 'http://127.0.0.1:' + str(config.server['port']) + config.server['basePath']
            client = ReviewClient(base_url, config.project_id)
            value = {'command': args.command}
            if args.command == 'list':
                value['comments'] = client.list()
            elif args.command == 'show':
                value['comment'] = client.show(args.id)
            elif args.command == 'export':
                value['export'] = client.export(args.output)
            elif args.command == 'mark-changed':
                snapshot = json.loads(args.snapshot.read_text(encoding='utf-8'))
                if isinstance(snapshot, dict) and 'comment' in snapshot:
                    if snapshot.get('projectId', config.project_id) != config.project_id:
                        raise ReviewDataError('Snapshot belongs to a different project', 'project_conflict', 3)
                    snapshot = snapshot['comment']
                if not isinstance(snapshot, dict) or str(snapshot.get('id')) != args.id:
                    raise ReviewDataError('--id must match the frozen snapshot id')
                resolution = args.resolution_file.read_text(encoding='utf-8')
                value['comment'] = client.mark_changed(snapshot, resolution)
        result.update(ok=True, **value)
        return_code = 0
    except (ReviewDataError, DataLockError, DataVersionError, ReleaseError) as error:
        result.update(error=error.code, message=str(error))
        return_code = error.exit_code
    except ConfigError as error:
        result.update(error=error.code, message=str(error))
        if error.diff is not None:
            result['diff'] = error.diff
        return_code = error.exit_code
    except (OSError, ValueError) as error:
        result.update(error='capability_unavailable', message=str(error))
        return_code = 2
    if config:
        result.update(projectId=config.project_id)
        result.update(requiredToolVersion=config.tool_version, toolVersionPolicy=config.version_policy,
                      versionMatches=config.tool_version == TOOL_VERSION and result.get('error') not in
                      ('version_conflict', 'installation_context_required'))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return return_code


if __name__ == '__main__':
    sys.exit(main())
