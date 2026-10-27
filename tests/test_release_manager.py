import dataclasses
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from project_config import setup_project, load_project_config, TOOL_VERSION
from data_lock import acquire_data_lock
from release_manager import (package_release, verify_release, install_release,
                             resolve_project_release, activate_release, ReleaseError)

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns('.git', 'artifacts', '__pycache__'))
        self.install = self.root / 'installation with spaces'
        self.project = self.root / 'consumer'
        self.project.mkdir()
        self.config, _ = setup_project(self.project, {'codex': False})
        self.config.data_dir.mkdir()
        (self.config.data_dir / 'comments.json').write_text('[{"id":"original","updatedAt":"unchanged"}]')
        (self.config.data_dir / 'screenshots').mkdir()
        (self.config.data_dir / 'screenshots/a.png').write_bytes(b'synthetic evidence')

    def tearDown(self):
        self.temp.cleanup()

    def package(self, version=None):
        if version:
            (self.source / 'VERSION').write_text(version + '\n')
        return package_release(self.source, self.root / 'packages')

    def installed(self, version=None):
        return install_release(self.package(version), self.install)

    def data_hashes(self):
        return {str(p.relative_to(self.config.data_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.config.data_dir.rglob('*') if p.is_file()}

    def test_package_excludes_project_data(self):
        for name in ['review-data/comments.json', 'artifacts/job/request.json', '.env',
                     'runtime/credentials.json', 'docs/private.txt', 'skills/web-review/token.txt']:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('DO NOT PACKAGE')
        archive = self.package()
        before = archive.read_bytes()
        self.assertEqual(self.package().read_bytes(), before)
        with tarfile.open(archive) as bundle:
            names = bundle.getnames()
            self.assertIn('release-manifest.json', names)
            self.assertIn('skills/web-review/workflow.json', names)
            self.assertFalse(any('DO NOT PACKAGE' in bundle.extractfile(name).read().decode(errors='ignore') for name in names))

    def test_corrupt_release_is_not_activated(self):
        release = self.installed()
        original = (self.project / 'review.config.json').read_bytes()
        (release / 'runtime/review.js').write_text('corrupt')
        with self.assertRaises(ReleaseError):
            activate_release(self.config, release)
        self.assertEqual((self.project / 'review.config.json').read_bytes(), original)

    def test_repeat_install_preserves_pin_config_data_and_rejects_local_changes(self):
        release = self.installed()
        before = self.data_hashes()
        config = (self.project / 'review.config.json').read_bytes()
        self.assertEqual(self.installed(), release)
        self.assertEqual(resolve_project_release(self.project, self.install), release)
        self.assertEqual(self.data_hashes(), before)
        self.assertEqual((self.project / 'review.config.json').read_bytes(), config)
        (release / 'runtime/review.css').write_text('user edit')
        with self.assertRaises(ReleaseError):
            self.installed()
        self.assertEqual((release / 'runtime/review.css').read_text(), 'user edit')

    def test_upgrade_rollback_preserves_new_comments_and_legacy_metadata(self):
        old = self.installed()
        new = self.installed('0.2.0-test')
        before = self.data_hashes()
        self.assertEqual(activate_release(self.config, new)['toolVersion'], '0.2.0-test')
        self.assertEqual(self.data_hashes(), before)
        (self.config.data_dir / 'comments.json').write_text('[{"id":"new","updatedAt":"still-original"}]')
        after = self.data_hashes()
        activate_release(load_project_config(self.project), old)
        self.assertEqual(self.data_hashes(), after)
        self.assertFalse((self.config.data_dir / 'meta.json').exists())
        self.assertFalse(self.config.jobs_dir.exists())

    def test_running_service_and_active_job_block_switch(self):
        self.installed()
        target = self.installed('0.2.0-test')
        with acquire_data_lock(self.config.data_dir):
            with self.assertRaises(ValueError):
                activate_release(self.config, target)
        job = self.config.jobs_dir / 'synthetic'
        job.mkdir(parents=True)
        (job / 'status.json').write_text('{"status":"running"}')
        before = (job / 'status.json').read_bytes()
        with self.assertRaises(ReleaseError):
            activate_release(self.config, target)
        self.assertEqual((job / 'status.json').read_bytes(), before)

    def test_invalid_foreign_or_new_schema_data_never_mutated(self):
        self.installed()
        target = self.installed('0.2.0-test')
        for value in ['broken', '{"schemaVersion":2,"projectId":"' + self.config.project_id + '"}',
                      '{"schemaVersion":1,"projectId":"foreign"}']:
            (self.config.data_dir / 'meta.json').write_text(value)
            before = self.data_hashes()
            with self.assertRaises(ValueError):
                activate_release(self.config, target)
            self.assertEqual(self.data_hashes(), before)
            self.assertEqual(load_project_config(self.project).tool_version, TOOL_VERSION)

    def test_failed_atomic_switch_preserves_config_and_data(self):
        self.installed()
        target = self.installed('0.2.0-test')
        before = self.data_hashes()
        raw = (self.project / 'review.config.json').read_bytes()
        with patch('release_manager.os.replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                activate_release(self.config, target)
        self.assertEqual((self.project / 'review.config.json').read_bytes(), raw)
        self.assertEqual(self.data_hashes(), before)

    def test_real_router_uses_pin_and_derives_worker_install_root(self):
        old = self.installed()
        new = self.installed('0.2.0-test')
        helper = new / 'skills/web-review/scripts/review.py'
        result = subprocess.run([sys.executable, str(helper), '--project', str(self.project), 'locate'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['releaseRoot'], str(old))
        self.assertEqual(value['installRoot'], str(self.install))
        self.assertFalse((self.config.data_dir / 'meta.json').exists())

    def test_actual_version_is_not_project_requirement(self):
        release = self.installed('0.2.0-test')
        result = subprocess.run([sys.executable, str(release / 'web-review.py'), '--project', str(self.project), 'version'], capture_output=True, text=True)
        value = json.loads(result.stdout)
        self.assertEqual(value['toolVersion'], '0.2.0-test')
        self.assertEqual(value['requiredToolVersion'], TOOL_VERSION)
        self.assertFalse(value['versionMatches'])
        from server import configured_health
        health = configured_health(dataclasses.replace(self.config, tool_version='other'))
        self.assertEqual(health['toolVersion'], TOOL_VERSION)
        self.assertEqual(health['requiredToolVersion'], 'other')

    def test_wrong_package_manifest_and_receipt_modification_rejected(self):
        release = self.installed()
        manifest = release / 'release-manifest.json'
        raw = json.loads(manifest.read_text())
        raw['package'] = 'someone-elses-tool'
        manifest.write_text(json.dumps(raw))
        with self.assertRaises(ReleaseError):
            verify_release(release)
        raw['package'] = 'web-review-kit'
        manifest.write_text(json.dumps(raw))
        with self.assertRaises(ReleaseError):
            resolve_project_release(self.project, self.install)

    def test_archive_path_escape_and_symlinks_rejected(self):
        archive = self.root / 'bad.tar.gz'
        for name in ['../escaped', '/absolute/escape', 'runtime/server.py']:
            with tarfile.open(archive, 'w:gz') as bundle:
                member = tarfile.TarInfo(name)
                if name == 'runtime/server.py':
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/tmp/unsafe'
                bundle.addfile(member, io.BytesIO(b''))
            with self.assertRaises(ReleaseError):
                install_release(archive, self.install)
            self.assertFalse((self.root / 'escaped').exists())
            self.assertEqual(list((self.install / 'releases').iterdir()), [])

    def test_locked_job_and_modified_current_release_block_upgrade(self):
        current = self.installed()
        target = self.installed('0.2.0-test')
        self.config.jobs_dir.mkdir(parents=True)
        with (self.config.jobs_dir / 'active.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ReleaseError):
                activate_release(self.config, target)
        (current / 'runtime/server.py').write_text('local modification')
        with self.assertRaises(ReleaseError):
            activate_release(self.config, target)
        self.assertEqual(load_project_config(self.project).tool_version, TOOL_VERSION)

    def test_doctor_mismatch_checks_workflow_without_protocol_call(self):
        from codex_doctor import doctor
        config = dataclasses.replace(self.config, tool_version='0.0.0-wrong')
        result = doctor(config)
        self.assertEqual(result['toolVersion'], TOOL_VERSION)
        self.assertEqual(result['requiredToolVersion'], '0.0.0-wrong')
        self.assertFalse(result['versionMatches'])
        self.assertFalse(result['capabilities']['review'])
        self.assertTrue(any(check['name'] == 'workflow' and check['ok'] for check in result['checks']))
        self.assertFalse((self.config.data_dir / 'meta.json').exists())

    def test_packaged_worker_freezes_verified_install_and_compat_infers_consumer(self):
        release = self.installed()
        launcher = self.project / 'tools/review/server.py'
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(release / 'compat/server.py')
        code = '''import json,runpy,sys
module=runpy.run_path(sys.argv[1],run_name='compat_check')
main=module['main']
from codex_tasks import execution_config_for
main.__globals__['serve_project']=lambda config: print(json.dumps({'project':str(config.project_root),'codexEnabled':config.codex['enabled'],'execution':execution_config_for(config)}))
main.__globals__['webbrowser'].open=lambda url: None
raise SystemExit(main(['--open','--codex']))
'''
        result = subprocess.run([sys.executable, '-c', code, str(launcher)], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['project'], str(self.project))
        self.assertTrue(value['codexEnabled'])
        self.assertEqual(value['execution']['installRoot'], str(self.install))
        self.assertEqual(value['execution']['skillPath'], str(release / 'skills/web-review/SKILL.md'))

    def test_cli_upgrade_rollback_and_missing_workflow(self):
        old = self.installed()
        new = self.installed('0.2.0-test')
        helper = old / 'skills/web-review/scripts/review.py'
        before = self.data_hashes()
        for command, target in [('update', new), ('rollback', old)]:
            result = subprocess.run([sys.executable, str(helper), '--project', str(self.project), command, '--target', str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(load_project_config(self.project).tool_version, target.name)
            self.assertFalse(json.loads(result.stdout)['serviceStarted'])
        self.assertEqual(self.data_hashes(), before)
        (old / 'skills/web-review/workflow.json').write_text('{"workflowVersion":99}')
        result = subprocess.run([sys.executable, str(helper), '--project', str(self.project), 'locate'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertFalse(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
