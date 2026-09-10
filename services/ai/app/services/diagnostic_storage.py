import os
import re
import stat
from datetime import datetime, timezone
from app.models.diagnostic_storage import DiagnosticStorageV1


def observe_spool(root):
    value = dict(status="unavailable", gap="not_configured", event_files=0, event_bytes=0,
                 metadata_bytes=0, other_files=0, other_bytes=0, skipped_entries=0, total_bytes=0)
    if root is None:
        return value
    try:
        mode = root.lstat().st_mode
        if not stat.S_ISDIR(mode):
            value.update(gap="unsupported_entry", status="incomplete", skipped_entries=1)
            return value
    except FileNotFoundError:
        value.update(status="absent", gap=None)
        return value
    except OSError:
        value.update(gap="filesystem_unavailable")
        return value
    descriptor = None
    try:
        # Pin the directory without following a replacement symlink. Platforms
        # without descriptor scans report a gap instead of weakening this bound.
        if os.scandir not in os.supports_fd or not hasattr(os, "O_NOFOLLOW"):
            value.update(gap="filesystem_unavailable")
            return value
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        with os.scandir(descriptor) as entries:
            value.update(status="observed", gap=None)
            for i, entry in enumerate(entries):
                if i >= 1024:
                    value.update(status="incomplete", gap="scan_limit")
                    break
                try:
                    observed = entry.stat(follow_symlinks=False)
                except OSError:
                    value["skipped_entries"] += 1
                    value.update(status="incomplete", gap="filesystem_unavailable")
                    continue
                if not stat.S_ISREG(observed.st_mode):
                    value["skipped_entries"] += 1
                    value.update(status="incomplete", gap="unsupported_entry")
                    continue
                size = observed.st_size
                if re.fullmatch(r"desktop-[a-f0-9-]{1,88}\.(json|pending)", entry.name):
                    value["event_files"] += 1
                    value["event_bytes"] += size
                elif entry.name in {"drops.count", "drops.pending", "spool.quota-lock"}:
                    value["metadata_bytes"] += size
                else:
                    value["other_files"] += 1
                    value["other_bytes"] += size
                value["total_bytes"] += size
    except OSError:
        value.update(status="unavailable", gap="filesystem_unavailable")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return value


def observe_diagnostic_storage(store, index):
    databases = []
    for name, owner in (("events", store), ("index", index)):
        value = dict(name=name, max_bytes=None, files=None, counters=None, status="unavailable", gap="not_configured")
        if owner is not None:
            quota, maintenance = owner.quota, owner.disk_maintenance
            value.update(max_bytes=quota.max_bytes, counters=dict(quota_refusals=quota.rejected, quota_unavailable=quota.unavailable,
                maintenance_busy=maintenance.busy, maintenance_failures=maintenance.failures,
                maintenance_completed=maintenance.completed, legacy_migrations=maintenance.legacy_migrations))
            try:
                sizes = quota.sizes()
                total = sum(sizes.values())
                value.update(files={**sizes, "total_bytes": total}, gap=None,
                    status="over_observed_limit" if total > quota.max_bytes else "within_observed_limit")
                if sizes["database"] == 0:
                    value.update(status="unavailable", gap="database_absent")
            except OSError:
                value.update(gap="filesystem_unavailable")
        databases.append(value)
    return DiagnosticStorageV1(observed_at=datetime.now(timezone.utc), databases=databases,
        desktop_spool=observe_spool(store.path.parent / "desktop-spool" if store is not None else None),
        unmeasured=["filesystem_allocation_and_metadata", "external_writers", "vacuum_temporary_files"])
