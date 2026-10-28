"""Global selection boundaries use only temporary packages and synthetic consumers."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

from project_config import TOOL_VERSION, load_project_config
from release_manager import (activate_global_release, resolve_global_release,
                             resolve_project_release, resolve_frozen_release, ReleaseError)
import test_release_manager as release_tests

ROOT = release_tests.ROOT


class GlobalRuntimeTests(unittest.TestCase):
    setUp = release_tests.ReleaseTests.setUp
    tearDown = release_tests.ReleaseTests.tearDown
    package = release_tests.ReleaseTests.package
    installed = release_tests.ReleaseTests.installed
    data_hashes = release_tests.ReleaseTests.data_hashes

    def package_without_global_capability(self):
        with tarfile.open(self.package('0.1.0-rc.9'), 'r:gz') as bundle:
            contents = {name: bundle.extractfile(name).read() for name in bundle.getnames()}
        manifest = json.loads(contents['release-manifest.json'])
        del manifest['runtimeSelection']
        contents['release-manifest.json'] = json.dumps(manifest).encode()
        archive = self.root / 'legacy.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, value in contents.items():
                item = tarfile.TarInfo(name)
                item.size = len(value)
                bundle.addfile(item, io.BytesIO(value))
        return archive

    def policy(self, value='global'):
        path = self.project / 'review.config.json'
        raw = json.loads(path.read_text())
        raw['toolVersion'] = value
        path.write_text(json.dumps(raw))
        return path.read_bytes()

    def invoke(self, release, *args, project=None):
        command = [sys.executable, str(release / 'skills/web-review/scripts/review.py'),
                   '--project', str(project or self.project), *map(str, args)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=15)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def request(self, release):
        value = {'project': str(self.project), 'data': str(self.config.data_dir),
                 'reviewUrl': 'http://127.0.0.1:19876/frozen',
                 'executionConfig': {'projectId': self.config.project_id,
                    'toolVersion': release.name, 'toolVersionPolicy': 'global',
                    'installRoot': str(self.install),
                    'skillPath': str(release / 'skills/web-review/SKILL.md'),
                    'guidance': self.config.guidance, 'codex': {}},
                 'comments': [{'id': 'synthetic-1', 'updatedAt': 'original', 'status': 'open'}]}
        path = self.root / 'request.json'
        path.write_text(json.dumps(value))
        return path, value

    def test_global_switch_keeps_pin_and_frozen_worker_concrete(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        activate_global_release(old, self.install)
        self.assertEqual(resolve_project_release(self.project, self.install), old)
        activate_global_release(new, self.install)
        self.assertEqual(resolve_project_release(self.project, self.install), old)
        before = self.policy()
        data = self.data_hashes()
        request, raw = self.request(old)
        self.assertEqual(resolve_project_release(self.project, self.install), new)
        for command in ('locate', 'version'):
            code, value = self.invoke(new, '--request', request, command)
            self.assertEqual(code, 0, value)
            self.assertEqual(value['toolVersion'], old.name)
        code, value = self.invoke(old, 'locate')
        self.assertEqual(code, 0, value)
        self.assertEqual(value['releaseRoot'], str(new))
        self.assertEqual(value['runtimeRoot'], str(new / 'runtime'))
        self.assertEqual(value['toolVersionPolicy'], 'global')
        self.assertEqual((self.project / 'review.config.json').read_bytes(), before)
        self.assertEqual(self.data_hashes(), data)
        self.assertEqual(json.loads(request.read_text()), raw)
        # A frozen invocation still works when the default disappears entirely.
        (self.install / 'current').unlink()
        self.assertEqual(self.invoke(new, '--request', request, 'version')[0], 0)
        self.assertEqual(self.invoke(new, 'locate')[0], 2)

    def test_frozen_identity_policy_skill_and_receipt_are_verified(self):
        release = self.installed()
        self.policy()
        path, request = self.request(release)
        for field, wrong in [('projectId', 'foreign'), ('toolVersionPolicy', release.name),
                             ('skillPath', str(self.root / 'foreign/SKILL.md')),
                             ('installRoot', str(self.root / 'different-install'))]:
            original = request['executionConfig'][field]
            request['executionConfig'][field] = wrong
            path.write_text(json.dumps(request))
            with self.subTest(field=field):
                self.assertEqual(self.invoke(release, '--request', path, 'locate')[0], 3)
            request['executionConfig'][field] = original
        path.write_text(json.dumps(request))
        self.policy(release.name)
        self.assertEqual(self.invoke(release, '--request', path, 'locate')[0], 3)
        self.policy()
        (self.install / 'receipts' / (release.name + '.json')).write_text('{}')
        self.assertEqual(self.invoke(release, '--request', path, 'locate')[0], 3)

    def test_missing_tampered_outside_and_unmanaged_current_rejected(self):
        release = self.installed()
        self.policy()
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)
        current = self.install / 'current'
        current.write_text('unmanaged')
        with self.assertRaises(ReleaseError):
            activate_global_release(release, self.install)
        self.assertEqual(current.read_text(), 'unmanaged')
        current.unlink()
        current.symlink_to(self.root / 'outside')
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)
        current.unlink()
        current.symlink_to('current')
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)
        current.unlink()
        current.symlink_to('releases/missing')
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)
        current.unlink()
        activate_global_release(release, self.install)
        (release / 'runtime/server.py').write_text('tampered')
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)

    def test_activation_skill_upgrade_is_stable_and_idempotent(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        link = self.root / 'agent-skills/web-review'
        link.parent.mkdir()
        link.symlink_to(old / 'skills/web-review')
        value = activate_global_release(old, self.install, skill_link=link)
        self.assertTrue(value['changed'])
        self.assertEqual(os.readlink(link), str(self.install / 'current/skills/web-review'))
        value = activate_global_release(new, self.install, skill_link=link)
        self.assertEqual(link.resolve(), new / 'skills/web-review')
        self.assertEqual(value['previousToolVersion'], old.name)
        before = os.readlink(link)
        self.assertFalse(activate_global_release(new, self.install, skill_link=link)['changed'])
        self.assertEqual(os.readlink(link), before)

    def test_activation_conflicts_preserve_previous_default_and_discovery(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        activate_global_release(old, self.install)
        link = self.root / 'unmanaged-skill'
        for kind in ('directory', 'foreign-link'):
            if kind == 'directory':
                link.mkdir()
            else:
                link.symlink_to(self.root / 'unmanaged-target')
            with self.subTest(kind=kind), self.assertRaises(ReleaseError):
                activate_global_release(new, self.install, skill_link=link)
            self.assertEqual(resolve_global_release(self.install), old)
            if kind == 'directory':
                self.assertTrue(link.is_dir())
                link.rmdir()
            else:
                self.assertEqual(os.readlink(link), str(self.root / 'unmanaged-target'))
                link.unlink()
        with patch('release_manager.os.replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                activate_global_release(new, self.install)
        self.assertEqual(resolve_global_release(self.install), old)

    def test_installed_setup_defaults_global_only_with_current_checkout_stays_pinned(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        for name, helper, expected in [('no-current', old, old.name), ('checkout', ROOT, TOOL_VERSION)]:
            project = self.root / name
            project.mkdir()
            command = [sys.executable, str(helper / 'web-review.py'), '--project', str(project), 'setup', '--no-codex']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((project / 'review.config.json').read_text())['toolVersion'], expected)
        activate_global_release(new, self.install)
        project = self.root / 'new-global'
        project.mkdir()
        code, value = self.invoke(old, 'setup', '--no-codex', project=project)
        self.assertEqual(code, 0, value)
        self.assertEqual(json.loads((project / 'review.config.json').read_text())['toolVersion'], 'global')
        self.assertEqual(value['toolVersion'], new.name)
        # Source checkout never silently accepts a configured global policy.
        self.policy()
        result = subprocess.run([sys.executable, str(ROOT / 'web-review.py'), '--project', str(self.project), 'version'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_installer_activation_and_same_archive_are_idempotent(self):
        archive = self.package()
        before_config = (self.project / 'review.config.json').read_bytes()
        before_data = self.data_hashes()
        for name, flags in [('default', []), ('explicit', ['--activate-global'])]:
            with self.subTest(mode=name):
                installation = self.root / name
                link = self.root / (name + '-skills/web-review')
                command = [sys.executable, str(ROOT / 'scripts/install.py'), '--archive', str(archive),
                           '--install-root', str(installation), '--skill-link', str(link), *flags]
                for expected in (True, False):
                    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    value = json.loads(result.stdout)
                    self.assertEqual(value['changed'], expected)
                    self.assertTrue(value['globalActivated'])
                    self.assertFalse(value['serviceStarted'])
                release = installation / 'releases' / TOOL_VERSION
                self.assertEqual(resolve_global_release(installation), release)
                self.assertEqual(os.readlink(link), str(installation / 'current/skills/web-review'))
                self.assertEqual(link.resolve(), release / 'skills/web-review')
        self.assertEqual((self.project / 'review.config.json').read_bytes(), before_config)
        self.assertEqual(self.data_hashes(), before_data)

    def test_installer_opt_out_preserves_existing_default_and_skill(self):
        old = self.installed()
        link = self.root / 'agent-skills/web-review'
        activate_global_release(old, self.install, skill_link=link)
        before_current = os.readlink(self.install / 'current')
        before_skill = os.readlink(link)
        before_config = (self.project / 'review.config.json').read_bytes()
        before_data = self.data_hashes()
        archive = self.package('0.2.0-next')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--archive', str(archive), '--install-root', str(self.install),
                                 '--no-activate-global'], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['toolVersion'], '0.2.0-next')
        self.assertFalse(value.get('globalActivated', False))
        self.assertFalse(value['serviceStarted'])
        self.assertTrue((self.install / 'releases/0.2.0-next/release-manifest.json').is_file())
        self.assertEqual(os.readlink(self.install / 'current'), before_current)
        self.assertEqual(os.readlink(link), before_skill)
        self.assertEqual(link.resolve(), old / 'skills/web-review')
        self.assertEqual(resolve_global_release(self.install), old)
        self.assertEqual((self.project / 'review.config.json').read_bytes(), before_config)
        self.assertEqual(self.data_hashes(), before_data)

    def test_installer_opt_out_on_fresh_root_uses_explicit_fixed_skill_link(self):
        archive = self.package()
        link = self.root / 'agent-skills/web-review'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--archive', str(archive), '--install-root', str(self.install),
                                 '--no-activate-global', '--skill-link', str(link)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        release = self.install / 'releases' / TOOL_VERSION
        self.assertEqual(value['releaseRoot'], str(release))
        self.assertFalse(value.get('globalActivated', False))
        self.assertFalse((self.install / 'current').exists())
        self.assertFalse((self.install / 'current').is_symlink())
        self.assertEqual(os.readlink(link), str(release / 'skills/web-review'))

    def test_installer_default_activation_leaves_skill_discovery_explicit(self):
        archive = self.package()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--archive', str(archive), '--install-root', str(self.install)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value['globalActivated'])
        self.assertIsNone(value['skillLink'])
        self.assertEqual(resolve_global_release(self.install), self.install / 'releases' / TOOL_VERSION)

    def test_installer_default_conflicting_skill_preserves_current_and_discovery(self):
        old = self.installed()
        activate_global_release(old, self.install)
        archive = self.package('0.2.0-next')
        link = self.root / 'foreign-skill'
        link.symlink_to(self.root / 'foreign-target')
        before_current = os.readlink(self.install / 'current')
        before_skill = os.readlink(link)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--archive', str(archive), '--install-root', str(self.install),
                                 '--skill-link', str(link)], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)['ok'])
        self.assertEqual(os.readlink(self.install / 'current'), before_current)
        self.assertEqual(os.readlink(link), before_skill)
        self.assertEqual(resolve_global_release(self.install), old)

    def test_installer_rejects_both_activation_flags_before_installing(self):
        archive = self.package()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--archive', str(archive), '--install-root', str(self.install),
                                 '--activate-global', '--no-activate-global'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('not allowed with argument', result.stderr)
        self.assertFalse(self.install.exists())

    def test_installer_historical_release_needs_explicit_activation_opt_out(self):
        current = self.installed()
        activate_global_release(current, self.install)
        before_current = os.readlink(self.install / 'current')
        archive = self.package_without_global_capability()
        command = [sys.executable, str(ROOT / 'scripts/install.py'),
                   '--archive', str(archive), '--install-root', str(self.install)]
        rejected = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)['error'], 'global_runtime_unsupported')
        self.assertEqual(os.readlink(self.install / 'current'), before_current)
        link = self.root / 'legacy-skills/web-review'
        allowed = subprocess.run(command + ['--no-activate-global', '--skill-link', str(link)],
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        value = json.loads(allowed.stdout)
        self.assertEqual(value['toolVersion'], '0.1.0-rc.9')
        self.assertFalse(value.get('globalActivated', False))
        self.assertEqual(os.readlink(link), str(self.install / 'releases/0.1.0-rc.9/skills/web-review'))
        self.assertEqual(os.readlink(self.install / 'current'), before_current)
        self.assertEqual(resolve_global_release(self.install), current)

    def test_loaded_service_and_execution_remain_old_but_startup_race_rejected(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(old, self.install)
        # Switch after config is loaded. Frozen execution remains old; startup must reject.
        script = r"""import json,sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'runtime'))
from project_config import load_project_config
from codex_tasks import execution_config_for
from server import configured_health, serve_project
from release_manager import activate_global_release
config=load_project_config(Path(sys.argv[2]))
activate_global_release(Path(sys.argv[3]), Path(sys.argv[4]))
execution=execution_config_for(config)
try:
    serve_project(config)
except ValueError as error:
    print(json.dumps({'execution':execution,'health':configured_health(config),'error':error.code}))
"""
        result = subprocess.run([sys.executable, '-c', script, str(old), str(self.project), str(new), str(self.install)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['execution']['toolVersion'], old.name)
        self.assertEqual(value['execution']['toolVersionPolicy'], 'global')
        self.assertEqual(value['health']['toolVersion'], old.name)
        self.assertEqual(value['error'], 'version_conflict')

    def test_resumed_worker_spawn_uses_frozen_release(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(new, self.install)
        path, request = self.request(old)
        directory = self.root / 'synthetic-job'
        directory.mkdir()
        (directory / 'request.json').write_bytes(path.read_bytes())
        script = r"""import json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(sys.argv[1]) / 'runtime'))
from codex_tasks import CodexTasks
manager=CodexTasks(Path(sys.argv[2]), Path(sys.argv[2])/'reviews', Path(sys.argv[2])/'jobs')
with (Path(sys.argv[3])/'lock').open('a') as handle, patch('codex_tasks.subprocess.Popen') as spawn:
    manager._spawn(Path(sys.argv[3]), handle)
    print(json.dumps(spawn.call_args.args[0]))
"""
        result = subprocess.run([sys.executable, '-c', script, str(new), str(self.project), str(directory)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)[1], str(old / 'runtime/codex_tasks.py'))


    def test_old_manifest_remains_verifiable_but_cannot_be_global(self):
        from release_manager import install_release, verify_release
        current = self.installed()
        activate_global_release(current, self.install)
        old = install_release(self.package_without_global_capability(), self.install)
        self.assertEqual(verify_release(old)['version'], old.name)
        self.policy(old.name)
        self.assertEqual(resolve_project_release(self.project, self.install), old)
        with self.assertRaises(ReleaseError) as raised:
            activate_global_release(old, self.install)
        self.assertEqual(raised.exception.code, 'global_runtime_unsupported')
        self.assertEqual(resolve_global_release(self.install), current)
        (self.install / 'current').unlink()
        (self.install / 'current').symlink_to(old)
        with self.assertRaises(ReleaseError):
            resolve_global_release(self.install)

    def test_concrete_compat_does_not_redirect_global_after_selection_race(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(new, self.install)
        result = subprocess.run([sys.executable, str(old / 'compat/server.py'),
                                 '--project', str(self.project)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error'], 'version_conflict')
        self.assertFalse((self.config.data_dir / 'meta.json').exists())

    def test_current_switch_during_server_lock_acquisition_closes_server(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(old, self.install)
        script = r"""import json,sys
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0, str(Path(sys.argv[1]) / 'runtime'))
from project_config import load_project_config
from release_manager import activate_global_release
from server import serve_project
server=Mock()
def acquire(*args,**kwargs):
    activate_global_release(Path(sys.argv[3]), Path(sys.argv[4]))
    return server
with patch('server.make_server', side_effect=acquire):
    try:
        serve_project(load_project_config(Path(sys.argv[2])))
    except ValueError as error:
        print(json.dumps({'error':error.code,'closed':server.server_close.called,'started':server.serve_forever.called}))
"""
        result = subprocess.run([sys.executable, '-c', script, str(old), str(self.project), str(new), str(self.install)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'error': 'version_conflict', 'closed': True, 'started': False})


    def test_second_publication_failure_restores_fixed_or_missing_skill(self):
        release = self.installed()
        link = self.root / 'skills/web-review'
        link.parent.mkdir()
        real_replace = os.replace
        def fail_current(source, destination):
            if destination == self.install / 'current':
                raise OSError('second publication failed')
            return real_replace(source, destination)
        for existed in (True, False):
            if existed:
                link.symlink_to(release / 'skills/web-review')
            with self.subTest(existed=existed), patch('release_manager.os.replace', side_effect=fail_current):
                with self.assertRaises(OSError):
                    activate_global_release(release, self.install, skill_link=link)
            self.assertFalse((self.install / 'current').exists())
            self.assertFalse((self.install / 'current').is_symlink())
            if existed:
                self.assertEqual(os.readlink(link), str(release / 'skills/web-review'))
                self.assertTrue(link.exists())
                link.unlink()
            else:
                self.assertFalse(link.is_symlink())

    def test_frozen_build_environment_handles_comments_and_annotations(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(new, self.install)
        path, request = self.request(old)
        environment = dict(os.environ, WEB_REVIEW_REQUEST_PATH=str(path),
                           WEB_REVIEW_HELPER=str(old / 'skills/web-review/scripts/review.py'))
        script = "import os,subprocess,sys; raise SystemExit(subprocess.run([sys.executable,os.environ['WEB_REVIEW_HELPER'],'--project',sys.argv[1],'locate']).returncode)"
        for kind in ('comments', 'annotation'):
            if kind == 'annotation':
                request.pop('comments')
                request.update(kind='annotation', annotation={'id': 'annotation-synthetic'})
                path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, '-c', script, str(self.project)], env=environment,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['releaseRoot'], str(old))
        self.assertEqual(self.invoke(new, '--request', path, 'locate')[0], 2)
        request['project'] = str(self.root / 'foreign')
        path.write_text(json.dumps(request))
        result = subprocess.run([sys.executable, '-c', script, str(self.project)], env=environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(json.loads(result.stdout)['error'], 'request_conflict')
        path.unlink()
        result = subprocess.run([sys.executable, '-c', script, str(self.project)], env=environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_app_server_environment_uses_actual_request_and_clears_inherited_context(self):
        from codex_session import AppServer
        old = self.installed()
        self.policy()
        path, request = self.request(old)
        request['executable'] = sys.executable
        request['requestPath'] = str(self.root / 'untrusted-payload.json')
        with patch.dict(os.environ, WEB_REVIEW_REQUEST_PATH='stale', WEB_REVIEW_HELPER='stale-helper'):
            with patch('codex_session.subprocess.Popen') as spawn, patch('codex_session.threading.Thread'):
                server = AppServer(request, path.parent, lambda *_: None, log_events=False)
                environment = spawn.call_args.kwargs['env']
                self.assertEqual(environment['WEB_REVIEW_REQUEST_PATH'], str(path))
                self.assertEqual(environment['WEB_REVIEW_HELPER'], str(old / 'skills/web-review/scripts/review.py'))
                server.close()
            with patch('codex_session.subprocess.Popen') as spawn, patch('codex_session.threading.Thread'):
                server = AppServer({'project': str(self.project), 'executable': sys.executable}, path.parent, lambda *_: None, log_events=False)
                environment = spawn.call_args.kwargs['env']
                self.assertNotIn('WEB_REVIEW_REQUEST_PATH', environment)
                self.assertNotIn('WEB_REVIEW_HELPER', environment)
                server.close()

    def test_global_change_while_reusing_service_is_rejected(self):
        old = self.installed()
        new = self.installed('0.2.0-next')
        self.policy()
        activate_global_release(old, self.install)
        script = r"""import errno,io,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(sys.argv[1]) / 'runtime'))
from project_config import load_project_config
from release_manager import activate_global_release
from server import serve_project,configured_health
config=load_project_config(Path(sys.argv[2]))
def acquire(*args,**kwargs):
    activate_global_release(Path(sys.argv[3]), Path(sys.argv[4]))
    raise OSError(errno.EADDRINUSE, 'synthetic occupied port')
with patch('server.make_server', side_effect=acquire), patch('server.urlopen', return_value=io.StringIO(json.dumps(configured_health(config)))):
    try:
        serve_project(config)
    except ValueError as error:
        print(json.dumps({'error':error.code}))
"""
        result = subprocess.run([sys.executable, '-c', script, str(old), str(self.project), str(new), str(self.install)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'error': 'version_conflict'})

    def test_invalid_frozen_resume_preserves_history_and_releases_lock(self):
        from codex_tasks import CodexTasks, write_json
        release = self.installed()
        self.policy()
        path, request = self.request(release)
        request['executionConfig']['toolVersionPolicy'] = release.name  # A previous explicit pin.
        manager = CodexTasks(self.project, self.config.data_dir, self.config.jobs_dir, sys.executable)
        directory = manager.output / ('b' * 32)
        directory.mkdir()
        write_json(directory / 'request.json', request)
        job = {'id': directory.name, 'status': 'completed', 'threadId': 'synthetic-thread',
               'messages': [], 'result': 'original result', 'startedAt': 1, 'finishedAt': 2,
               'comments': [], 'transport': 'app-server'}
        write_json(directory / 'status.json', job)
        write_json(manager.output / 'current.json', {'id': directory.name})
        before = (directory / 'status.json').read_bytes()
        with patch('codex_tasks.subprocess.Popen') as spawn:
            with self.assertRaises(ReleaseError):
                manager.message(directory.name, 'a' * 32, 'Followup')
            spawn.assert_not_called()
        self.assertEqual((directory / 'status.json').read_bytes(), before)
        self.assertFalse((directory / 'inbox' / ('a' * 32 + '.json')).exists())
        lock = manager._lock()
        self.assertIsNotNone(lock)
        lock.close()

    def test_invalid_new_request_fails_without_active_job_or_process(self):
        from codex_tasks import CodexTasks
        release = self.installed()
        self.policy()
        _, request = self.request(release)
        request['executionConfig']['toolVersionPolicy'] = release.name
        manager = CodexTasks(self.project, self.config.data_dir, self.config.jobs_dir, sys.executable,
                             execution_config=request['executionConfig'])
        comment = {'id': 'synthetic', 'number': 1, 'text': 'edit', 'updatedAt': 'original'}
        with patch('codex_tasks.subprocess.Popen') as spawn:
            with self.assertRaises(ValueError):
                manager.start([comment], request['reviewUrl'])
            spawn.assert_not_called()
        statuses = list(manager.output.glob('*/status.json'))
        self.assertEqual(len(statuses), 1)
        self.assertEqual(json.loads(statuses[0].read_text())['status'], 'failed')
        lock = manager._lock()
        self.assertIsNotNone(lock)
        lock.close()


if __name__ == '__main__':
    unittest.main()
