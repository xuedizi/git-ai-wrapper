# CodeBuddy CLI and IDE working directories

The CodeBuddy preset first uses the hook JSON `cwd` when it is an absolute,
existing directory from which a Git repository can be discovered. Otherwise it
tries the hook process's actual working directory (`std::env::current_dir`, or
`getcwd`). It does not read `PWD`, `CODEBUDDY_PROJECT_DIR`, or
`CLAUDE_PROJECT_DIR`, and does not change the process working directory.

This handles CodeBuddy CN IDE events containing `cwd: "/"` while the hook
process is already running in the project. Valid CLI event directories retain
priority, even when the hook process runs in another repository. The selected
directory is preserved, including repository subdirectories, and is used for
both preset context and relative edited-file paths.

Discovery uses the existing no-Git-subprocess implementation. Fallback emits a
structured warning with the event directory, process directory, selected
directory, source (`getcwd`), and reason. If neither source works, parsing returns
an explicit diagnostic containing both failures and emits no checkpoint request.
Read-only tools retain their existing skip behavior.

No hook command changes or additional interpreter dependencies are required.
Update the private git-ai executable through the TCLI release installer; updating
only the TCLI entrypoint does not apply this fix. Release builders must publish
and verify wrapper `v1.7.0-tac.v0.2.2` before packaging TCLI with that pin.

Regression coverage includes valid CLI event priority, IDE fallback, missing and
invalid event paths, spaces/subdirectories, failure of both sources, and real
PreToolUse/PostToolUse edit and Bash checkpoints followed by commit attribution.
Run `scripts/test-patched-git-ai.sh` to test the complete pinned patch stack.

This fix does not change model extraction (`auto` is not a concrete model), IDE
transcript parsing, or enterprise delivery configuration. A successful repository
lookup alone is not evidence that usage has reached the server.
