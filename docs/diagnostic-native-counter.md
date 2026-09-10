# Native eviction counter checkpoint v1

Native spool eviction counts now use two fixed-name, checksummed slots:
`drops.count` and `drops.alternate`. `DesktopDiagnostics.write` holds the existing
process/thread spool lock across load, eviction, checkpoint and event publication.
Python consumes the unchanged `desktop-diagnostic-v1` event records; it only counts
the extra slot as storage metadata and does not interpret native checkpoints.

Each record contains the literal prefix `diagnostic-counter-v1:`, a zero-padded
20-digit unsigned decimal count, `:`, the lowercase SHA-256 hex digest of the
prefix and decimal field, and a newline. Reads are limited to exact record size
plus one byte. Wrong size/checksum, non-regular paths and symlinks are rejected;
complete unknown version prefixes stop writes rather than being overwritten.
A partial version prefix is damage, permitting recovery from the other valid slot.
SHA-256 is integrity checking, not authentication or power-loss certification.

Load selects the maximum valid slot count. Each update rejects a decrease and
updates the older or damaged slot, preserving the other durable copy. Every slot
update writes the full fixed record, sets its size and calls `sync_all`. Creating
a slot also synchronizes its directory. Reusing an existing inode avoids the old
per-eviction rename/directory-sync checkpoint cost. Actual event deletions are
still synchronized before recording their count; the new event is still file-
synchronized, renamed and directory-synchronized after a successful checkpoint.
Retention remains 256 event files / 4 MiB, with seven-day expiry. No larger eviction
batch, asynchronous return or weakened event publication barrier is used.

For legacy ASCII `drops.count`, migration first synchronizes a backup of that
same baseline in `drops.alternate`, then rewrites/synchronizes the primary in the
new format. Until primary conversion the alternate does not advance beyond the
legacy baseline. If interrupted, either legacy primary or the backup can recover.
A valid legacy `drops.pending` at/above the current count is checkpointed before
its removal; stale or malformed pending data is removed with a reported failure.
Every pending removal remains directory-synchronized. Interrupted/new-format
partial overwrites recover the intact other slot and report observed damage.
If no valid baseline survives, collection refuses to reset the count to zero.

**Downgrade behavior:** an old native writer's ASCII counter reader rejects the
new `drops.count` format, so it stops writing native diagnostics instead of silently
using a stale count. Existing spooled events remain readable by Python. Application
business work is still independent of logging failure. This migration does not
support native logging from downgraded binaries; do not hand-edit/reset checkpoint
files to make an older binary accept them.

Tests cover real legacy/pending migration, all migration prefix cuts, torn fixed-
slot overwrites and truncations, repair, u64 bounds, downgrade/unknown-version
rejection and symlink/special-file refusal. Child processes exit after the durable
migration backup and after a partial inactive-slot overwrite; the parent recovers
the prior count, continues and verifies that the old reader rejects the result.
Existing full-ring expiry/size, two-writer, Python lock and sidecar tests remain.
These cases do not claim immunity to arbitrary device corruption or power loss.

[Performance and integration evidence](performance/diagnostic-native-journal-v1.md)
retains old failures and new measured results under the unchanged budget.
