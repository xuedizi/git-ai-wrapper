# Enterprise zero-configuration patch implementation plan

Goal: package company settings in the sidecar, derive user/repository identity from each repository, and require no end-user configuration.
Approved specification: conversation decisions on 2026-09-07; user accepted the proposed field semantics.
Architecture: capture effective repository email and origin/sole remote once when constructing metric attributes, outside trace ingestion and outside file loops. Preserve upstream author/URL attributes; reserve enterprise snapshot attributes. Project frozen identifiers without identity maps. Embed release settings and wrapper version at build time. Keep durable delivery and unconfirmed ACK behavior.

## Constraints
- Preserve CodeBuddy patch and the upstream v1.7.0 pin.
- No production request, live daemon changes, installation, release, or fabricated credentials.
- Organization, stable HMAC secret and token are publisher inputs; unconfirmed ACK remains non-transmitting.
- user_id = effective repository user.email; repo_id = normalized origin URL (sole remote fallback); commit_id = full Git SHA.
- Default development/test configuration disabled; formal builds require publisher configuration and wrapper version.

## Tasks
- [x] Add failing tests for direct identity projection, source identity capture across repositories/config changes, SHA commits, embedded configuration validation and no runtime-config dependency.
- [x] Implement repository snapshots, remove maps, preserve snapshot semantics through persistence/projection, version the changed identity scope to prevent old event reinterpretation.
- [x] Embed publisher configuration via generated Rust source; add validated build input and automatic wrapper version wiring to release workflow. Unit tests use isolated fixtures only.
- [x] Update integration fixtures to distinguish configured email from commit author and verify canonical remote plus raw SHA. Run targeted and full library tests, TestRepo integrations, format/lint.
- [x] Regenerate only enterprise patch from CodeBuddy baseline; verify both patches apply cleanly to exact pin; update examples, README and implementation record.

Validation commands: task test CARGO_TEST_ARGS='--locked --lib' TEST_FILTER=enterprise_metrics; task test CARGO_TEST_ARGS='--locked --test integration' TEST_FILTER=enterprise_metrics; task test CARGO_TEST_ARGS='--locked --lib'; cargo fmt --check; python3 -m unittest discover -s scripts -p '*_test.py'. All Cargo work uses explicit CARGO_HOME and isolated target directories.
