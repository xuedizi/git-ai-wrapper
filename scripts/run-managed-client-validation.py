#!/usr/bin/env python3
"""Validate an encrypted client bundle against a downloaded native GA release."""

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PLATFORMS = {f"{system}/{arch}" for system in ("linux", "darwin", "windows") for arch in ("amd64", "arm64")}
SHA256 = re.compile(r"[0-9a-fA-F]{64}")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def verify_and_extract_bundle(bundle, manifest_path, platform, destination):
    manifest = json.loads(manifest_path.read_text(), object_pairs_hook=unique_keys)
    source_digest = manifest.get("source_digest", "")
    expected = manifest.get("bundles", {}).get(platform.replace("/", "-"), {}).get("sha256", "")
    if not isinstance(source_digest, str) or not SHA256.fullmatch(source_digest):
        raise ValueError("invalid source digest in bundle manifest")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise ValueError("missing or invalid bundle SHA256")
    digest = hashlib.sha256()
    with bundle.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if not hmac.compare_digest(digest.hexdigest(), expected.lower()):
        raise ValueError("decrypted bundle SHA256 mismatch")
    # Validate every entry before creating any extracted file. In particular,
    # neither POSIX nor Windows path syntax can escape the private directory.
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        seen = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            key = str(path).casefold()
            if (not entry.filename or "\\" in entry.filename or ":" in entry.filename
                    or path.is_absolute() or ".." in path.parts or not path.parts
                    or key in seen or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)))):
                raise ValueError("unsafe bundle ZIP entry")
            seen.add(key)
        destination.mkdir(mode=0o700)
        for entry in entries:
            target = destination.joinpath(*PurePosixPath(entry.filename).parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o700 if (entry.external_attr >> 16) & 0o111 else 0o600)
    return source_digest.lower()


def extract_ga(ga_dir, platform, destination):
    filename = "git-ai.exe" if platform.startswith("windows/") else "git-ai"
    expected = "git-ai-" + platform.replace("/", "-") + ".tar.gz"
    archives = list(ga_dir.rglob("*.tar.gz"))
    if len(archives) != 1 or archives[0].name != expected:
        raise ValueError("download must contain exactly the expected GA release archive")
    with tarfile.open(archives[0], "r:gz") as archive:
        entries = archive.getmembers()
        if len(entries) != 1 or entries[0].name != filename or not entries[0].isfile():
            raise ValueError("GA archive must contain one regular root executable")
        destination.mkdir(mode=0o700)
        target = destination / filename
        with archive.extractfile(entries[0]) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o700)
        return target.resolve()


def bounded_diagnostics(log_path):
    with log_path.open("rb") as source:
        source.seek(max(0, log_path.stat().st_size - 65536))
        lines = source.read().decode("utf-8", errors="replace").splitlines()
    selected = set()
    pattern = re.compile(r"--- FAIL:|_test\.go:\d+|error|failed|panic:|exception", re.IGNORECASE)
    for index, line in enumerate(lines):
        if pattern.search(line):
            selected.update(range(max(0, index - 1), min(len(lines), index + 3)))
    if not selected:
        selected.update(range(max(0, len(lines) - 8), len(lines)))
    return "\n".join(lines[index] for index in sorted(selected))[-4096:]


def run_suite(label, command, cwd, environment, log_path, require_tests=True):
    try:
        with log_path.open("wb") as output:
            subprocess.run(command, cwd=cwd, env=environment, stdout=output,
                           stderr=subprocess.STDOUT, check=True, timeout=1800)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as failure:
        print(f"{label} FAILED ({type(failure).__name__})", file=sys.stderr)
        print(bounded_diagnostics(log_path), file=sys.stderr)
        raise RuntimeError(f"{label} failed; decrypted files and complete logs are not uploaded") from None
    text = log_path.read_text(errors="replace")
    count = len(re.findall(r"^--- PASS:", text, re.MULTILINE))
    if require_tests and not count:
        raise RuntimeError(f"{label} selected no passing tests")
    print(f"{label} PASS tests={count}" if count else f"{label} PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--ga-dir", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / ".ci/tcli-validation/manifest.json")
    args = parser.parse_args()
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    with tempfile.TemporaryDirectory(prefix="managed-client-", dir=runner_temp) as temporary:
        root = Path(temporary)
        clients = root / "clients"
        source_digest = verify_and_extract_bundle(args.bundle.resolve(), args.manifest.resolve(), args.platform, clients)
        ga = extract_ga(args.ga_dir.resolve(), args.platform, root / "ga")
        suffix = ".exe" if args.platform.startswith("windows/") else ""
        binaries = {name: clients / (name + suffix) for name in ("selfupdate.test", "tcli", "apm")}
        for path in binaries.values():
            if not path.is_file():
                raise ValueError("bundle is missing a required native test/client executable")
            path.chmod(0o700)
        home = root / "home"
        home.mkdir(mode=0o700)
        environment = os.environ.copy()
        for name in ("TCLI_VALIDATION_KEY", "GH_TOKEN", "GITHUB_TOKEN"):
            environment.pop(name, None)
        environment.update({"HOME": str(home), "USERPROFILE": str(home),
                            "GIT_AI_DAEMON_HOME": str(home),
                            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
                            "XDG_CONFIG_HOME": str(home / ".config"),
                            "TCLI_MANAGED_TCLI_TEST_BINARY": str(binaries["tcli"].resolve()),
                            "TCLI_MANAGED_APM_TEST_BINARY": str(binaries["apm"].resolve()),
                            "TCLI_MANAGED_GA_TEST_BINARY": str(ga)})
        print(f"CLIENT_VALIDATION platform={args.platform} source_digest={source_digest}")
        run_suite("managed client tests", [str(binaries["selfupdate.test"]), "-test.v",
                  "-test.timeout=25m", "-test.run=^(TestManaged|TestWindowsComponentRename|TestWatchManagedProcess)"],
                  clients, environment, root / "client-tests.log")
        installer_test = clients / "scripts/install_private_sidecar_test.ps1"
        if suffix and installer_test.is_file():
            run_suite("private sidecar installer", ["powershell.exe", "-NoProfile", "-NonInteractive",
                      "-ExecutionPolicy", "Bypass", "-File", str(installer_test)],
                      clients, environment, root / "installer-tests.log", require_tests=False)
        print(f"CLIENT_VALIDATION PASS platform={args.platform}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile, tarfile.TarError) as error:
        print(f"managed client validation failed: {error}", file=sys.stderr)
        sys.exit(1)
