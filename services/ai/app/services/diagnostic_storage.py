from datetime import datetime, timezone
from app.models.diagnostic_storage import DiagnosticStorageV1


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
        unmeasured=["desktop_spool", "filesystem_allocation_and_metadata", "external_writers", "vacuum_temporary_files"])
