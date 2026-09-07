import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FixedBuildConfigTests(unittest.TestCase):
    def test_build_uses_repository_config_from_other_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / 'wrapper'
            (repo / 'scripts').mkdir(parents=True)
            (repo / 'config').mkdir()
            (repo / 'patches').mkdir()
            for name in ['build-git-ai.sh', 'prepare-enterprise-config.py']:
                shutil.copy(ROOT / 'scripts' / name, repo / 'scripts' / name)
            (repo / 'patches/GIT_AI_VERSION').write_text('v1.7.0\n')
            fixture = {'enabled': True, 'organization_id': 'fixture-org',
                       'identity_secret': 'fixture-stable-identity-secret-32-bytes',
                       'destinations': [{'id': 'company', 'endpoint': 'https://company.test/upload',
                            'token': 'fixture-fixed-token', 'ack': {'mode':'json','pointer':'/success','equals':True},
                            'event_types': ['checkpoint','commit']}]}
            (repo / 'config/enterprise-metrics.release.json').write_text(json.dumps(fixture))
            # Stub only upstream clone and Cargo compilation; execute real config generator and build shell.
            bins = base / 'bin'
            bins.mkdir()
            (bins / 'git').write_text('#!/bin/bash\nif [ "$1" = clone ]; then\n  for arg; do last="$arg"; done\n  mkdir -p "$last/src/enterprise_metrics"\nelif [ "$1" = rev-parse ]; then\n  echo abc123\nfi\n')
            (bins / 'cargo').write_text('#!/bin/bash\nmkdir -p target/release\ncp src/enterprise_metrics/embedded.rs target/release/git-ai\n')
            for item in bins.iterdir():
                item.chmod(0o755)
            env = dict(os.environ, PATH=str(bins)+os.pathsep+os.environ['PATH'],
                       TAC_GIT_AI_ENTERPRISE_CONFIG=str(base / 'must-not-read.json'))
            result = subprocess.run(['bash', str(repo / 'scripts/build-git-ai.sh'), '--out', str(base / 'out'),
                                     '--version', 'v1.7.0-tac.v0.2.0'], cwd=base, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            embedded = (base / 'out/git-ai').read_text()
            self.assertIn('fixture-fixed-token', embedded)
            self.assertIn('v1.7.0-tac.v0.2.0', embedded)
            self.assertNotIn('fixture-fixed-token', result.stdout+result.stderr)

if __name__ == '__main__':
    unittest.main()
