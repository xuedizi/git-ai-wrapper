# Managed GA lifecycle protocol

`managed-update.patch` applies after the three existing wrapper patches to the
unchanged `v1.7.0` pin. Formal wrapper identity and the wrapper build's
`TCLI_MANAGED_GIT_AI=1` compile flag select TCLI ownership. Unmanaged upstream
builds retain their own update behavior. Managed `upgrade` directs users to
`tcli self-update`; foreground commands never schedule upstream network checks.

## CLI contract

```
git-ai managed-update identity
git-ai managed-update inspect [--transaction UUID] [--installation /absolute/.tcli/git-ai]
git-ai managed-update prepare|stop|abort|start|health|resume --transaction UUID \
  [--installation /absolute/.tcli/git-ai]
```

`identity` is entirely offline and reports the invoking candidate binary's
`protocol`, `wrapper_version`, `managed`, and schema fields before any config,
filesystem, or daemon access. TCLI uses it before maintenance to validate the
staged executable against its manifest.

Stdout is one JSON object. Errors return nonzero and contain `protocol: 1`,
`wrapper_version`, `error`, and false `ready`, `quiesced`, `durable` fields.
Successful replies contain:

| Field | Meaning |
| --- | --- |
| `protocol`, `wrapper_version` | Protocol 1 and actual embedded wrapper build identity. |
| `transaction`, `phase` | UUID or null; normal, prepared, stopping, validating. |
| `running`, `pid`, `executable`, `daemon_home` | Responsive daemon identity, or the stopped-runtime observation. |
| `started_at_ns` | Live daemon's startup metadata; the updater must independently verify OS process identity. |
| `busy`, `idle_seconds` | Active accepted work/foreground leases/AI sessions and conservative continuous idle observation. |
| `ready`, `quiesced`, `durable` | Worker initialization and successful local drain boundary; never upload completion. |
| `validation` | Live daemon is waiting to open business admission. |
| `data_schema`, `data_schema_min`, `data_schema_max` | 1 for this compatible pinned data implementation; no new migration is introduced. |

`--installation` binds a staged bridge to the eventual installed sidecar. The
bridge must execute from that exact file or its owned update staging subtree.
Live control replies must identify the requested runtime; prepare refuses a
daemon belonging to another executable. An unavailable control socket plus a
held lifecycle lock is blocked, never reported stopped. `inspect` does not
create a maintenance directory or start a daemon. Candidate copies can retain
names such as `bridge-git-ai`; command dispatch recognizes the bridge before
Git-proxy dispatch.

Each installation permanently binds its executable, canonical runtime/lock paths,
control/trace endpoints, and global database paths in the private
`<installation parent>/.git-ai-runtime/binding.json`. Startup, foreground entry,
inspection and maintenance reject any conflicting HOME, runtime override, or
data path even while stopped. The first startup/foreground operation or prepare
creates the binding atomically; read-only identity and inspection do not.
An incomplete binding fails closed. Changing this binding is outside this
protocol. Legacy binaries predate registration, so explicit offline migration
still requires externally pausing IDE/hooks and stopping every legacy runtime;
a new candidate cannot prove the absence of unregistered legacy homes.

## Coordination and recovery

Rust owns `<daemon internal>/managed-update/gate.lock`, foreground OS leases,
and a durable `state.json`. The gate serializes startup registration with
maintenance reservation; the persistent state survives updater failure and
has no TTL bypass. State is bound to a UUID and installed executable. Files are
owner checked; Unix forbids group/other writes and symlinks, Windows rejects
reparse points and uses a protected owner-only DACL for the dedicated namespace.
State replacement flushes the file and Unix directory, or uses Windows
`MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`.

- Prepare refuses active Git/AI root sessions or foreground commands, closes
  checkpoint and trace admission, drains previously accepted work and local
  metric persistence, then returns durable/quiesced. A failed prepare stays
  reversible; abort reopens the old daemon and clears the reservation.
- The trace boundary uses in-memory atomic counters only. It adds no filesystem
  reads, Git subprocesses, object lookups, or network calls to trace ingestion.
- Stream/token sweeps pause during prepare; their explicit drains still handle
  accepted notifications. Detached rewrite-metric producers finish before the
  FIFO local persistence barrier. Persistence errors and lost metric batches
  refuse certification, even if their upload queue is empty. Enterprise events
  share the local source-metric transaction; its asynchronous upload `flush` is
  never treated as a durability barrier.
- Stop requires successful prepare. It requests graceful shutdown after writing
  its response and disables the deadline's forced process exit for that stop.
  **The reply is not process-exit evidence.** TCLI must independently wait for
  the identified process and other executable users before replacing files.
- Start accepts the transaction capability and creates a validation daemon with
  ordinary ingress closed. Databases are opened using the pinned compatible
  schemas; stream/token, telemetry flush, enterprise delivery and metadata
  backfill wait for resume. Health requires initialized listeners and workers;
  database initialization that fell back to temporary storage blocks readiness.
  Offline health validates every existing SQLite database with `quick_check`
  and exact pinned schema versions. It copies database/WAL/journal files to a
  private disposable snapshot for SQLite recovery, never modifying installed
  data. Corrupt or newer/older schemas block the update. Missing databases are
  valid for a fresh/stopped installation. Validation startup applies the same
  check before opening installed databases.
- Resume follows TCLI's durable commit and reopens admission. Aborting a stopped
  transaction is rejected: the updater must recover the consistent release,
  start/health it if previously running, and resume. The originally stopped
  case stays stopped and can complete through local health/resume.

Ordinary `bg start/restart/shutdown`, internal restart, direct commands, and
self-restart routes cannot bypass the durable reservation. Checkpoint hooks
retain their host-compatible exit status while printing a maintenance deferral;
other blocked direct commands exit 75. Events emitted during the intentional
maintenance gap are not replayed or represented as successfully captured.
Trace rejections feed the existing loss counters. Fixed executable paths still
require TCLI's bounded sharing-conflict retries on Windows.

## Automatic checks

An installed managed daemon waits a random 60–300 seconds, then invokes the
paired `<install>/tcli _update-check --source daemon --install <install>/tcli`.
It checks again on a 60-second background timer; TCLI owns the shared network
cache, 24-hour interval, failure backoff, and 15-minute busy retry. Test/staging
paths do not qualify as an installed `.tcli/git-ai` checker source. There is no
network activity on Git/Hook ingestion paths. Activity counter changes and
foreground-directory changes reset the conservative idle observation, so
short commands between inspections cannot be counted as continuous idle.

## Validation record and remaining platform gates

The runtime-binding test first failed against the previous binary with
`inspect missed installation binding`. The live lifecycle test also caught
normal SQLite WAL residue before the snapshot validator was added; the WAL test
checks installed database and journal bytes remain unchanged and rejects future
schema versions.

The first protocol test failed on the original three-patch baseline because
`update.inspect` was an unknown control request, then passed with this patch.
On macOS arm64, seven focused library tests pass, including negative durability
acknowledgement, locked/unresponsive daemon, UUID ownership, and symlink refusal.
Seven isolated TestRepo integrations cover offline and renamed candidate identity, stopped-runtime/read-only behavior, corrupt database refusal, permanent runtime binding, canonical-path `bg start`, and
a live prepare/stop/new-PID/health/resume cycle preserving real checkpoint and
trace2 commit Git Notes. The live test also holds a foreground hook on stdin
and verifies busy deferral before it releases the lease.

The full macOS library run outside the sandbox passed 2,436 tests, ignored one,
and failed one pre-existing test that requires fetching Git Notes from the
archive scratch checkout's absent `origin`. No product code was changed for that
fixture dependency.

The installed Rust 1.98 Clippy reports twelve pre-existing upstream lints in six
lint classes. The new code passes all-target Clippy with only those existing
classes suppressed; the upstream pin and unrelated implementation are retained.
Windows security helper API types were checked against locked windows-sys
0.61.2 source. Windows compilation/runtime ACL tests, actual executable mapping
and sharing-conflict tests, Linux runtime tests, and cross-platform crash-point
fault injection remain required release gates. This local evidence does not
claim those platform guarantees have been exercised.
