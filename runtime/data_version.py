"""Read-only v1 detection and deliberate, backed-up legacy activation."""
import json
import os
from pathlib import Path
import shutil
import uuid

from data_lock import acquire_data_lock


class DataVersionError(ValueError):
    exit_code = 3
    code = 'data_version_conflict'


def _read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as error:
        raise DataVersionError('Invalid review data JSON at ' + str(path) + ': ' + str(error)) from error


def inspect_data_version(data_dir: Path) -> dict:
    """No directories, empty comments, metadata or backups are created by inspection."""
    data = Path(data_dir).resolve()
    manifest = data / 'comments.json'
    if manifest.exists():
        comments = _read(manifest)
        if not isinstance(comments, list) or any(not isinstance(item, dict) for item in comments):
            raise DataVersionError('comments.json must remain a bare array of comment objects')
    meta = data / 'meta.json'
    if not meta.exists():
        return {'schemaVersion': 1, 'projectId': None, 'legacy': True, 'supported': True}
    value = _read(meta)
    if (not isinstance(value, dict) or type(value.get('schemaVersion')) is not int or
            not isinstance(value.get('projectId'), str) or not value['projectId'].strip()):
        raise DataVersionError('meta.json requires integer schemaVersion and nonempty projectId')
    return {**value, 'legacy': False, 'supported': value['schemaVersion'] == 1}


def require_writable_data(data_dir: Path, project_id=None):
    version = inspect_data_version(data_dir)
    if not version['supported']:
        raise DataVersionError('Unsupported review data schemaVersion: ' + str(version['schemaVersion']))
    if project_id is not None and version['projectId'] not in (None, project_id):
        raise DataVersionError('Review data belongs to a different project')
    return version


def activate_data_version(data_dir: Path, project_id: str, backup_dir: Path, project_root=None) -> dict:
    """Explicit activation, never called by serve/read/doctor. Backup destination must be new."""
    data, backup = Path(data_dir).resolve(), Path(backup_dir).resolve()
    workspace = Path(project_root).resolve() if project_root is not None else data.parent
    if not isinstance(project_id, str) or not project_id.strip():
        raise DataVersionError('projectId must be nonempty')
    if backup == workspace or workspace in backup.parents or backup == data or data in backup.parents:
        raise DataVersionError('Backup must be outside the consumer workspace and review data')
    with acquire_data_lock(data):
        version = require_writable_data(data, project_id)
        if not version['legacy']:
            return version
        # copytree preserves all evidence, extension files, modes and timestamps.
        if data.exists():
            shutil.copytree(data, backup)
        else:
            backup.mkdir(parents=True, exist_ok=False)
        data.mkdir(parents=True, exist_ok=True)
        temporary = data / ('.meta-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps({'schemaVersion': 1, 'projectId': project_id}, indent=2) + '\n', encoding='utf-8')
            os.replace(temporary, data / 'meta.json')
        finally:
            if temporary.exists():
                temporary.unlink()
        return {**inspect_data_version(data), 'backup': str(backup)}
