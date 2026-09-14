# git-ai-wrapper

`git-ai-wrapper` builds TAC's minimally patched `git-ai-project/git-ai`
sidecar executables.

Release tags use:

```text
v<upstream-git-ai-version>-tac.v<wrapper-version>
```

For example, `v1.7.0-tac.v0.2.0` is built from
`git-ai-project/git-ai@v1.7.0` as wrapper release `v0.2.0`.

## Downstream scope

The wrapper intentionally carries four active downstream patches:

- `codebuddy-preset.patch` adds first-class CodeBuddy support. CodeBuddy's
  hook protocol is compatible with Claude Code, but its transcript stores the
  model in a structured `providerData.model` field (rather than Claude's
  `message.model`). The patch adds a `codebuddy` preset, a `CodebuddyJsonl`
  stream format with a dedicated model extractor, a `Codebuddy` tool classifier,
  and a `CodebuddyInstaller` that writes hooks into `~/.codebuddy/settings.json`.
  Subagent-parent detection is intentionally deferred to a later version.
  Invalid event working directories fall back to the hook process directory,
  preserving valid CLI event directories; see [CLI/IDE cwd compatibility](docs/codebuddy-cwd.md).

- `enterprise-metrics.patch` adds opt-in checkpoint/commit enterprise telemetry with publisher-embedded configuration and automatic Git email/remote identity:
  transactional inbox/outbox, allowlisted DTOs, independently acknowledged
  destinations, retry/backoff, and daemon control commands. HTTPS uses Native TLS
  and the platform trust store, with a local HTTPS panic regression. See
  [enterprise telemetry setup](docs/enterprise-metrics.md).

- `tcli-auto-update.patch` lets a TCLI-bundled daemon periodically invoke its paired
  `tcli self-update --auto`; standalone git-ai keeps its upstream update behavior.
- `install-hooks-target.patch` adds `--target` to native hook installation. See
  [targeted installation](docs/install-hooks-target.md).

General git-ai attribution, blame, stats, and Git-Notes behavior remains
upstream `git-ai` 1.7.0. CodeBuddy integration, enterprise delivery, and targeted hook installation are maintained as separate patches. TCLI owns orchestration and invokes:

```bash
git ai install-hooks
git ai stats --json
```

## Layout

```text
patches/GIT_AI_VERSION        upstream git-ai-project/git-ai tag
patches/codebuddy-preset.patch
patches/enterprise-metrics.patch
patches/install-hooks-target.patch
patches/tcli-auto-update.patch
config/enterprise-metrics.release.json  fixed publisher settings (enabled by default)
disabled-patches/             inactive source archives (none currently)
scripts/build-git-ai.sh       clone, patch, and cargo-build git-ai / git-ai.exe
scripts/test-patched-git-ai.sh
scripts/prepare-enterprise-config.py
scripts/package-release.sh
scripts/generate-manifest.sh
scripts/verify-executable-arch.py
scripts/verify-release.py
.github/workflows/release.yml
```

## Local smoke

```bash
bash scripts/build-git-ai.sh --out dist/raw --version v1.7.0-tac.v0.2.0
bash scripts/package-release.sh \
  --version v1.7.0-tac.v0.2.0 \
  --platform "$(go env GOOS)/$(go env GOARCH)" \
  --input dist/raw/git-ai \
  --out dist/release
scripts/generate-manifest.sh \
  --version v1.7.0-tac.v0.2.0 \
  --upstream "$(cat patches/GIT_AI_VERSION)" \
  --dir dist/release \
  --out dist/release/git-ai-manifest.json
```

Builds always embed `config/enterprise-metrics.release.json` (enabled by default).
Maintain publisher fields there and pass the intended release tag with `--version`;
end users never edit telemetry configuration. No GitHub configuration secret is needed.

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

The `patch-tests` job applies all four active patches to a clean pinned checkout and
runs the library suite (including TCLI layout and timer tests), enterprise/installer
regressions, and CodeBuddy cwd tests before native release builds.

Remove the CodeBuddy patch only after a released upstream tag contains both the
source behavior and equivalent regression coverage. Rollback must restore the
complete previously verified wrapper commit/tag, including its matching
`GIT_AI_VERSION`, patch, tests, and documentation; changing only the version pin
can leave an incompatible patch set.
