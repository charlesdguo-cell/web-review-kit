#!/usr/bin/env python3
"""Packaged consumer symlink entry: tools/review/server.py --open --codex."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import webbrowser
sys.dont_write_bytecode = True
RELEASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE / 'runtime'))
from project_config import load_project_config, ConfigError
from release_manager import installed_root, resolve_project_release, ReleaseError
from server import serve_project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--codex', action='store_true')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--base-path')
    parser.add_argument('--public-origin', action='append')
    parser.add_argument('--bind-host')
    parser.add_argument('--codex-bin')
    args = parser.parse_args(argv)
    # Preserve lexical symlink location, including launches from outside consumer cwd.
    project = (args.project or Path(__file__).absolute().parents[2]).resolve()
    try:
        install = installed_root(RELEASE)
        target = resolve_project_release(project, install)
        if target != RELEASE:
            import subprocess
            return subprocess.run([sys.executable, str(target / 'compat/server.py'), '--project', str(project)] + list(argv if argv is not None else sys.argv[1:])).returncode
        config = load_project_config(project)
        options = dict(config.server)
        for flag, key in [('port', 'port'), ('base_path', 'basePath'), ('public_origin', 'publicOrigins'), ('bind_host', 'host')]:
            if getattr(args, flag) is not None:
                options[key] = getattr(args, flag)
        codex = dict(config.codex)
        if args.codex:
            codex['enabled'] = True
        if args.codex_bin:
            codex['executable'] = args.codex_bin
        if codex['enabled'] and (options['host'] != '127.0.0.1' or options['basePath'] or options['publicOrigins']):
            raise ConfigError('Codex is available only at the configured local entrypoint')
        config = replace(config, server=options, codex=codex,
                         web_root=args.root.resolve() if args.root else config.web_root,
                         data_dir=args.data.resolve() if args.data else config.data_dir)
        if args.open:
            webbrowser.open('http://127.0.0.1:' + str(options['port']) + options['basePath'] + '/')
        serve_project(config)
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': getattr(error, 'code', 'configuration_unavailable'), 'message': str(error)}))
        return getattr(error, 'exit_code', 2)


if __name__ == '__main__':
    sys.exit(main())
