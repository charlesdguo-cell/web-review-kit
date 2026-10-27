#!/usr/bin/env python3
"""Route explicit review operations to a project's pinned release; never dispatch jobs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HOST_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_VERSION = 1
CLI_COMMANDS = {'setup', 'doctor', 'serve', 'version', 'list', 'show', 'export', 'mark-changed', 'update', 'rollback'}
DATA_COMMANDS = {'list', 'show', 'export', 'mark-changed'}
WORKER_COMMANDS = DATA_COMMANDS | {'locate', 'snapshot', 'version'}


class RouterError(ValueError):
    def __init__(self, message, code='routing_unavailable', exit_code=2):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RouterError(message, 'invalid_arguments')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def project_identity(project):
    raw = read_json(project / 'review.config.json')
    if (not isinstance(raw, dict) or raw.get('configVersion') != 1 or
            any(not isinstance(raw.get(key), str) or not raw[key].strip() for key in ('projectId', 'toolVersion'))):
        raise RouterError('Expected review.config.json configVersion=1 with projectId and toolVersion', 'configuration_unavailable')
    return {key: raw[key] for key in ('projectId', 'toolVersion')}


def resolve_release(project, install):
    # Task 7 owns installation layout, integrity checks and release resolution.
    # Missing resolver/release is an error, never a host/newest/download fallback.
    sys.path.insert(0, str(HOST_ROOT / 'runtime'))
    try:
        from release_manager import resolve_project_release
    except ImportError as error:
        raise RouterError('Pinned release resolver is unavailable; complete the release installation first',
                          'resolver_unavailable') from error
    return Path(resolve_project_release(project, install)).resolve()


def describe_release(release, identity):
    actual = (release / 'VERSION').read_text(encoding='utf-8').strip()
    if actual != identity['toolVersion']:
        raise RouterError('Resolved runtime differs from project toolVersion', 'version_conflict', 3)
    skill = release / 'skills/web-review'
    try:
        contract = read_json(skill / 'workflow.json')
        if not isinstance(contract, dict) or type(contract.get('workflowVersion')) is not int or contract['workflowVersion'] != WORKFLOW_VERSION:
            raise ValueError('unsupported workflowVersion')
        paths = {'cli': release / 'web-review.py', 'skill': skill / 'SKILL.md',
                 'setupWorkflow': skill / 'references/project-setup.md',
                 'commentWorkflow': skill / 'references/comment-workflow.md'}
        if any(not path.is_file() for path in paths.values()):
            raise ValueError('incomplete workflow bundle')
    except (OSError, ValueError) as error:
        raise RouterError('Pinned release workflow is missing or incompatible: ' + str(error), 'workflow_unavailable') from error
    return {'ok': True, **identity, 'releaseRoot': str(release), 'workflowVersion': WORKFLOW_VERSION,
            **{key: str(path) for key, path in paths.items()}}


def frozen_request(path, project, identity, description, explicit_url):
    request = read_json(path)
    if not isinstance(request, dict) or not isinstance(request.get('executionConfig'), dict):
        raise RouterError('Worker request needs frozen executionConfig; legacy requests require their original workflow', 'request_unavailable')
    execution = request['executionConfig']
    if (not isinstance(request.get('project'), str) or not Path(request['project']).is_absolute() or
            Path(request['project']).resolve() != project or
            any(execution.get(key) != identity[key] for key in ('projectId', 'toolVersion')) or
            not isinstance(execution.get('skillPath'), str) or not Path(execution['skillPath']).is_absolute() or
            Path(execution['skillPath']).resolve() != Path(description['skill'])):
        raise RouterError('Frozen request project, pin or skill path differs from the selected release', 'request_conflict', 3)
    if (not isinstance(execution.get('guidance'), dict) or not isinstance(execution.get('codex'), dict) or
            not isinstance(request.get('data'), str) or not Path(request['data']).is_absolute() or
            not isinstance(request.get('reviewUrl'), str) or not request['reviewUrl'].strip() or
            not isinstance(request.get('comments'), list) or
            any(not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or
                not isinstance(item.get('updatedAt'), str) or not item['updatedAt'] for item in request['comments']) or
            len({item['id'] for item in request['comments']}) != len(request['comments'])):
        raise RouterError('Worker request has incomplete frozen guidance, endpoint, data or comments', 'request_unavailable')
    if explicit_url is not None and explicit_url.rstrip('/') != request['reviewUrl'].rstrip('/'):
        raise RouterError('Explicit review URL differs from frozen request.reviewUrl', 'request_conflict', 3)
    return request


def verify_batch_operation(command, arguments, request, identity):
    if command not in ('show', 'mark-changed'):
        return
    parser = Parser(prog='review.py ' + command)
    parser.add_argument('--id', required=True)
    if command == 'mark-changed':
        parser.add_argument('--snapshot', type=Path, required=True)
        parser.add_argument('--resolution-file', type=Path, required=True)
    args = parser.parse_args(arguments)
    matches = [item for item in request['comments'] if item['id'] == args.id]
    if len(matches) != 1:
        raise RouterError('Comment id is not in the frozen batch', 'request_unavailable')
    if command == 'mark-changed':
        snapshot = read_json(args.snapshot)
        if isinstance(snapshot, dict) and 'comment' in snapshot:
            if snapshot.get('projectId', identity['projectId']) != identity['projectId']:
                raise RouterError('Snapshot project differs from frozen request', 'request_conflict', 3)
            snapshot = snapshot['comment']
        if snapshot != matches[0]:
            raise RouterError('Writeback snapshot differs from original frozen batch', 'request_conflict', 3)


def main(argv=None):
    result = {'ok': False, 'projectId': None, 'toolVersion': None}
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--project', type=Path, required=True)
        parser.add_argument('--install-root', type=Path, required=True, help='Verified release installation root')
        parser.add_argument('--request', type=Path, help='Existing immutable worker request; does not start a job')
        parser.add_argument('--review-url', help='Explicit service base URL; CLI verifies projectId before data access')
        parser.add_argument('command', choices=sorted(CLI_COMMANDS | {'locate', 'snapshot'}))
        parser.add_argument('arguments', nargs=argparse.REMAINDER)
        args = parser.parse_args(argv)
        if args.request and args.command not in WORKER_COMMANDS:
            raise RouterError('Existing workers only consume their batch; setup/service/version changes are separate operations', 'invalid_arguments')
        project, install = args.project.resolve(), args.install_root.resolve()
        # Setup alone bootstraps an unconfigured project from this explicitly selected bundle.
        # Configured projects, including repeated setup, always use the project's pin.
        if args.command == 'setup' and not (project / 'review.config.json').exists():
            identity = {'projectId': None, 'toolVersion': (HOST_ROOT / 'VERSION').read_text(encoding='utf-8').strip()}
            release = HOST_ROOT
        else:
            identity = project_identity(project)
            release = resolve_release(project, install)
        result.update(identity)
        description = describe_release(release, identity)
        request = frozen_request(args.request, project, identity, description, args.review_url) if args.request else None
        review_url = request['reviewUrl'] if request else args.review_url
        if args.command == 'locate':
            if args.arguments:
                raise RouterError('locate takes no additional arguments', 'invalid_arguments')
            result = description
            if request:
                result.update(executionConfig=request['executionConfig'], reviewUrl=review_url,
                              data=request['data'], frozenComments=len(request['comments']))
        elif args.command == 'snapshot':
            if request is None:
                raise RouterError('snapshot needs --request; current-conversation snapshots come from show', 'invalid_arguments')
            snapshot_parser = Parser(prog='review.py snapshot')
            snapshot_parser.add_argument('--id', required=True)
            snapshot_parser.add_argument('--output', type=Path, required=True)
            snapshot = snapshot_parser.parse_args(args.arguments)
            matches = [item for item in request['comments'] if item['id'] == snapshot.id]
            if len(matches) != 1:
                raise RouterError('Comment id is not in the frozen batch', 'request_unavailable')
            with snapshot.output.open('x', encoding='utf-8') as handle:
                json.dump({**identity, 'comment': matches[0]}, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            result.update(ok=True, snapshot=str(snapshot.output.resolve()), id=snapshot.id)
        else:
            if args.review_url is not None and args.command not in DATA_COMMANDS:
                raise RouterError('--review-url is supported only for review data operations', 'invalid_arguments')
            # Do not let passthrough arguments replace router-owned project/endpoint identity.
            if any(arg.split('=', 1)[0] in ('--project', '--review-url') for arg in args.arguments):
                raise RouterError('Project and review URL must precede the command', 'invalid_arguments')
            if request:
                verify_batch_operation(args.command, args.arguments, request, identity)
            command = [sys.executable, description['cli'], '--project', str(project)]
            if review_url is not None and args.command in DATA_COMMANDS:
                command += ['--review-url', review_url]
            return subprocess.run(command + [args.command] + args.arguments, cwd=project).returncode
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except (OSError, ValueError) as error:
        result.update(ok=False, error=getattr(error, 'code', 'routing_unavailable'), message=str(error))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return getattr(error, 'exit_code', 2)


if __name__ == '__main__':
    sys.exit(main())
