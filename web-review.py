#!/usr/bin/env python3
"""Thin project-scoped entrypoint for the Web Review Kit."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from project_config import ConfigError, TOOL_VERSION, load_project_config, setup_project
from server import serve_project
from review_data import ReviewClient, ReviewDataError
from data_lock import DataLockError
from data_version import DataVersionError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ConfigError(message, code='invalid_arguments')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    setup = commands.add_parser('setup', help='Create project configuration without starting a service')
    for flag in ('web-root', 'data-dir', 'jobs-dir', 'host', 'base-path', 'codex-bin', 'model'):
        setup.add_argument('--' + flag)
    setup.add_argument('--port', type=int)
    setup.add_argument('--public-origin', action='append')
    toggle = setup.add_mutually_exclusive_group()
    toggle.add_argument('--codex', action='store_true', default=None)
    toggle.add_argument('--no-codex', dest='codex', action='store_false')
    commands.add_parser('serve', help='Serve the configured project')
    commands.add_parser('version', help='Report toolkit version')
    commands.add_parser('doctor', help='Check environment, protocol and auth without inference')
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
        if args.command == 'version':
            if (args.project / 'review.config.json').exists():
                config = load_project_config(args.project)
            value = {'command': 'version'}
        elif args.command == 'setup':
            if (args.project / 'review.config.json').exists():
                config = load_project_config(args.project)
            config, created = setup_project(args.project, vars(args))
            value = {'command': 'setup', 'created': created}
        else:
            config = load_project_config(args.project)
            if args.command == 'serve':
                serve_project(config)
                return 0
            if args.command == 'doctor':
                from codex_doctor import doctor
                value = {'command': 'doctor', **doctor(config)}
                result.update(ok=value['ready'], projectId=config.project_id, toolVersion=config.tool_version, **value)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                return 0 if value['ready'] else 2
            base_url = 'http://127.0.0.1:' + str(config.server['port']) + config.server['basePath']
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
    except (ReviewDataError, DataLockError, DataVersionError) as error:
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
        if args.command != 'version':
            result['toolVersion'] = config.tool_version
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return return_code


if __name__ == '__main__':
    sys.exit(main())
