# patches

Out-of-tree patches against upstream `git-ai-project/git-ai`, applied by
`git-ai-wrapper/scripts/build-git-ai.sh`. Only top-level `*.patch` files in this
directory are active build inputs.

- `GIT_AI_VERSION` pins the upstream tag.
- `codebuddy-preset.patch` adds first-class CodeBuddy and WorkBuddy support in one shared patch. CodeBuddy's hook
  protocol is compatible with Claude Code, but its JSONL transcript stores the
  model in a structured `providerData.model` field (unlike Claude's
  `message.model`). The patch adds:
  - `codebuddy` and `workbuddy` presets (`src/commands/checkpoint_agent/presets/codebuddy.rs`)
  - a `CodebuddyJsonl` stream format in both `StreamFormat` enums
  - a dedicated model extractor (`extract_model_from_codebuddy_jsonl_line`)
  - a `Codebuddy` tool classifier (reusing Claude's tool-name mapping)
  - a `CodebuddyInstaller` that writes `PreToolUse`/`PostToolUse` hooks into
    `~/.codebuddy/settings.json` or `~/.workbuddy/settings.json`, respectively
  - shared parsing/model extraction with separate tool and session identities
  - registered `workbuddy` hook target (`install-hooks --target workbuddy`)

General git-ai attribution, blame, stats, and Git-Notes behavior remains owned
by upstream git-ai 1.7.0. The narrow downstream patch owns CodeBuddy/WorkBuddy
preset and hook-installer support.

Delete the CodeBuddy patch only after an upstream release carries both its
source fix and regression coverage. To roll back, restore the complete prior
wrapper baseline commit/tag, including its matching patch and tests; do not
change only `GIT_AI_VERSION`.

Inactive diagnostic or recovery patches, if any, are documented in
`../disabled-patches/README.md` and are never applied from this directory.

- `enterprise-metrics.patch` adds independent checkpoint/commit enterprise
  delivery and management. Apply it after `codebuddy-preset.patch`. Its baseline
  is the exact `GIT_AI_VERSION` tag with the CodeBuddy patch applied.
  Includes the Native TLS/platform trust configuration and a loopback HTTPS
  regression preventing the missing-Rustls-provider panic.
  Publisher embedding, automatic repository identity and the unconfirmed service-contract gate are described in
  [enterprise telemetry](../docs/enterprise-metrics.md).

- `install-hooks-target.patch` adds only `--target` to native `install-hooks`
  (and its `install` alias). Apply after the existing patches. Targets use
  registered installer IDs; selection gates both hooks and extras, preserves
  all Skills, and survives dry-run apply suggestions. Targeted uninstall is
  explicitly rejected. Includes parser and isolated TestRepo regressions.
  See [parameter contract](../docs/install-hooks-target.md).

- `tcli-auto-update.patch` detects the TCLI `.tcli/git-ai[.exe]` layout and invokes
  the paired `tcli self-update --auto` after a randomized 60–300 second startup
  delay, then every hour. TCLI owns network caching (24 hours after success,
  15 minutes after failure). `TCLI_AUTO_UPDATE=0` disables the trigger. Bundled GA
  does not download independent upstream updates; standalone GA is unchanged.
  The patch adds no maintenance protocol or persistent update state.
