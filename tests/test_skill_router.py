import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / 'skills/web-review/scripts/review.py'


def load_router():
    spec = importlib.util.spec_from_file_location('skill_review_router', ROUTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillRouterTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('WEB_REVIEW_REQUEST_PATH', 'WEB_REVIEW_HELPER'):
            os.environ.pop(name, None)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'consumer project'
        self.project.mkdir()
        self.config = {'configVersion': 1, 'projectId': 'synthetic', 'toolVersion': '0.1.0-old'}
        (self.project / 'review.config.json').write_text(json.dumps(self.config))
        self.install = self.root / 'installation'
        self.old = self.release('0.1.0-old')
        self.new = self.release('0.2.0-new')
        self.resolver_calls = []
        self.resolver = types.ModuleType('release_manager')
        def resolve(project, install):
            self.resolver_calls.append((project, install))
            return self.old
        self.resolver.resolve_project_release = resolve

    def tearDown(self):
        self.temp.cleanup()

    def release(self, version):
        release = self.install / 'releases' / version
        skill = release / 'skills/web-review'
        (skill / 'references').mkdir(parents=True)
        (release / 'VERSION').write_text(version + '\n')
        (skill / 'workflow.json').write_text(json.dumps({'workflowVersion': 1}))
        (skill / 'SKILL.md').write_text('Synthetic skill')
        for name in ('project-setup.md', 'comment-workflow.md'):
            (skill / 'references' / name).write_text(version + ' ' + name)
        (release / 'web-review.py').write_text(
            'import json,sys\nprint(json.dumps({"runtime": ' + repr(version) + ', "argv": sys.argv[1:]}))\n')
        return release

    def run_router(self, *args, resolver=True):
        router = load_router()
        import contextlib
        import io
        output = io.StringIO()
        modules = {'release_manager': self.resolver} if resolver else {'release_manager': None}
        with patch.dict(sys.modules, modules), contextlib.redirect_stdout(output):
            code = router.main(['--project', str(self.project), '--install-root', str(self.install), *args])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def request(self):
        request = {'project': str(self.project), 'data': str(self.project / 'reviews'),
                   'reviewUrl': 'http://127.0.0.1:18555/frozen',
                   'executionConfig': {**{key: self.config[key] for key in ('projectId', 'toolVersion')},
                                       'guidance': {'requiredFiles': ['consumer.md'], 'sourceRoots': ['src'],
                                                    'buildCommands': [], 'checkCommands': []},
                                       'codex': {'enabled': True},
                                       'skillPath': str(self.old / 'skills/web-review/SKILL.md')},
                   'comments': [{'id': 'comment-1', 'updatedAt': 'frozen-time', 'status': 'open',
                                 'text': 'Synthetic', 'attachments': [{'url': '/original.png'}]}]}
        path = self.root / 'request.json'
        path.write_text(json.dumps(request))
        return path, request

    def test_router_uses_project_pin(self):
        router = load_router()
        with patch.dict(sys.modules, {'release_manager': self.resolver}), patch.object(router, 'HOST_ROOT', self.new), patch.object(router.subprocess, 'run') as run:
            run.return_value.returncode = 0
            code = router.main(['--project', str(self.project), '--install-root', str(self.install), 'show', '--id', 'comment-1'])
        self.assertEqual(code, 0)
        self.assertEqual(self.resolver_calls, [(self.project, self.install)])
        self.assertEqual(Path(run.call_args.args[0][1]), self.old / 'web-review.py')
        self.assertNotIn(str(self.new), repr(run.call_args))

    def test_missing_release_does_not_fallback(self):
        def missing(*args):
            raise FileNotFoundError('Pinned release absent')
        self.resolver.resolve_project_release = missing
        router = load_router()
        with patch.dict(sys.modules, {'release_manager': self.resolver}), patch.object(router, 'HOST_ROOT', self.new), patch.object(router.subprocess, 'run') as run:
            with patch('sys.stdout'):
                code = router.main(['--project', str(self.project), '--install-root', str(self.install), 'list'])
        self.assertEqual(code, 2)
        run.assert_not_called()
        self.assertEqual(json.loads((self.project / 'review.config.json').read_text()), self.config)

    def test_unavailable_resolver_is_explicit(self):
        code, result = self.run_router('locate', resolver=False)
        self.assertEqual(code, 2)
        self.assertEqual(result['error'], 'resolver_unavailable')

    def test_incompatible_workflow_and_wrong_release_are_rejected(self):
        (self.old / 'skills/web-review/workflow.json').write_text('{"workflowVersion": 99}')
        code, result = self.run_router('locate')
        self.assertEqual((code, result['error']), (2, 'workflow_unavailable'))
        (self.old / 'VERSION').write_text('wrong-version')
        code, result = self.run_router('locate')
        self.assertEqual((code, result['error']), (3, 'version_conflict'))

    def test_locate_returns_pinned_references(self):
        code, result = self.run_router('locate')
        self.assertEqual(code, 0)
        workflow = Path(result['commentWorkflow'])
        self.assertTrue(workflow.is_relative_to(self.old))
        self.assertIn('0.1.0-old', workflow.read_text())

    def test_worker_snapshot_is_single_frozen_record_and_exclusive(self):
        path, request = self.request()
        before = path.read_bytes()
        destination = self.root / 'frozen.json'
        code, result = self.run_router('--request', str(path), 'snapshot', '--id', 'comment-1', '--output', str(destination))
        self.assertEqual(code, 0, result)
        frozen = json.loads(destination.read_text())
        self.assertEqual(frozen['comment'], request['comments'][0])
        self.assertEqual(frozen['projectId'], 'synthetic')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.run_router('--request', str(path), 'snapshot', '--id', 'comment-1', '--output', str(destination))[0], 2)
        self.assertEqual(json.loads(destination.read_text()), frozen)

    def test_worker_endpoint_and_guidance_remain_frozen(self):
        path, request = self.request()
        router = load_router()
        with patch.dict(sys.modules, {'release_manager': self.resolver}), patch.object(router.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(router.main(['--project', str(self.project), '--install-root', str(self.install),
                                         '--request', str(path), 'show', '--id', 'comment-1']), 0)
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index('--review-url') + 1], request['reviewUrl'])
        code, result = self.run_router('--request', str(path), 'locate')
        self.assertEqual(result['executionConfig'], request['executionConfig'])
        self.assertEqual(result['reviewUrl'], request['reviewUrl'])

    def test_worker_identity_drift_or_endpoint_override_stops(self):
        path, request = self.request()
        code, result = self.run_router('--request', str(path), '--review-url', 'http://127.0.0.1:1', 'list')
        self.assertEqual((code, result['error']), (3, 'request_conflict'))
        request['executionConfig']['toolVersion'] = '0.0.0-obsolete'
        path.write_text(json.dumps(request))
        code, result = self.run_router('--request', str(path), 'locate')
        self.assertEqual((code, result['error']), (3, 'request_conflict'))

    def test_worker_does_not_setup_serve_or_dispatch(self):
        path, _ = self.request()
        for command in ('setup', 'serve', 'update', 'rollback', 'dispatch', 'worker'):
            with self.subTest(command=command):
                self.assertEqual(self.run_router('--request', str(path), command)[0], 2)

    def test_worker_refuses_comments_outside_batch_and_replaced_snapshot(self):
        path, request = self.request()
        self.assertEqual(self.run_router('--request', str(path), 'show', '--id', 'other-comment')[0], 2)
        frozen = self.root / 'altered.json'
        frozen.write_text(json.dumps({**request['comments'][0], 'updatedAt': 'refreshed-without-permission'}))
        code, result = self.run_router('--request', str(path), 'mark-changed', '--id', 'comment-1',
                                       '--snapshot', str(frozen), '--resolution-file', 'unused.txt')
        self.assertEqual((code, result['error']), (3, 'request_conflict'))

    def test_worker_version_does_not_forward_review_url(self):
        path, _ = self.request()
        router = load_router()
        with patch.dict(sys.modules, {'release_manager': self.resolver}), patch.object(router.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(router.main(['--project', str(self.project), '--install-root', str(self.install),
                                         '--request', str(path), 'version']), 0)
        self.assertNotIn('--review-url', run.call_args.args[0])

    def test_isolated_skill_discovery_and_call(self):
        import shutil
        isolated_host = self.root / 'isolated host'
        isolated_skill = isolated_host / 'skills/web-review'
        shutil.copytree(ROOT / 'skills/web-review', isolated_skill)
        runtime = isolated_host / 'runtime'
        runtime.mkdir()
        (runtime / 'release_manager.py').write_text(
            'from pathlib import Path\ndef resolve_project_release(project_root, install_root):\n'
            '    return Path(install_root) / "releases" / "0.1.0-old"\n')
        discovered = list((isolated_host / 'skills').glob('*/SKILL.md'))
        self.assertEqual(discovered, [isolated_skill / 'SKILL.md'])
        result = subprocess.run([sys.executable, str(isolated_skill / 'scripts/review.py'),
                                 '--project', str(self.project), '--install-root', str(self.install), 'version'],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['runtime'], '0.1.0-old')


if __name__ == '__main__':
    unittest.main()
