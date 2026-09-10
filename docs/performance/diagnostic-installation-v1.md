# Diagnostic installation storage probe

The [raw cross-runtime report](diagnostic-installation-v1.json) comes from one
provider-free disposable installation. It runs the production Python event writer,
index update path and desktop spool consumer concurrently with an actual compiled
Rust spool writer. Index sources deliberately return missing traces: this is
storage pressure, not model quality, production adoption or domain commit proof.

The fixture starts with a 60 MiB event freelist, a 28 MiB index freelist and 256
valid 16 KiB native records. Held SQLite readers create sustained WAL pressure
under the real 128 MiB / 64 MiB defaults. The native child attempts 1,200 events;
the event worker attempts 1,000, while the index attempts 160 batches. Both DB
quota refusals must occur. Readers are then released, maintenance resumes and
both SQLite integrity checks must pass. Samples include incomplete-scan gaps.

Normal configured envelopes sum to 196 MiB (128 + 64 + 4), leaving room below the
200 MiB reference for bounded producer metadata. This arithmetic and the observed
samples are not an installation-wide enforcement or atomic-peak certificate:
unknown/external files, filesystem blocks/metadata and legacy recovery exceptions
remain outside that claim. Lost/refused diagnostics are expected under this
intentional overload; counter values are reported, never relabeled as success.
The consumer uses a deliberately aggressive cadence; elapsed time is not a
performance baseline or product-latency gate.

Legacy recovery now holds one stable `recovery.quota-lock` per diagnostic
directory before its per-DB lock. This serializes transient recovery workspaces
across event and index owners while leaving ordinary per-DB writes independent.
It does not enforce a 200 MiB transient cap: a recovery may use its documented
512 MiB extra workspace, and outside writers are not controlled by this lock.
Tests exercise competing recovery owners and crash lock release. The probe also
exposed a writer connection that survived thread completion until garbage
collection; the writer now explicitly closes it, with a regression retaining a
strong reference to verify that maintenance can proceed without GC.

Reproduce from the repository root:

```sh
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib --no-run
# Pass the library-test executable printed by Cargo:
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_installation_probe --native-test-binary /absolute/path/to/library-test-executable
```

The report records runtime/platform, source and native-binary hashes, explicit
limits, refusals, elapsed time and raw sampled columns. It is local macOS/Unix
evidence; native Vault/UI and other platform acceptance remain separate.
