"""Verified private bundles, explicit global selection and stopped-project pins."""
from contextlib import contextmanager, ExitStack
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from data_lock import acquire_data_lock
from data_version import inspect_data_version
from project_config import load_project_config

# Closed allowlist: untracked data, credentials, logs and consumer assets cannot sneak in.
RELEASE_FILES = '''VERSION README.md AGENTS.md web-review.py
runtime/server.py runtime/codex_tasks.py runtime/codex_session.py runtime/codex_doctor.py runtime/annotation_tasks.py
runtime/project_config.py runtime/review_data.py runtime/data_lock.py runtime/data_version.py
runtime/merge_review_data.py runtime/release_manager.py runtime/review.js runtime/review.css
runtime/html2canvas.min.js runtime/LICENSE.html2canvas-pro
skills/web-review/SKILL.md skills/web-review/workflow.json skills/web-review/scripts/review.py
skills/web-review/references/project-setup.md skills/web-review/references/comment-workflow.md
schemas/project-config.schema.json schemas/review-data-v1.schema.json
scripts/package.py scripts/install.py compat/server.py docs/releases.md docs/browser-identity.md
docs/source-map.md'''.split()
# These published candidates predate the independent annotation runtime. A newer
# global Skill must still resolve their pinned, closed inventories unchanged.
PRE_ANNOTATION_VERSIONS = frozenset('0.1.0-rc.' + str(number) for number in range(1, 8))
PRE_ANNOTATION_FILES = frozenset(RELEASE_FILES) - {'runtime/annotation_tasks.py'}
DEPENDENCY_SHA256 = 'e13cf4fb0919313c321783fb67b51b18dd0e7e90d33ba9fc50706278f070d363'
LEGACY_RC1_MANIFEST_SHA256 = '50cc67d2ca9c36b066253721f87ccd41b5be6f9c522e851803cc5a2656b3fc88'


class ReleaseError(ValueError):
    def __init__(self, message, code='release_conflict', exit_code=3):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ReleaseError('Cannot read valid release/configuration JSON: ' + str(path)) from error


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', value):
        raise ReleaseError('Invalid release VERSION')
    return value


def _workflow(root):
    value = _json(root / 'skills/web-review/workflow.json')
    if not isinstance(value, dict) or type(value.get('workflowVersion')) is not int or value['workflowVersion'] != 1:
        raise ReleaseError('Unsupported Skill workflowVersion', 'workflow_unavailable', 2)


def package_release(source_root: Path, destination: Path) -> Path:
    """Return reproducible tar.gz; archive root contains runtime/ and skills/ directly."""
    root, dest = Path(source_root).resolve(), Path(destination).resolve()
    version = _version((root / 'VERSION').read_text().strip())
    _workflow(root)
    contents = {}
    for name in sorted(RELEASE_FILES):
        path = root / name
        if path.is_symlink() or root not in path.resolve().parents or not path.is_file():
            raise ReleaseError('Missing or linked package file: ' + name)
        contents[name] = path.read_bytes()
    if _hash(contents['runtime/html2canvas.min.js']) != DEPENDENCY_SHA256:
        raise ReleaseError('Vendored dependency changed; review patch and fixed hash before packaging')
    hashes = {name: _hash(data) for name, data in contents.items()}
    manifest = {'manifestVersion': 1, 'package': 'web-review-kit', 'version': version,
                'files': hashes, 'source': {'treeSha256': _hash(_encode(hashes))},
                'storageSchemas': {'read': [1], 'write': [1]}, 'exportFormats': [2],
                'runtimeSelection': {'global': 1},
                'workflowVersion': 1, 'python': '>=3.9',
                'dependencies': [{'name': 'html2canvas-pro', 'version': '2.4.2',
                                  'sha256': DEPENDENCY_SHA256, 'license': 'MIT',
                                  'patch': 'isolation:isolate participates in real stacking-context detection'}]}
    contents['release-manifest.json'] = _encode(manifest)
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / ('web-review-kit-' + version + '.tar.gz')
    with tempfile.NamedTemporaryFile(dir=dest, delete=False) as output:
        temporary = Path(output.name)
        try:
            with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as bundle:
                    for name, data in sorted(contents.items()):
                        item = tarfile.TarInfo(name)
                        item.size, item.mode, item.mtime = len(data), 0o644, 0
                        bundle.addfile(item, io.BytesIO(data))
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    (dest / 'release-manifest.json').write_bytes(contents['release-manifest.json'])
    (archive.with_name(archive.name + '.sha256')).write_text(_hash(archive.read_bytes()) + '  ' + archive.name + '\n')
    return archive


def verify_release(path: Path) -> dict:
    """Integrity only. Download provenance is the authorized private GitHub release."""
    root = Path(path).resolve()
    manifest = _json(root / 'release-manifest.json')
    if (not isinstance(manifest, dict) or manifest.get('package') != 'web-review-kit' or
            manifest.get('manifestVersion') != 1 or not isinstance(manifest.get('files'), dict)):
        raise ReleaseError('Wrong package identity or manifest format')
    version = _version((root / 'VERSION').read_text().strip())
    if manifest.get('version') != version:
        raise ReleaseError('Manifest version differs from VERSION', 'version_conflict')
    required = set(RELEASE_FILES)
    if version in PRE_ANNOTATION_VERSIONS and set(manifest['files']) == PRE_ANNOTATION_FILES:
        required = PRE_ANNOTATION_FILES
    if set(manifest['files']) != required:
        raise ReleaseError('Release file inventory is incomplete or contains unmanaged files')
    actual = set()
    for file in root.rglob('*'):
        relative = file.relative_to(root)
        if file.is_symlink():
            raise ReleaseError('Symlinks are not permitted inside a release')
        if '__pycache__' in relative.parts and file.suffix == '.pyc':
            continue
        if file.is_file():
            actual.add(relative.as_posix())
    if actual != required | {'release-manifest.json'}:
        raise ReleaseError('Installed file inventory has local additions or missing files')
    for name, digest in manifest['files'].items():
        if not isinstance(digest, str) or _hash((root / name).read_bytes()) != digest:
            raise ReleaseError('Managed file integrity conflict: ' + name)
    if manifest.get('source') != {'treeSha256': _hash(_encode(manifest['files']))}:
        raise ReleaseError('Source digest mismatch')
    # rc.1's published manifest incorrectly labeled the unchanged browser v2 export
    # as v1. Recognize only those exact historical bytes for same-root transitions;
    # never rewrite them or accept the incorrect declaration in another release.
    legacy_export_metadata = (version == '0.1.0-rc.1' and
                              _hash((root / 'release-manifest.json').read_bytes()) == LEGACY_RC1_MANIFEST_SHA256)
    if (manifest.get('storageSchemas') != {'read': [1], 'write': [1]} or
            manifest.get('exportFormats') != ([1] if legacy_export_metadata else [2]) or manifest.get('workflowVersion') != 1):
        raise ReleaseError('Unsupported storage/export/workflow contract')
    if 'runtimeSelection' in manifest and manifest['runtimeSelection'] != {'global': 1}:
        raise ReleaseError('Unsupported runtime selection contract')
    _workflow(root)
    if manifest['files']['runtime/html2canvas.min.js'] != DEPENDENCY_SHA256:
        raise ReleaseError('Unrecognized vendored dependency')
    return manifest


@contextmanager
def _lock(path):
    with Path(path).open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReleaseError('Installation or active job lock is held: ' + str(path)) from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _extract(archive, target):
    with tarfile.open(archive, 'r:gz') as bundle:
        seen = set()
        for item in bundle:
            name = PurePosixPath(item.name)
            if (not item.isfile() or name.is_absolute() or '..' in name.parts or
                    item.name not in set(RELEASE_FILES) | {'release-manifest.json'} or item.name in seen):
                raise ReleaseError('Unsafe or unexpected archive member: ' + item.name)
            seen.add(item.name)
            output = target / item.name
            output.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(item) as source, output.open('xb') as dest:
                shutil.copyfileobj(source, dest)


def _receipt(root, release):
    path = root / 'receipts' / (release.name + '.json')
    if path.is_symlink():
        raise ReleaseError('Installation receipt cannot be a symlink')
    expected = {'version': release.name, 'manifestSha256': _hash((release / 'release-manifest.json').read_bytes())}
    if _json(path) != expected:
        raise ReleaseError('Installed release receipt differs from manifest; local modification detected')


def installed_root(release: Path) -> Path:
    """Deterministic layout plus receipt validation, never search for newest releases."""
    path = Path(release).resolve()
    manifest = verify_release(path)
    if path.parent.name != 'releases' or path.name != manifest['version']:
        raise ReleaseError('Release is not in an explicit installation releases/VERSION directory')
    root = path.parent.parent
    if any((root / name).is_symlink() for name in ('releases', 'receipts')):
        raise ReleaseError('Installation directories cannot be symlinks')
    _receipt(root, path)
    return root


def install_release(archive: Path, install_root: Path) -> Path:
    """Install files only. Existing modified versions are never overwritten; no project mutation."""
    root = Path(install_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with _lock(root / '.install.lock'):
        if any((root / name).is_symlink() for name in ('releases', 'receipts')):
            raise ReleaseError('Installation directories cannot be symlinks')
        (root / 'releases').mkdir(exist_ok=True)
        (root / 'receipts').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=root) as temporary:
            stage = Path(temporary) / 'bundle'
            stage.mkdir()
            if Path(archive).is_dir():
                verify_release(archive)
                shutil.copytree(archive, stage, dirs_exist_ok=True)
            else:
                _extract(archive, stage)
            manifest = verify_release(stage)
            target = root / 'releases' / manifest['version']
            if target.exists() or target.is_symlink():
                if target.is_symlink():
                    raise ReleaseError('Release destination is a symlink')
                verify_release(target)
                _receipt(root, target)
                if (target / 'release-manifest.json').read_bytes() != (stage / 'release-manifest.json').read_bytes():
                    raise ReleaseError('Same version has different content; publish a new version')
                return target
            receipt = root / 'receipts' / (manifest['version'] + '.json')
            if receipt.exists():
                raise ReleaseError('Orphan installation receipt; inspect before retrying')
            # Write receipt before directory publication: readers only see complete releases.
            receipt.write_bytes(_encode({'version': manifest['version'], 'manifestSha256': _hash((stage / 'release-manifest.json').read_bytes())}))
            try:
                os.rename(stage, target)
            except BaseException:
                receipt.unlink()
                raise
            return target


def resolve_installed_version(version, install_root) -> Path:
    """Resolve one exact release, retaining the closed manifest and receipt checks."""
    root = Path(install_root).expanduser().resolve()
    if any((root / name).is_symlink() for name in ('releases', 'receipts')):
        raise ReleaseError('Installation directories cannot be symlinks')
    release = root / 'releases' / _version(version)
    if release.is_symlink() or not release.is_dir():
        raise ReleaseError('Pinned release is not installed: ' + version, 'release_unavailable', 2)
    if installed_root(release) != root:
        raise ReleaseError('Release belongs to a different installation')
    return release


def resolve_global_release(install_root) -> Path:
    root = Path(install_root).expanduser().resolve()
    current = root / 'current'
    if not current.is_symlink():
        raise ReleaseError('Global current must be an explicit installed-release symlink', 'global_release_unavailable', 2)
    try:
        target = current.resolve()
    except (OSError, RuntimeError) as error:
        raise ReleaseError('Global current cannot be resolved', 'global_release_unavailable', 2) from error
    if target.parent != root / 'releases':
        raise ReleaseError('Global current points outside this installation', 'installation_root_conflict')
    release = resolve_installed_version(target.name, root)
    if _json(release / 'release-manifest.json').get('runtimeSelection') != {'global': 1}:
        raise ReleaseError('Selected release does not support global runtime selection; keep it pinned', 'global_runtime_unsupported', 2)
    if current.resolve() != release:
        raise ReleaseError('Global current changed during resolution; retry', 'version_conflict')
    return release


def resolve_project_release(project_root, install_root) -> Path:
    config = load_project_config(Path(project_root))
    if config.version_policy == 'global':
        return resolve_global_release(install_root)
    return resolve_installed_version(config.version_policy, install_root)


def resolve_frozen_release(project_root, install_root, execution, request_project) -> Path:
    """A request binds its policy and identity, but never follows a changed current."""
    project = Path(project_root).resolve()
    config = load_project_config(project)
    root = Path(install_root).expanduser().resolve()
    if (not isinstance(execution, dict) or not isinstance(request_project, str) or
            not Path(request_project).is_absolute() or Path(request_project).resolve() != project or
            execution.get('projectId') != config.project_id or
            execution.get('toolVersionPolicy', execution.get('toolVersion')) != config.version_policy or
            execution.get('installRoot', str(root)) != str(root)):
        raise ReleaseError('Frozen request project, policy or installation differs', 'request_conflict')
    if config.version_policy != 'global' and execution.get('toolVersion') != config.version_policy:
        raise ReleaseError('Frozen concrete release differs from the explicit project pin', 'request_conflict')
    release = resolve_installed_version(execution.get('toolVersion'), root)
    if config.version_policy == 'global' and _json(release / 'release-manifest.json').get('runtimeSelection') != {'global': 1}:
        raise ReleaseError('Frozen release does not support global runtime selection', 'global_runtime_unsupported', 2)
    skill = execution.get('skillPath')
    if (not isinstance(skill, str) or not Path(skill).is_absolute() or
            Path(skill).resolve() != release / 'skills/web-review/SKILL.md'):
        raise ReleaseError('Frozen request Skill differs from the verified release', 'request_conflict')
    return release


def validate_runtime(config, *, release=None, follow_current=True):
    """Check startup routing, or only the concrete binding for an existing worker."""
    host = Path(release).resolve() if release is not None else Path(__file__).resolve().parent.parent
    actual = (host / 'VERSION').read_text().strip()
    if config.tool_version != actual:
        raise ReleaseError('Actual runtime differs from loaded project version', 'version_conflict')
    if (host / 'release-manifest.json').exists():
        root = installed_root(host)
        if follow_current and resolve_project_release(config.project_root, root) != host:
            raise ReleaseError('Runtime differs from selected project release; retry through the Skill', 'version_conflict')
        return root
    if config.version_policy == 'global':
        raise ReleaseError('Global policy requires a verified installation; source checkouts remain pinned', 'installation_context_required', 2)
    return None


def activate_global_release(target, install_root, *, skill_link=None):
    """Explicit atomic default switch; never mutate projects or running work."""
    root = Path(install_root).expanduser().resolve()
    target = Path(target).resolve()
    with _lock(root / '.install.lock'):
        release = resolve_installed_version(target.name, root)
        if release != target:
            raise ReleaseError('Global target belongs to another installation', 'installation_root_conflict')
        if _json(release / 'release-manifest.json').get('runtimeSelection') != {'global': 1}:
            raise ReleaseError('Target release does not support global runtime selection; keep it pinned', 'global_runtime_unsupported', 2)
        current = root / 'current'
        previous = resolve_global_release(root) if current.exists() or current.is_symlink() else None
        link = Path(skill_link).expanduser().absolute() if skill_link is not None else None
        discovery_target = current / 'skills/web-review'
        replace_link = False
        original_skill = None
        # Preflight discovery before publishing current; unmanaged conflicts preserve both.
        if link is not None and (link.exists() or link.is_symlink()):
            if not link.is_symlink():
                raise ReleaseError('Discovery destination already exists; preserved: ' + str(link))
            original_skill = os.readlink(link)
            lexical = Path(os.path.abspath(link.parent / os.readlink(link)))
            if lexical != discovery_target:
                existing = link.resolve()
                old_release = existing.parent.parent
                if (existing != old_release / 'skills/web-review' or
                        resolve_installed_version(old_release.name, root) != old_release):
                    raise ReleaseError('Discovery destination is unmanaged; preserved: ' + str(link))
                replace_link = True
        elif link is not None:
            replace_link = True
        # Create temporary symlinks before publication, so destination errors cannot
        # leave a changed default. os.replace keeps readers on a complete old/new target.
        with ExitStack() as stack:
            def staged_link(destination, value):
                destination.parent.mkdir(parents=True, exist_ok=True)
                handle, name = tempfile.mkstemp(prefix='.web-review-link-', dir=destination.parent)
                os.close(handle)
                temporary = Path(name)
                temporary.unlink()
                temporary.symlink_to(value, target_is_directory=True)
                stack.callback(lambda: temporary.unlink(missing_ok=True))
                return temporary
            next_current = staged_link(current, Path('releases') / release.name) if previous != release else None
            next_skill = staged_link(link, discovery_target) if replace_link else None
            restore_skill = staged_link(link, original_skill) if replace_link and original_skill is not None else None
            if next_skill is not None:
                os.replace(next_skill, link)
            try:
                if next_current is not None:
                    os.replace(next_current, current)
            except BaseException:
                if next_skill is not None:
                    if restore_skill is not None:
                        os.replace(restore_skill, link)
                    else:
                        link.unlink()
                raise
    return {'globalCurrent': str(current), 'globalActivated': True,
            'previousToolVersion': previous.name if previous else None,
            'changed': previous != release, 'skillLink': str(link) if link else None}


def activate_release(config, target: Path, *, install_root=None) -> dict:
    """Atomic config pin only; no implicit migration, startup, metadata creation or task mutation."""
    host = Path(__file__).resolve().parent.parent
    host_root = installed_root(host) if (host / 'release-manifest.json').exists() else None
    if install_root is None and host_root is None:
        raise ReleaseError('Source/API activation requires explicit install_root; target is not installation context',
                           'installation_context_required', 2)
    root = Path(install_root).expanduser().resolve() if install_root is not None else host_root
    if host_root is not None and root != host_root:
        raise ReleaseError('Explicit install_root differs from the verified calling runtime', 'installation_root_conflict')
    target = Path(target).resolve()
    if installed_root(target) != root:
        raise ReleaseError('Target belongs to another installation; root relocation is not supported', 'installation_root_conflict')
    manifest = verify_release(target)
    config_path = config.project_root / 'review.config.json'
    with acquire_data_lock(config.data_dir), ExitStack() as stack:
        if config.jobs_dir.exists():
            stack.enter_context(_lock(config.jobs_dir / 'active.lock'))
            for status_path in config.jobs_dir.glob('*/status.json'):
                status = _json(status_path)
                if not isinstance(status, dict) or not isinstance(status.get('status'), str) or status.get('status') in ('starting', 'running', 'stopping'):
                    raise ReleaseError('Active or malformed job blocks version switch: ' + str(status_path), 'active_task_conflict')
        current = load_project_config(config.project_root)
        if current != config:
            raise ReleaseError('Project configuration changed during activation', 'configuration_conflict')
        # Never infer current installation from target; require an intact existing pin
        # in the verified caller/explicit root before changing configuration.
        resolve_project_release(config.project_root, root)
        data = inspect_data_version(config.data_dir)
        if data['projectId'] not in (None, config.project_id):
            raise ReleaseError('Review data belongs to another project', 'project_conflict')
        if data['schemaVersion'] not in manifest['storageSchemas']['write']:
            raise ReleaseError('Target cannot write this data schema; no automatic migration is available', 'data_version_conflict')
        original = config_path.read_bytes()
        raw = json.loads(original)
        raw['toolVersion'] = manifest['version']
        if config.version_policy != manifest['version']:
            with tempfile.NamedTemporaryFile(dir=config.project_root, prefix='.review-config-', delete=False) as output:
                temporary = Path(output.name)
                try:
                    os.chmod(temporary, config_path.stat().st_mode & 0o777)
                    output.write(_encode(raw))
                    output.flush()
                    os.fsync(output.fileno())
                    if config_path.read_bytes() != original:
                        raise ReleaseError('Concurrent configuration edit', 'configuration_conflict')
                    os.replace(temporary, config_path)
                finally:
                    temporary.unlink(missing_ok=True)
    return {'ok': True, 'projectId': config.project_id, 'toolVersion': manifest['version'],
            'previousToolVersion': config.version_policy, 'releaseRoot': str(target), 'installRoot': str(root),
            'changed': config.version_policy != manifest['version'], 'serviceStarted': False, 'migrationRun': False}
