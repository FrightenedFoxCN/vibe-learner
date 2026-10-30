# Diagnostic storage policy and verified limits

Enforcement is per owned store, with explicit recovery exceptions. The 200 MiB
installation reference is not an enforced aggregate hard cap. Payload retention,
physical admission and transient recovery have separate limits.

| Owner | Normal enforced policy | Evidence/source |
| --- | --- | --- |
| Browser ring and server event queue | 1,000 events per bounded queue; overflow counted | `apps/web/lib/diagnostics.ts`, `services/ai/app/core/diagnostics.py` |
| Browser ingestion | At most 100 events/batch and 16 KiB serialized/event | `services/ai/app/api/diagnostic_routes.py` |
| Event payload retention | Seven days from DB ingestion, 10,000 rows, 64 MiB UTF-8 payload | `core/diagnostic_retention.py`, event retention tests |
| Operation links | Seven days, 10,000 rows, 4 MiB payload | `core/diagnostic_record_retention.py` |
| Harness diagnostic index | Seven days, 5,000 rows, 32 MiB payload | `core/diagnostic_record_retention.py`, `services/diagnostic_index.py` |
| Event database admission | 128 MiB owned DB/side-file envelope | `core/diagnostic_quota.py` and quota tests |
| Index database admission | 64 MiB owned DB/side-file envelope | `services/diagnostic_index.py` and quota tests |
| Native event spool | 256 files, seven days, maximum 16 KiB/new event; 4 MiB event envelope | `apps/desktop/src-tauri/src/diagnostics.rs` and native tests |

Python paths above are relative to `services/ai/app`. Payload and physical limits
are distinct. Operation links share the event database: their 4 MiB payload budget
is not another physical database envelope to add to 128 MiB. Canonical business
operations and Harness evidence have their own retention owners and are not
pruned by diagnostic cleanup. Seven days is a ceiling, not a promise of seven days
of complete records: row, byte and pressure limits can expire records earlier.

Normal event/index/spool envelopes sum to 196 MiB. This sum is useful configuration
arithmetic, not evidence of an atomic directory peak. Unknown external files,
filesystem allocation/metadata, transient recovery and incomplete directory scans
prevent an installation-wide 200 MiB claim. Unknown files are observed with
explicit gaps; the collector does not delete arbitrary files merely to meet a
reference number. Read-only observations report lengths, not allocated disk blocks.

Oversize legacy recovery may use up to 512 MiB of separately checked transient
workspace. A shared installation recovery lock serializes event/index recovery;
ordinary writes retain per-owner admission. A five-second cooperative SQL budget
and retry backoff bound attempts, but are not hard wall-clock/filesystem bounds.
Pinned readers, insufficient workspace and contention can postpone reclamation.
Failure and loss counters remain visible; a logging refusal never changes a
business commit into rollback or success.

The [storage probes](performance/diagnostic-local-baseline-v1.md) cover combined
Rust/Python quota pressure, pinned-reader release, integrity and legacy recovery.
Observed file lengths and sampled maxima do not certify atomic installation peaks
or filesystem allocation. `disk_size_limit_certified` remains false until the
installation-wide acceptance in root TODO is complete.

Native counter metadata now uses two bounded checksummed slots; see the
[versioned protocol](diagnostic-native-counter.md) for migration and downgrade
behavior. This changes checkpoint persistence, not event retention or quotas.
