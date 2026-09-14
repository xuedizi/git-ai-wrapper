import importlib.util
import json
import io
import os
import subprocess
import sys
import tarfile
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("run-managed-client-validation.py")


class BundleVerificationTest(unittest.TestCase):
    def load_runner(self):
        spec = importlib.util.spec_from_file_location("managed_client_validation", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_digest_mismatch_does_not_extract_bundle(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("tcli", b"private fixture")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"source_digest": "a" * 64, "bundles": {"linux-amd64": {"sha256": "b" * 64}}}))
            target = root / "extracted"
            with self.assertRaisesRegex(ValueError, "SHA256"):
                runner.verify_and_extract_bundle(archive, manifest, "linux/amd64", target)
            self.assertFalse(target.exists())

    def test_verified_zip_rejects_traversal_before_any_extraction(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("tcli", b"private fixture")
                bundle.writestr("../escaped", b"escape")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"source_digest": "a" * 64, "bundles": {"linux-amd64": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}}))
            target = root / "extracted"
            with self.assertRaisesRegex(ValueError, "unsafe"):
                runner.verify_and_extract_bundle(archive, manifest, "linux/amd64", target)
            self.assertFalse(target.exists())
            self.assertFalse((root / "escaped").exists())

    def test_verified_bundle_extracts_fixture_bytes(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("scripts/fixture.txt", b"private fixture")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"source_digest": "a" * 64, "bundles": {"linux-amd64": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}}))
            target = root / "extracted"
            self.assertEqual(runner.verify_and_extract_bundle(archive, manifest, "linux/amd64", target), "a" * 64)
            self.assertEqual((target / "scripts/fixture.txt").read_bytes(), b"private fixture")

    def test_empty_test_selection_cannot_report_success(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "no passing tests"):
                runner.run_suite("managed client tests", [sys.executable, "-c", "print('PASS')"], root, os.environ.copy(), root / "tests.log")

    @unittest.skipIf(os.name == "nt", "Unix executable fixture tests runner plumbing")
    def test_runner_isolates_home_and_does_not_forward_ci_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            fixture = b"""#!/usr/bin/env python3
import os, pathlib
assert not any(os.environ.get(key) for key in ('TCLI_VALIDATION_KEY', 'GH_TOKEN', 'GITHUB_TOKEN'))
for key in ('TCLI_MANAGED_TCLI_TEST_BINARY', 'TCLI_MANAGED_APM_TEST_BINARY', 'TCLI_MANAGED_GA_TEST_BINARY'):
    assert pathlib.Path(os.environ[key]).is_file()
assert pathlib.Path(os.environ['HOME']).resolve().is_relative_to(pathlib.Path(os.environ['RUNNER_TEMP']).resolve())
print('--- PASS: TestManagedRunnerPlumbing (0.00s)')
print('PASS')
"""
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("selfupdate.test", fixture)
                bundle.writestr("tcli", b"synthetic tcli")
                bundle.writestr("apm", b"synthetic apm")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"source_digest": "a" * 64, "bundles": {"linux-amd64": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}}))
            ga_dir = root / "download"
            ga_dir.mkdir()
            with tarfile.open(ga_dir / "git-ai-linux-amd64.tar.gz", "w:gz") as ga:
                member = tarfile.TarInfo("git-ai")
                member.size = 2
                ga.addfile(member, io.BytesIO(b"GA"))
            environment = os.environ.copy()
            environment.update(RUNNER_TEMP=str(root), TCLI_VALIDATION_KEY="synthetic-secret", GH_TOKEN="synthetic-token", GITHUB_TOKEN="synthetic-token")
            result = subprocess.run([sys.executable, str(SCRIPT), "--platform", "linux/amd64", "--ga-dir", str(ga_dir), "--bundle", str(archive), "--manifest", str(manifest)], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("managed client tests PASS tests=1", result.stdout)
            self.assertFalse(list(root.glob("managed-client-*")))


if __name__ == "__main__":
    unittest.main()
