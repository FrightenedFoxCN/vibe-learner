# Diagnostic storage policy and verified limits

The initial Unified Debug plan listed retention of seven days or 200 MiB as a
**candidate default to validate during implementation**. Current enforcement is
per owned store, with explicit recovery exceptions. The candidate is not a proven
installation-wide hard cap. This document reconciles existing implementation and
evidence; it changes no runtime quota and grants no broader data retention scope.

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

The [combined Rust/Python pressure probe](performance/diagnostic-installation-v1.md)
actually triggered both DB quotas, recovered after pinned-reader release and
verified SQLite integrity. Its largest sampled directory length was about
103.22 MiB; incomplete observations are retained. Neither that sample maximum nor
196 MiB arithmetic certifies a 200 MiB hard installation cap. The
[legacy recovery report](performance/diagnostic-legacy-recovery-v1.md) and process
exit tests cover bounded recovery and interruption within their documented scope.

Permitted acceptance wording: bounded owner-specific collection, quota admission,
retention, recovery and honest directory observation are implemented and tested.
Do not describe the installation as capped at 200 MiB, guarantee lossless logging,
or equate payload retention with physical disk use. The candidate hard-cap claim
is unsupported and remains explicitly uncertified; no performance result changes
that conclusion.

Native counter metadata now uses two bounded checksummed slots; see the
[versioned protocol](diagnostic-native-counter.md) for migration and downgrade
behavior. This changes checkpoint persistence, not event retention or quotas.
