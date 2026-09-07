import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('prepare-enterprise-config.py')

class PublisherConfigTests(unittest.TestCase):
    def run_prepare(self, config=None, version=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ['python3', str(SCRIPT), '--out', str(root / 'embedded.rs')]
            if config is not None:
                path = root / 'publisher.json'
                path.write_text(json.dumps(config))
                args += ['--config', str(path)]
            if version:
                args += ['--version', version]
            result = subprocess.run(args, capture_output=True, text=True)
            output = (root / 'embedded.rs').read_text() if (root / 'embedded.rs').exists() else ''
            return result, output

    def fixture(self):
        return {'enabled': True, 'organization_id': 'org',
                'identity_secret': 'stable-fixture-secret-at-least-32-bytes',
                'destinations': [{'id':'company', 'endpoint':'https://company.test/upload',
                                  'token':'fixture-secret', 'ack':{'mode':'unconfirmed'},
                                  'event_types':['checkpoint','commit']}]}

    def test_development_has_no_upload_configuration(self):
        result, output = self.run_prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('development', output)
        self.assertIn('enabled', output)
        self.assertNotIn('fixture-secret', output)

    def test_formal_config_embedded_with_exact_wrapper_version(self):
        result, output = self.run_prepare(self.fixture(), 'v1.7.0-tac.v0.2.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fixture-secret', output)
        self.assertIn('v1.7.0-tac.v0.2.0', output)
        self.assertNotIn('fixture-secret', result.stdout + result.stderr)

    def test_enabled_config_requires_release_version(self):
        result, _ = self.run_prepare(self.fixture())
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_config_never_creates_artifact_or_prints_token(self):
        for change in [{'organization_id':''}, {'identity_secret':'short'}, {'users':{'x':'y'}}]:
            cfg = self.fixture() | change
            result, output = self.run_prepare(cfg, 'v1.7.0-tac.v0.2.0')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output, '')
            self.assertNotIn('fixture-secret', result.stdout + result.stderr)
        for change in [{'token':''}, {'token':'secret\nline'}, {'endpoint':'http://company.test/upload'},
                       {'ack':{'mode':'guess'}}, {'event_types':['bogus']}]:
            cfg = self.fixture()
            cfg['destinations'][0].update(change)
            result, output = self.run_prepare(cfg, 'v1.7.0-tac.v0.2.0')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output, '')

if __name__ == '__main__':
    unittest.main()
