# patches

Out-of-tree patches against upstream `git-ai-project/git-ai`, applied by
`git-ai-wrapper/scripts/build-git-ai.sh`. Only top-level `*.patch` files in this
directory are active build inputs.

- `GIT_AI_VERSION` pins the upstream tag.
- `codebuddy-preset.patch` adds first-class CodeBuddy support. CodeBuddy's hook
  protocol is compatible with Claude Code, but its JSONL transcript stores the
  model in a structured `providerData.model` field (unlike Claude's
  `message.model`). The patch adds:
  - a `codebuddy` preset (`src/commands/checkpoint_agent/presets/codebuddy.rs`)
  - a `CodebuddyJsonl` stream format in both `StreamFormat` enums
  - a dedicated model extractor (`extract_model_from_codebuddy_jsonl_line`)
  - a `Codebuddy` tool classifier (reusing Claude's tool-name mapping)
  - a `CodebuddyInstaller` that writes `PreToolUse`/`PostToolUse` hooks into
    `~/.codebuddy/settings.json`

General git-ai attribution, blame, stats, and Git-Notes behavior remains owned
by upstream git-ai 1.7.0. The narrow downstream patch owns only CodeBuddy
preset and hook-installer support.

Delete the CodeBuddy patch only after an upstream release carries both its
source fix and regression coverage. To roll back, restore the complete prior
wrapper baseline commit/tag, including its matching patch and tests; do not
change only `GIT_AI_VERSION`.

Inactive diagnostic or recovery patches, if any, are documented in
`../disabled-patches/README.md` and are never applied from this directory.
