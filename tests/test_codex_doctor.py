import contextlib
import dataclasses
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_doctor import doctor
from project_config import setup_project

FIXTURE = Path(__file__).with_name('codex_app_server_fixture.py').read_text()


class CodexDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-doctor-test-')
        self.root = Path(self.temp.name).resolve()
        self.exe = self.root / 'fake-codex'; self.exe.write_text(FIXTURE); self.exe.chmod(0o755)
        self.skill = self.root / 'test-skill.md'; self.skill.write_text('test skill')
        self.config, _ = setup_project(self.root, {'codex': True, 'codex_bin': str(self.exe)})
        self.skill_patch = patch('codex_doctor.skill_path', return_value=self.skill)
        self.skill_patch.start()

    def tearDown(self):
        self.skill_patch.stop(); self.temp.cleanup()

    def checks(self, result):
        return {check['name']: check for check in result['checks']}

    def test_execution_snapshot_omits_unset_model_and_provider_credentials(self):
        from codex_tasks import execution_config_for
        config = dataclasses.replace(self.config, codex={**self.config.codex, 'apiKey': 'SENSITIVE'})
        snapshot = execution_config_for(config)
        self.assertNotIn('model', snapshot['codex'])
        self.assertNotIn('SENSITIVE', json.dumps(snapshot))
        self.assertTrue(Path(snapshot['skillPath']).is_absolute())
        config = dataclasses.replace(config, codex={**config.codex, 'model': 'explicit-model'})
        self.assertEqual(execution_config_for(config)['codex']['model'], 'explicit-model')

    def test_ready_checks_auth_without_creating_thread_turn_or_review_data(self):
        result = doctor(self.config)
        self.assertTrue(result['ready'], result)
        self.assertTrue(result['capabilities']['codex'])
        self.assertFalse(result['capabilities']['modelTaskVerified'])
        methods = [json.loads(line).get('method') for line in (self.root / 'rpc.jsonl').read_text().splitlines()]
        self.assertEqual(methods, ['initialize', 'initialized', 'account/read'])
        self.assertFalse(self.config.data_dir.exists()); self.assertFalse(self.config.jobs_dir.exists())
        self.assertNotIn('SENSITIVE', json.dumps(result))
        self.assertNotIn('account', result)

    def test_cli_missing_and_bare_name_uses_path(self):
        missing = dataclasses.replace(self.config, codex={**self.config.codex, 'executable': 'missing-fixture-codex'})
        self.assertFalse(self.checks(doctor(missing))['cli']['ok'])
        self.assertFalse((self.root / 'rpc.jsonl').exists())
        with patch.dict(os.environ, {'PATH': str(self.root) + os.pathsep + os.environ['PATH']}):
            bare = dataclasses.replace(self.config, codex={**self.config.codex, 'executable': self.exe.name})
            self.assertTrue(doctor(bare)['ready'])

    def test_handshake_failure_and_unauthenticated(self):
        (self.root / 'doctor-behavior').write_text('handshake-fail')
        result = doctor(self.config)
        self.assertFalse(result['ready']); self.assertFalse(self.checks(result)['protocol']['ok'])
        (self.root / 'doctor-behavior').write_text('unauthenticated')
        result = doctor(self.config)
        self.assertFalse(result['ready']); self.assertFalse(self.checks(result)['authentication']['ok'])
        self.assertNotIn('SENSITIVE', json.dumps(result))

    def test_api_provider_does_not_require_chatgpt_account(self):
        (self.root / 'doctor-behavior').write_text('api-provider')
        result = doctor(self.config)
        self.assertTrue(result['ready'], result)

    def test_unreadable_skill_invalid_paths_and_foreign_data(self):
        self.skill.unlink()
        self.assertFalse(self.checks(doctor(self.config))['skill']['ok'])
        invalid = dataclasses.replace(self.config, web_root=self.root / 'missing')
        self.assertFalse(self.checks(doctor(invalid))['environment']['ok'])
        self.config.data_dir.mkdir()
        (self.config.data_dir / 'meta.json').write_text(json.dumps({'schemaVersion': 1, 'projectId': 'someone-else'}))
        before = (self.config.data_dir / 'meta.json').read_bytes()
        self.assertFalse(self.checks(doctor(self.config))['reviewData']['ok'])
        self.assertEqual((self.config.data_dir / 'meta.json').read_bytes(), before)
        self.assertFalse((self.config.data_dir / 'comments.json').exists())

    def test_disabled_and_shared_never_claim_execution_capability(self):
        disabled = dataclasses.replace(self.config, codex={**self.config.codex, 'enabled': False})
        result = doctor(disabled)
        self.assertFalse(result['capabilities']['codex'])
        self.assertFalse((self.root / 'rpc.jsonl').exists())
        shared = dataclasses.replace(self.config, server={**self.config.server, 'publicOrigins': ['https://review.example'], 'basePath': '/team'})
        result = doctor(shared)
        self.assertFalse(result['capabilities']['codex']); self.assertFalse(result['ready'])
        self.assertFalse((self.root / 'rpc.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
