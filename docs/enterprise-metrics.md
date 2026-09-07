# Enterprise checkpoint / commit telemetry

Enterprise settings are owned by the publisher and embedded in the sidecar.
End users do not copy JSON files, configure tokens, or maintain identity maps.
The enterprise patch applies after CodeBuddy on upstream `v1.7.0`.

## Publisher configuration and builds

The fixed publisher configuration is
[`config/enterprise-metrics.release.json`](../config/enterprise-metrics.release.json),
kept in the repository at the user's request. It defaults to `enabled: true` and
contains the documented endpoint/token, a generated stable HMAC identity secret,
and the verified ACK rule: HTTP 200 plus JSON `/success` equal to `true`.
The company `organization_id` is `tinnove`, as confirmed by the publisher. The template remains available at
[`enterprise-metrics.example.json`](../config/enterprise-metrics.example.json).

```bash
scripts/build-git-ai.sh --out dist/raw --version v1.7.0-tac.v0.2.0
```

Use the intended wrapper release tag for `--version`. The script resolves
the fixed config relative to its own repository, regardless of the caller's working
directory. No `--enterprise-config` argument or environment override is needed or
accepted. GitHub Actions uses the same checked-in file and the release tag;
`ENTERPRISE_METRICS_CONFIG_JSON` is no longer required.

The generated module embeds both settings and wrapper version. The JSON does not
contain `client_version`, `users`, `repositories`, `token_env`, or `token_file`.
Missing or invalid required values fail the build. Preserve `identity_secret`
across releases; changing it changes derived identifiers and queue scope.
Token rotation means updating this file and distributing a new package.
The JSON is not shipped as a separate release asset or printed in build logs;
credentials remain excluded from queue snapshots and status output. Direct
upstream Cargo/test builds still use the disabled fixture embedded in the patch.

Production does not read `~/.git-ai/enterprise-metrics.json` or
`TCLI_GA_TELEMETRY_CONFIG`. Only test/test-support binaries accept
`GIT_AI_TEST_ENTERPRISE_CONFIG` for isolated fixtures. Updating the packaged
configuration requires distributing the new sidecar and restarting its daemon.
No installer or test in this change modifies live settings or starts a
production daemon. Existing collection hooks/Trace2 still need to be installed
by the normal product initialization.

## Automatic identity

- `user_id` is the effective repository Git `user.email`, including global
  fallback and local/worktree overrides through the existing Git config reader.
  It identifies the configured project user, not a historical commit author.
- `repo_id` is the normalized `origin` fetch URL; without origin, the sole remote
  is used. Multiple remotes without origin, missing URLs and missing email do
  not get guessed. SSH/HTTPS forms use the existing canonical HTTPS normalizer,
  removing credentials, `.git` and trailing slash. Nondefault ports remain distinct;
  SSH aliases without `user@` are accepted. Host aliases are not merged.
- Identity is captured once when constructing checkpoint/commit metric attributes,
  outside Trace2 ingestion and per-file loops, using one config snapshot (including branch-conditional includes) and no
  new Git subprocess. The upload worker never reads current repository state.
- Different repositories and later config changes produce their own snapshots;
  pending events keep their original identity. Missing snapshots stay locally
  pending with `waiting_identity` until retention expires; adding config later
  does not rewrite historical evidence. New events use the corrected config.
- Reserved enterprise custom attributes preserve the upstream author/URL fields.
  `commit_id` is the full original Git SHA, scoped by `repo_id`; other opaque IDs
  retain HMAC-SHA256 using the publisher's stable identity secret.

## Success contract

The endpoint is a complete URL, including the documented `prxoy` spelling.
The `adapter: "autopai-v1"` registry entry owns the wire mapping; new backends
implement EventSink and register a factory without changing queue policy.
Each request is `POST`, `Content-Type: application/json`, header `token`, and
`{"completeData": <one event>}`. Redirects are never followed with credentials.
Endpoint validation requires HTTPS without embedded credentials/query/fragment.

Explicit policies:

```json
{"mode": "unconfirmed"}
```

No network transmission. Default policy.

```json
{"mode": "http_200"}
```

Use only if the service guarantees HTTP 200 means the event was durably accepted,
including duplicate requests. No business response body is required.

```json
{"mode": "json", "pointer": "/code", "equals": 0, "event_id_pointer": "/event_id"}
```

Illustrative configurable policy, **not a claim about the real service response**.
Requires HTTP 200, the configured JSON value, and optionally the matching event
ID. Unknown 2xx, 400/422/409 and unexplained business failures block that event
type instead of guessing. 401/403 blocks the destination; 404/405/redirects block
its address; network/408/429/5xx retry with backoff and valid Retry-After;
413 is a permanent individual rejection. Dead letters are not replayed by retry.

## Events and identity

Both payloads have schema_version=1, stable UUID event_id, UTC event_timestamp,
client_version, organization_id, user_id, repo_id, and optional tool/model/session.

- `checkpoint`: kind (`ai_agent`, `ai_tab`, `known_human`, `unknown`),
  measurement_mode (`direct`, `recovery`), added/deleted lines, optional SLOC,
  opaque file/tool-use/trace IDs and known edit/checkpoint subtypes. One source
  file fact is one event, even when two real edits have identical counts. The
  legacy source kind `human` maps to `unknown`. Known recovery subtypes are
  recovered_bash, recovered_session_event_mtime, recovered_commit_metadata and
  recovered_edge_extension. Recovery counts are separate from direct editing.
- `commit`: original Git commit SHA, committed_at, Git added/deleted counts,
  AI/known-human/unknown additions, tool_model_breakdown, is_merge=false,
  is_rewrite=false. Parent count is carried from the existing stats preflight
  through a reserved local metric attribute; no additional Git lookup is added.
  Missing evidence is quarantined, rather than converted into zero or false.
  The `all` AI aggregate is not added to its breakdown again.

Logical checkpoint_id and sequence are omitted where the source cannot prove
an identity/order; trace/tool-use ID alone is not a logical checkpoint identity.
Commits do not fabricate a unique session. The server must accept these optional
fields. Merge/rewrite/session/token_usage production routes remain out of scope.
No source code, diff, prompt, transcript, raw file path, commit message or recovery
metadata is copied into the enterprise DTO. Email and normalized repository URL
are intentional identity fields.

Organization, identity secret and destination changes never redirect existing
work to a different scope. The email/URL identity scheme has a separate binding
from the old mapping-based scheme; old queues are not silently reinterpreted.
Token changes for the same destination resume pending work; changing endpoint
creates a different destination binding. No historical backfill is provided.

## Durability and operations

Source metrics and enterprise inbox references share a SQLite transaction.
Projection writes the allowlisted event plus one delivery row per destination
in a second transaction. Unprojected source rows are protected from normal
metrics pruning. No network runs under a DB transaction or on the Git/Hook path.
The existing pre-persistence telemetry queue is best-effort; overflow/disk failure
still means missing observations. Status exposes upstream dropped batches.

Worker passes project up to 50 rows and attempt up to four deliveries with at
most two concurrent HTTP requests. Each destination uses 1:3 commit/checkpoint
weighted scheduling, borrowing unused slots, plus its configured minimum request
interval. Requests use three-second connect / ten-second total timeouts and
120-second leases. Stale ACKs cannot overwrite a newer lease. Retry-After and
retry state survive daemon restarts; packaged configuration/credential changes on restart or explicit
retry resume blocked work. Two in-flight requests may complete after a block.

Default capacity is 100 MiB with 20 MiB reserved for commits, and retention is
30 days. The quota charges source bytes, serialized destination bindings and a
per-event overhead allowance; it is a **logical reservation, not an exact SQLite
file-size limit** (WAL, indexes and reusable pages add overhead). Quota checks use
transactional counters, not full scans on every event. Capacity overflow refuses
new events by type and records loss; expiry releases inbox references and records
undelivered losses. Delivered history is retained for the configured period.
Do not copy/rebuild a source database to replay historical checkpoints with new
IDs: this release only captures new source inserts and does not provide backfill.

```text
tcli telemetry status   # JSON counts, oldest age, ACKs, scope/contract errors,
                        # losses, type blocks, direct/recovery and trace coverage
tcli telemetry flush    # wake one asynchronous worker pass; not a delivery ACK
tcli telemetry retry    # resume retryable/blocked work; preserve event IDs
```

Management uses the bundled sidecar's `enterprise-telemetry` control command.
Existing `tcli ga [args...]` forwarding, streams and exit status are preserved.
All network retries are at-least-once. The server still needs event-ID uniqueness,
commit business deduplication and revision rules; the client cannot implement
server-side exactly-once or infer that a timed-out request was rejected.

## Validation and release

The zero-configuration revision passed 2,424 library tests (one upstream ignored),
the real checkpoint/commit and recovery integration tests, seven targeted identity
regressions, and four publisher-generator tests. Both patches apply to the exact
pin and reproduce all 24 changed source files byte-for-byte. Standard Clippy on
Rust 1.98 still reports the same 12 upstream diagnostics as before; allowing only
those six existing lint categories yields a passing all-targets check.


The patch gate applies both patches to the exact upstream tag, runs the full
library suite and the real TestRepo checkpoint/commit and recovery identity integration tests. The HTTP
adapter test uses a local mock server, not the production endpoint. Native
release builds continue to cover the existing six-platform matrix.

For local tests, use the repository Task runner and an explicit CARGO_HOME;
TestRepo changes HOME for isolation and otherwise its nested Cargo build loses
the dependency cache. Tests needing IPC/local sockets must run in an environment
that permits the isolated test daemon. No `task dev`/system installation is
needed for these tests.
