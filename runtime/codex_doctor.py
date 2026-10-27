"""Read-only environment and App Server readiness; never starts a model turn."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

from codex_session import AppServer
from codex_tasks import resolve_executable, skill_path
from data_version import inspect_data_version
from project_config import ProjectConfig


def _writable_destination(path):
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def doctor(config: ProjectConfig) -> dict:
    checks = []

    def check(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    shared = bool(config.server['publicOrigins'] or config.server['basePath'] or config.server['host'] != '127.0.0.1')
    local_enabled = config.codex['enabled'] and not shared
    environment_ok = (config.project_root.is_dir() and config.web_root.is_dir() and
                      _writable_destination(config.data_dir) and _writable_destination(config.jobs_dir))
    for name in config.guidance.get('requiredFiles', []):
        path = config.project_root / name
        environment_ok = environment_ok and path.is_file() and os.access(path, os.R_OK)
    for name in config.guidance.get('sourceRoots', []):
        environment_ok = environment_ok and (config.project_root / name).is_dir()
    check('environment', environment_ok, 'Project, web, guidance and writable data/job paths checked without creating them')
    try:
        version = inspect_data_version(config.data_dir)
        data_ok = version['supported'] and version['projectId'] in (None, config.project_id)
        check('reviewData', data_ok, 'Read-only version/project inspection; legacy data is not activated')
    except (OSError, ValueError):
        data_ok = False
        check('reviewData', False, 'Review data version or identity is unavailable')
    check('localExecution', local_enabled, 'Codex enabled for localhost' if local_enabled else 'Codex disabled or shared entrypoint')
    executable = resolve_executable(config.codex['executable'])
    check('cli', bool(executable), 'Configured executable found' if executable else 'Configured Codex executable not found; install or configure it explicitly')
    path = skill_path()
    skill_ok = path.is_absolute() and path.is_file() and os.access(path, os.R_OK)
    check('skill', skill_ok, 'web-review skill readable' if skill_ok else 'web-review skill missing or unreadable in this toolkit version')
    if executable and local_enabled and environment_ok:
        client = None
        try:
            result = subprocess.run([executable, '--version'], cwd=config.project_root,
                                    capture_output=True, text=True, timeout=10)
            match = re.search(r'codex-cli\s+[0-9][0-9A-Za-z.+_-]*', result.stdout)
            check('cliVersion', result.returncode == 0 and bool(match), match.group(0) if match else 'CLI version unavailable')
            # Suppress protocol/stderr logs: account responses are inspected, never persisted.
            with tempfile.TemporaryDirectory(prefix='web-review-doctor-') as temporary:
                try:
                    client = AppServer({'executable': executable, 'project': str(config.project_root)},
                                       Path(temporary), lambda *_: None, log_events=False)
                    client.call('initialize', {'clientInfo': {'name': 'web_review_doctor', 'version': '1.0'}}, timeout=10)
                    client.send({'method': 'initialized'})
                    check('protocol', True, 'App Server initialize/initialized handshake accepted')
                    auth = client.call('account/read', {'refreshToken': False}, timeout=10)
                    authenticated = auth.get('requiresOpenaiAuth') is False or isinstance(auth.get('account'), dict)
                    check('authentication', authenticated, 'Provider authentication available' if authenticated else 'Provider requires authentication; log in explicitly outside doctor')
                finally:
                    if client:
                        client.close(); client = None
        except Exception:
            # Never propagate account data, raw protocol errors or credential-bearing stderr.
            if not any(item['name'] == 'protocol' for item in checks):
                check('protocol', False, 'App Server handshake unavailable or unsupported')
            else:
                check('authentication', False, 'Account status unavailable through the supported account/read interface')
    ready = all(item['ok'] for item in checks)
    return {'checks': checks, 'ready': ready,
            'capabilities': {'review': bool(environment_ok and data_ok),
                             'codex': bool(ready and local_enabled), 'sharedReview': shared,
                             'modelTaskVerified': False}}
