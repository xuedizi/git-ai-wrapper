# Targeted hook installation

TCLI forwards arguments unchanged to the bundled git-ai sidecar. This patch adds
only `--target` to native `install-hooks` and its `install` alias; it introduces
no commands, discovery flags, tool IDs, or new installer capabilities.

```sh
tcli ga install-hooks --target codex --dry-run
tcli ga install-hooks --target=codex,codebuddy --dry-run=false
tcli ga install-hooks --target codex --target cursor --dry-run
```

## Parameter contract

- Omit `--target` to retain native installation behavior and dry-run defaults.
- Accept `--target VALUE` and `--target=VALUE`, comma-separated and repeated.
  Values are trimmed, validated as lowercase installer IDs, deduplicated, and
  executed in existing installer order. Selection is not persisted.
- Reject missing values, empty entries (including trailing commas), unknown IDs,
  and IDs unavailable on the current platform before installation writes.
  Errors list registered IDs on that platform. No `all`, wildcards, or aliases.
- Supported IDs come from the patched upstream registry: `amp`, `claude-code`,
  `cline`, `codebuddy`, `codex`, `cursor`, `droid`, `firebender`, `gemini`,
  `github-copilot`, `jetbrains`, `opencode`, `pi`, `vscode`, `windsurf`, and
  `visual-studio` on Windows. Native availability checks remain in effect.
- `jetbrains` selects the existing IDE-family installer. There is no new
  `android-studio` target.
- Native options retain their semantics. In particular, Visual Studio still
  requires `--visual-studio-extension`; that flag cannot widen an explicit
  target set. Unknown unrelated options retain native parsing behavior.

## Scope

Only selected installers run: detection, hooks, extensions/settings, and their
restart notices. Unselected tool configuration is not installed, updated, or
removed. Existing unselected integrations are not disabled.

Targeted installation skips all Skills installation and cleanup. Combining
`--target` with native `--skills` is rejected before writes because Skills use
shared content and links. Without `--target`, native Skills behavior is unchanged.

Shared git-ai runtime setup remains native. Explicit `--env` / `--wsl` and other
native options keep their existing global scope; `--target` does not promise
isolation of shared services or select tools within an explicit WSL installation.
Tool-not-found and installer failure handling retain native status/exit behavior;
a missing selected tool is explicitly reported and never triggers all-tool fallback.

Dry-run invokes the same selection without installation writes. Its suggested
apply command preserves the deduplicated target set. Repeated installs retain
native idempotency. `uninstall-hooks` and `uninstall` reject `--target` before
uninstalling anything; targeted uninstall is not added.

## Delivery and verification

The feature is shipped as `patches/install-hooks-target.patch` against pinned
upstream `v1.7.0` after the existing patches, not as changes to a newer local
upstream checkout. Rebuild and distribute the sidecar before using this flag:
older binaries may silently ignore it and run default installation.

The release patch test script includes native unit tests and `install_hooks_target`
integration regressions covering selected hooks, untouched other-tool files and
Skills, idempotency, dry-run target preservation, and invalid/uninstall rejection.
TCLI has a regression ensuring target arguments are forwarded unchanged.
