# git-ai-wrapper

`git-ai-wrapper` builds TAC's minimally patched `git-ai-project/git-ai`
sidecar executables.

Release tags use:

```text
v<upstream-git-ai-version>-tac.v<wrapper-version>
```

For example, `v1.7.0-tac.v0.1.0` is built from
`git-ai-project/git-ai@v1.7.0` as wrapper release `v0.1.0`.

## Downstream scope

The wrapper intentionally carries one active downstream patch:

- `codebuddy-preset.patch` adds first-class CodeBuddy support. CodeBuddy's
  hook protocol is compatible with Claude Code, but its transcript stores the
  model in a structured `providerData.model` field (rather than Claude's
  `message.model`). The patch adds a `codebuddy` preset, a `CodebuddyJsonl`
  stream format with a dedicated model extractor, a `Codebuddy` tool classifier,
  and a `CodebuddyInstaller` that writes hooks into `~/.codebuddy/settings.json`.
  Subagent-parent detection is intentionally deferred to a later version.

General git-ai attribution, blame, stats, and Git-Notes behavior remains
upstream `git-ai` 1.7.0. The narrow downstream patch owns only CodeBuddy preset
and hook-installer support. TCLI owns orchestration and invokes:

```bash
git ai install-hooks
git ai stats --json
```

## Layout

```text
patches/GIT_AI_VERSION        upstream git-ai-project/git-ai tag
patches/codebuddy-preset.patch
disabled-patches/             inactive source archives (none currently)
scripts/build-git-ai.sh       clone, patch, and cargo-build git-ai / git-ai.exe
scripts/test-patched-git-ai.sh
scripts/package-release.sh
scripts/generate-manifest.sh
scripts/verify-executable-arch.py
scripts/verify-release.py
.github/workflows/release.yml
```

## Local smoke

```bash
bash scripts/build-git-ai.sh --out dist/raw
bash scripts/package-release.sh \
  --version v1.7.0-tac.v0.1.0 \
  --platform "$(go env GOOS)/$(go env GOARCH)" \
  --input dist/raw/git-ai \
  --out dist/release
scripts/generate-manifest.sh \
  --version v1.7.0-tac.v0.1.0 \
  --upstream "$(cat patches/GIT_AI_VERSION)" \
  --dir dist/release \
  --out dist/release/git-ai-manifest.json
```

## Release platforms

Each release contains one native executable archive for every supported
platform:

| Platform | GitHub-hosted runner | Executable |
| --- | --- | --- |
| `linux/amd64` | `ubuntu-24.04` | `git-ai` |
| `linux/arm64` | `ubuntu-24.04-arm` | `git-ai` |
| `darwin/amd64` | `macos-15-intel` | `git-ai` |
| `darwin/arm64` | `macos-15` | `git-ai` |
| `windows/amd64` | `windows-2025` | `git-ai.exe` |
| `windows/arm64` | `windows-11-arm` | `git-ai.exe` |

The `patch-tests` job applies the active patch to a clean pinned checkout and
runs `cargo test` before any native release build starts.

Remove the CodeBuddy patch only after a released upstream tag contains both the
source behavior and equivalent regression coverage. Rollback must restore the
complete previously verified wrapper commit/tag, including its matching
`GIT_AI_VERSION`, patch, tests, and documentation; changing only the version pin
can leave an incompatible patch set.
