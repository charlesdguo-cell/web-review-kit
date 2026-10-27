#!/usr/bin/env python3
"""Thin project-scoped entrypoint for the Web Review Kit."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from project_config import ConfigError, TOOL_VERSION, load_project_config, setup_project
from server import serve_project


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
            serve_project(config)
            return 0
        result.update(ok=True, **value)
        return_code = 0
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
