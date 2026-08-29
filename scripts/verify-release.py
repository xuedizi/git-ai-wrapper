#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import json
import re
import stat
import sys
import tarfile
import zlib
from pathlib import Path
from typing import Any


EXPECTED = {
    "git-ai-linux-amd64": ("git-ai-linux-amd64.tar.gz", "git-ai"),
    "git-ai-linux-arm64": ("git-ai-linux-arm64.tar.gz", "git-ai"),
    "git-ai-darwin-amd64": ("git-ai-darwin-amd64.tar.gz", "git-ai"),
    "git-ai-darwin-arm64": ("git-ai-darwin-arm64.tar.gz", "git-ai"),
    "git-ai-windows-amd64": ("git-ai-windows-amd64.tar.gz", "git-ai.exe"),
    "git-ai-windows-arm64": ("git-ai-windows-arm64.tar.gz", "git-ai.exe"),
}
EXPECTED_ARCHIVES = {archive for archive, _ in EXPECTED.values()}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class VerificationError(Exception):
    pass


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def verify_archives(downloads: Path) -> None:
    if not downloads.is_dir():
        raise VerificationError(f"downloads directory not found: {downloads}")

    archives_by_name: dict[str, list[Path]] = {}
    for archive in downloads.rglob("*.tar.gz"):
        archives_by_name.setdefault(archive.name, []).append(archive)
    duplicates = {
        name: paths for name, paths in archives_by_name.items() if len(paths) > 1
    }
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise VerificationError(f"duplicate archive basename: {names}")

    actual_directories = {entry.name for entry in downloads.iterdir()}
    expected_directories = set(EXPECTED)
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        extra = sorted(actual_directories - expected_directories)
        raise VerificationError(
            "top-level artifact directories differ: "
            f"missing={missing}, extra={extra}"
        )

    expected_archive_paths = {
        f"{directory_name}/{archive_name}"
        for directory_name, (archive_name, _) in EXPECTED.items()
    }
    actual_archive_paths = {
        archive.relative_to(downloads).as_posix()
        for paths in archives_by_name.values()
        for archive in paths
    }
    unexpected_archive_paths = actual_archive_paths - expected_archive_paths
    if unexpected_archive_paths:
        paths = ", ".join(sorted(unexpected_archive_paths))
        raise VerificationError(f"unexpected archive path: {paths}")

    for directory_name, (archive_name, executable_name) in EXPECTED.items():
        artifact_dir = downloads / directory_name
        try:
            artifact_dir_mode = artifact_dir.lstat().st_mode
        except OSError as error:
            raise VerificationError(
                f"unable to inspect artifact path {artifact_dir}: {error}"
            ) from error
        if not stat.S_ISDIR(artifact_dir_mode):
            raise VerificationError(
                f"artifact path must be a real directory: {artifact_dir}"
            )
        archives = sorted(
            entry for entry in artifact_dir.iterdir() if entry.name.endswith(".tar.gz")
        )
        if len(archives) != 1 or archives[0].name != archive_name:
            found = [archive.name for archive in archives]
            raise VerificationError(
                f"{directory_name} must contain exactly {archive_name}; found={found}"
            )

        try:
            archive_mode = archives[0].lstat().st_mode
        except OSError as error:
            raise VerificationError(
                f"unable to inspect archive path {archives[0]}: {error}"
            ) from error
        if not stat.S_ISREG(archive_mode):
            raise VerificationError(
                f"archive path must be a regular file: {archives[0]}"
            )

        try:
            with gzip.open(archives[0], "rb") as compressed:
                for _ in iter(lambda: compressed.read(1024 * 1024), b""):
                    pass
        except (EOFError, OSError, zlib.error) as error:
            raise VerificationError(
                f"invalid gzip stream {archive_name}: {error}"
            ) from error

        try:
            with tarfile.open(archives[0], "r:gz") as archive:
                members = archive.getmembers()
        except (EOFError, OSError, tarfile.TarError, zlib.error) as error:
            raise VerificationError(f"invalid archive {archive_name}: {error}") from error
        if (
            len(members) != 1
            or members[0].name != executable_name
            or not members[0].isfile()
            or members[0].size <= 0
        ):
            found = [(member.name, member.size) for member in members]
            raise VerificationError(
                f"{archive_name} expected only '{executable_name}' with positive size; "
                f"found={found}"
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(
    manifest_path: Path,
    release_dir: Path,
    expected_version: str,
    expected_upstream: str,
) -> None:
    try:
        with manifest_path.open(encoding="utf-8") as stream:
            manifest = json.load(stream, object_pairs_hook=no_duplicates)
    except VerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid manifest JSON: {error}") from error

    if not isinstance(manifest, dict):
        raise VerificationError("manifest root must be an object")
    if manifest.get("version") != expected_version:
        raise VerificationError(
            f"version mismatch: expected {expected_version!r}, "
            f"got {manifest.get('version')!r}"
        )
    if manifest.get("upstream_git_ai") != expected_upstream:
        raise VerificationError(
            f"upstream mismatch: expected {expected_upstream!r}, "
            f"got {manifest.get('upstream_git_ai')!r}"
        )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise VerificationError("manifest artifacts must be an object")
    actual_artifacts = set(artifacts)
    if actual_artifacts != EXPECTED_ARCHIVES:
        missing = sorted(EXPECTED_ARCHIVES - actual_artifacts)
        extra = sorted(actual_artifacts - EXPECTED_ARCHIVES)
        raise VerificationError(
            f"artifact keys differ: missing={missing}, extra={extra}"
        )

    if not release_dir.is_dir():
        raise VerificationError(f"release directory not found: {release_dir}")
    for artifact_name in sorted(EXPECTED_ARCHIVES):
        metadata = artifacts[artifact_name]
        if not isinstance(metadata, dict):
            raise VerificationError(f"metadata for {artifact_name} must be an object")
        expected_sha = metadata.get("sha256")
        if not isinstance(expected_sha, str) or SHA256_RE.fullmatch(expected_sha) is None:
            raise VerificationError(f"invalid sha256 for {artifact_name}")
        expected_size = metadata.get("size")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size <= 0
        ):
            raise VerificationError(f"invalid size for {artifact_name}")

        artifact_path = release_dir / artifact_name
        try:
            artifact_stat = artifact_path.lstat()
        except OSError as error:
            raise VerificationError(
                f"unable to inspect release artifact {artifact_path}: {error}"
            ) from error
        if not stat.S_ISREG(artifact_stat.st_mode):
            raise VerificationError(
                f"release artifact must be a regular file: {artifact_path}"
            )
        actual_size = artifact_stat.st_size
        if actual_size != expected_size:
            raise VerificationError(
                f"size mismatch for {artifact_name}: "
                f"expected {expected_size}, got {actual_size}"
            )
        try:
            actual_sha = sha256(artifact_path)
        except OSError as error:
            raise VerificationError(
                f"unable to read release artifact {artifact_path}: {error}"
            ) from error
        if actual_sha != expected_sha:
            raise VerificationError(
                f"sha256 mismatch for {artifact_name}: "
                f"expected {expected_sha}, got {actual_sha}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify git-ai-wrapper release artifacts")
    parser.add_argument("--archives-only", action="store_true")
    parser.add_argument("--downloads", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--upstream")
    args = parser.parse_args()

    if args.archives_only:
        if args.downloads is None:
            parser.error("--archives-only requires --downloads")
        if any(
            value is not None
            for value in (args.manifest, args.release_dir, args.version, args.upstream)
        ):
            parser.error("--archives-only cannot be combined with manifest arguments")
    else:
        missing = [
            option
            for option, value in (
                ("--manifest", args.manifest),
                ("--release-dir", args.release_dir),
                ("--version", args.version),
                ("--upstream", args.upstream),
            )
            if value is None
        ]
        if missing:
            parser.error(f"manifest verification requires {', '.join(missing)}")
        if args.downloads is not None:
            parser.error("--downloads requires --archives-only")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.archives_only:
            verify_archives(args.downloads)
            print("OK: verified six release archive artifacts")
        else:
            verify_manifest(
                args.manifest,
                args.release_dir,
                args.version,
                args.upstream,
            )
            print("OK: verified release manifest and staged artifacts")
    except VerificationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: filesystem failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
