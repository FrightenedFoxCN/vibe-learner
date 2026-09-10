"""Bounded no-follow inventory of diagnostic file lengths, never file contents.

This is a separate live scan, not a sum of separately sampled database/spool
observations, allocated-block accounting, or an admission guarantee.
"""
import os
import stat
import time


def observe_diagnostic_directory(store, index, *, budget_seconds=0.1):
    value = dict(status="unavailable", gaps=["not_configured"], budget_state="unknown",
                 database_bytes=0, spool_bytes=0, other_bytes=0, total_bytes=0,
                 database_files=0, spool_files=0, other_files=0, scanned_entries=0,
                 visited_directories=0, skipped_entries=0, max_bytes=200 * 1024 * 1024,
                 scan_limit=4096, max_depth=4, scan_budget_ms=100,
                 scope="diagnostics_directory_regular_file_lengths")
    if store is None:
        return value
    root = store.path.parent
    families = set()
    gaps = []
    for owner in (store, index):
        if owner is None:
            continue
        if owner.path.parent != root:
            gaps.append("configured_database_outside_directory")
            continue
        families.update(owner.path.name + suffix for suffix in ("", "-wal", "-shm", "-journal", ".quota-lock"))
    deadline = time.monotonic() + budget_seconds

    def gap(reason):
        if reason not in gaps:
            gaps.append(reason)

    def scan(descriptor, depth, in_spool):
        value["visited_directories"] += 1
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if time.monotonic() >= deadline:
                    gap("time_limit")
                    return
                if value["scanned_entries"] >= value["scan_limit"]:
                    gap("scan_limit")
                    return
                value["scanned_entries"] += 1
                try:
                    observed = entry.stat(follow_symlinks=False)
                    if stat.S_ISREG(observed.st_mode):
                        kind = "spool" if in_spool else "database" if depth == 0 and entry.name in families else "other"
                        value[kind + "_files"] += 1
                        value[kind + "_bytes"] += observed.st_size
                        value["total_bytes"] += observed.st_size
                    elif stat.S_ISDIR(observed.st_mode):
                        if depth >= value["max_depth"]:
                            value["skipped_entries"] += 1
                            gap("depth_limit")
                            continue
                        child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                        try:
                            current = os.fstat(child)
                            if (current.st_dev, current.st_ino) != (observed.st_dev, observed.st_ino):
                                value["skipped_entries"] += 1
                                gap("filesystem_unavailable")
                                continue
                            scan(child, depth + 1, in_spool or (depth == 0 and entry.name == "desktop-spool"))
                        finally:
                            os.close(child)
                        if "scan_limit" in gaps or "time_limit" in gaps:
                            return
                    else:
                        value["skipped_entries"] += 1
                        gap("unsupported_entry")
                except OSError:
                    value["skipped_entries"] += 1
                    gap("filesystem_unavailable")

    descriptor = None
    try:
        if os.scandir not in os.supports_fd or os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
            value["gaps"] = ["filesystem_unavailable"]
            return value
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        scan(descriptor, 0, False)
        value.update(status="incomplete" if gaps else "observed", gaps=gaps)
    except FileNotFoundError:
        value.update(status="incomplete" if gaps else "absent", gaps=gaps)
    except OSError:
        value.update(gaps=["filesystem_unavailable"])
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if value["total_bytes"] > value["max_bytes"]:
        value["budget_state"] = "over_observed_limit"
    elif value["status"] == "observed":
        value["budget_state"] = "within_observed_limit"
    return value
