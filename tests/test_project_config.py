import json
from pathlib import Path
import tempfile
import unittest

from project_config import ConfigError, ProjectConfig, load_project_config


def configuration():
    return {
        'configVersion': 1, 'projectId': 'synthetic-project-1', 'toolVersion': '0.1.0-dev',
        'webRoot': 'site', 'dataDir': 'reviews', 'jobsDir': '.review/jobs',
        'server': {'host': '127.0.0.1', 'port': 8799, 'basePath': '', 'publicOrigins': []},
        'pageIdentity': {}, 'browserStorage': {},
        'guidance': {'requiredFiles': ['README.md'], 'sourceRoots': ['src'],
                     'buildCommands': [['python3', 'build.py']], 'checkCommands': []},
        'codex': {'enabled': False, 'executable': 'codex',
                  'approvalPolicy': 'never', 'sandbox': 'danger-full-access'},
    }


class ProjectConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / '外部 project'
        (self.project / 'site').mkdir(parents=True)
        self.raw = configuration()
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        (self.project / 'review.config.json').write_text(json.dumps(self.raw), encoding='utf-8')

    def test_external_project_paths(self):
        config = load_project_config(self.project)
        self.assertIsInstance(config, ProjectConfig)
        for key, expected in [('project_root', self.project), ('web_root', self.project / 'site'),
                              ('data_dir', self.project / 'reviews'), ('jobs_dir', self.project / '.review/jobs')]:
            self.assertEqual(getattr(config, key), expected.resolve())
        self.assertNotIn('model', config.codex)
        self.assertEqual(config.server['host'], '127.0.0.1')

    def test_host_defaults_and_explicit_model(self):
        del self.raw['server']['host']
        self.raw['codex']['model'] = 'explicit-model'
        self.write()
        config = load_project_config(self.project)
        self.assertEqual(config.server['host'], '127.0.0.1')
        self.assertEqual(config.codex['model'], 'explicit-model')

    def test_unicode_and_symlink_paths(self):
        alias = Path(self.temp.name) / '项目 symlink'
        alias.symlink_to(self.project, target_is_directory=True)
        self.raw['webRoot'] = '页面 空格'
        (self.project / self.raw['webRoot']).mkdir()
        self.write()
        self.assertEqual(load_project_config(alias), load_project_config(self.project))
        self.assertEqual(load_project_config(alias).web_root, (self.project / '页面 空格').resolve())

    def test_unknown_config_version(self):
        self.raw['configVersion'] = 999
        self.write()
        with self.assertRaises(ConfigError) as raised:
            load_project_config(self.project)
        self.assertEqual(raised.exception.exit_code, 2)

    def test_shared_requires_https_origin_base_path_and_no_codex(self):
        for changes in [dict(host='0.0.0.0'), dict(publicOrigins=['http://example.test'], basePath='/review'),
                        dict(publicOrigins=['https://example.test']), dict(basePath='/review')]:
            with self.subTest(changes=changes):
                self.raw = configuration()
                self.raw['server'].update(changes)
                self.write()
                with self.assertRaises(ConfigError):
                    load_project_config(self.project)
        self.raw = configuration()
        self.raw['server'].update(publicOrigins=['https://example.test'], basePath='/review')
        self.write()
        self.assertFalse(load_project_config(self.project).codex['enabled'])
        self.raw['codex']['enabled'] = True
        self.write()
        with self.assertRaises(ConfigError):
            load_project_config(self.project)

    def test_guidance_commands_are_argv_arrays(self):
        for invalid in ['python3 build.py', ["python3 build.py"], [['python3', 4]], [[]]]:
            self.raw['guidance']['buildCommands'] = invalid
            self.write()
            with self.subTest(invalid=invalid), self.assertRaises(ConfigError):
                load_project_config(self.project)

    def test_invalid_types_ports_and_permissions(self):
        for section, key, value in [('server', 'port', True), ('server', 'port', 0),
                                    ('server', 'port', 65536), ('server', 'host', 'localhost'),
                                    ('codex', 'enabled', 'yes'), ('codex', 'approvalPolicy', 'on-request'),
                                    ('codex', 'sandbox', 'workspace-write')]:
            self.raw = configuration()
            self.raw[section][key] = value
            self.write()
            with self.subTest(section=section, key=key, value=value), self.assertRaises(ConfigError):
                load_project_config(self.project)

    def test_missing_config_or_web_root_is_unavailable(self):
        self.raw['webRoot'] = 'missing'
        self.write()
        with self.assertRaises(ConfigError):
            load_project_config(self.project)
        (self.project / 'review.config.json').unlink()
        with self.assertRaises(ConfigError):
            load_project_config(self.project)


if __name__ == '__main__':
    unittest.main()
