"""Validated project-owned configuration; independent of the installation path."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

CONFIG_VERSION = 1
TOOL_VERSION = (Path(__file__).resolve().parent.parent / 'VERSION').read_text(encoding='utf-8').strip()
CONFIG_NAME = 'review.config.json'


class ConfigError(ValueError):
    def __init__(self, message, exit_code=2, code='configuration_unavailable', diff=None):
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.diff = diff


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str
    tool_version: str
    project_root: Path
    web_root: Path
    data_dir: Path
    jobs_dir: Path
    server: dict
    page_identity: dict
    browser_storage: dict
    guidance: dict
    codex: dict


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ConfigError(name + ' must be a nonempty string')
    return value


def _object(value, name):
    if not isinstance(value, dict):
        raise ConfigError(name + ' must be an object')
    return dict(value)


def _strings(value, name):
    if not isinstance(value, list):
        raise ConfigError(name + ' must be an array')
    for item in value:
        _text(item, name)
    return value


def _path(root, value, name):
    return (root / _text(value, name)).resolve()


def _validated(root, raw):
    raw = _object(raw, 'configuration')
    if type(raw.get('configVersion')) is not int or raw['configVersion'] != CONFIG_VERSION:
        raise ConfigError('Unsupported configVersion; expected 1', code='unsupported_config_version')
    identity = _text(raw.get('projectId'), 'projectId')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', identity):
        raise ConfigError('Invalid projectId')
    version = _text(raw.get('toolVersion'), 'toolVersion')
    web = _path(root, raw.get('webRoot'), 'webRoot')
    data = _path(root, raw.get('dataDir'), 'dataDir')
    jobs = _path(root, raw.get('jobsDir'), 'jobsDir')
    if not web.is_dir():
        raise ConfigError('webRoot does not exist or is not a directory')
    server = _object(raw.get('server'), 'server')
    server.setdefault('host', '127.0.0.1')
    if server['host'] not in ('127.0.0.1', '0.0.0.0'):
        raise ConfigError('server.host must be 127.0.0.1 or 0.0.0.0')
    port = server.get('port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ConfigError('server.port must be between 1 and 65535')
    base = server.get('basePath')
    if not isinstance(base, str) or (base and not re.fullmatch(r'(?:/[a-zA-Z0-9_-]+)+', base)):
        raise ConfigError('server.basePath must be empty or an absolute URL prefix without trailing slash')
    origins = _strings(server.get('publicOrigins'), 'server.publicOrigins')
    for origin in origins:
        try:
            parts = urlsplit(origin)
        except ValueError as error:
            raise ConfigError('Invalid HTTPS public origin') from error
        if (parts.scheme != 'https' or not parts.netloc or not parts.hostname or parts.path or
                parts.query or parts.fragment or parts.username or parts.password):
            raise ConfigError('server.publicOrigins must contain HTTPS origins without paths')
        try:
            parts.port
        except ValueError:
            raise ConfigError('Invalid public origin port')
    shared = bool(origins or base or server['host'] != '127.0.0.1')
    if shared and (not origins or not base):
        raise ConfigError('Shared mode requires explicit HTTPS publicOrigins and basePath')
    codex = _object(raw.get('codex'), 'codex')
    if type(codex.get('enabled')) is not bool:
        raise ConfigError('codex.enabled must be a boolean')
    executable = _text(codex.get('executable'), 'codex.executable')
    if '/' in executable:
        codex['executable'] = str((root / executable).resolve())
    if 'model' in codex:
        _text(codex['model'], 'codex.model')
    if codex.get('approvalPolicy') != 'never' or codex.get('sandbox') != 'danger-full-access':
        raise ConfigError('Codex requires approvalPolicy=never and sandbox=danger-full-access')
    if shared and codex['enabled']:
        raise ConfigError('Shared mode cannot enable Codex')
    guidance = _object(raw.get('guidance'), 'guidance')
    for name in ('requiredFiles', 'sourceRoots'):
        _strings(guidance.get(name), 'guidance.' + name)
    for name in ('buildCommands', 'checkCommands'):
        commands = guidance.get(name)
        if not isinstance(commands, list):
            raise ConfigError('guidance.' + name + ' must be an array of argv arrays')
        for argv in commands:
            if not isinstance(argv, list) or not argv:
                raise ConfigError('guidance.' + name + ' must contain nonempty argv arrays')
            _strings(argv, 'guidance.' + name)
    return ProjectConfig(identity, version, root, web, data, jobs, server,
                         _object(raw.get('pageIdentity'), 'pageIdentity'),
                         _object(raw.get('browserStorage'), 'browserStorage'), guidance, codex)


def load_project_config(project_root: Path) -> ProjectConfig:
    root = Path(project_root).resolve()
    try:
        raw = json.loads((root / CONFIG_NAME).read_text(encoding='utf-8'))
        return _validated(root, raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError('Cannot read review.config.json: ' + str(error)) from error


def setup_project(project_root: Path, options: dict):
    """Create configuration exclusively, or compare only explicitly requested options."""
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ConfigError('Project directory does not exist')
    path = root / CONFIG_NAME
    existing = load_project_config(root) if path.exists() else None
    if existing:
        raw = json.loads(path.read_text(encoding='utf-8'))
    else:
        raw = {
            'configVersion': CONFIG_VERSION, 'projectId': str(uuid.uuid4()), 'toolVersion': TOOL_VERSION,
            'webRoot': '.', 'dataDir': 'review-data', 'jobsDir': '.review/jobs',
            'server': {'host': '127.0.0.1', 'port': 8799, 'basePath': '', 'publicOrigins': []},
            'pageIdentity': {}, 'browserStorage': {},
            'guidance': {'requiredFiles': [], 'sourceRoots': [], 'buildCommands': [], 'checkCommands': []},
            'codex': {'enabled': False, 'executable': 'codex', 'approvalPolicy': 'never', 'sandbox': 'danger-full-access'},
        }
    mapping = {'web_root': 'webRoot', 'data_dir': 'dataDir', 'jobs_dir': 'jobsDir',
               'host': 'server.host', 'port': 'server.port', 'base_path': 'server.basePath',
               'public_origin': 'server.publicOrigins', 'codex': 'codex.enabled',
               'codex_bin': 'codex.executable', 'model': 'codex.model'}
    diff = {}
    for option, key in mapping.items():
        value = options.get(option)
        if value is None:
            continue
        section, _, leaf = key.rpartition('.')
        target = raw[section] if section else raw
        old = target.get(leaf)
        if key in ('webRoot', 'dataDir', 'jobsDir'):
            equal = old is not None and (root / old).resolve() == (root / value).resolve()
        elif key == 'codex.executable' and old and '/' in old and '/' in value:
            equal = (root / old).resolve() == (root / value).resolve()
        else:
            equal = old == value
        if existing and not equal:
            diff[key] = {'existing': old, 'requested': value}
        elif not existing:
            target[leaf] = value
    if diff:
        raise ConfigError('Existing configuration differs; resolve review.config.json explicitly before retrying',
                          3, 'configuration_conflict', diff)
    if not existing and options.get('codex') is None:
        server = raw['server']
        shared = bool(server['publicOrigins'] or server['basePath'] or server['host'] != '127.0.0.1')
        raw['codex']['enabled'] = not shared
    config = _validated(root, raw)
    if existing:
        return config, False
    try:
        # Exclusive creation prevents two concurrent setup commands overwriting identity.
        with path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(raw, ensure_ascii=False, indent=2) + '\n')
    except FileExistsError:
        raise ConfigError('Configuration was created concurrently; retry setup', 3, 'configuration_conflict')
    return config, True
