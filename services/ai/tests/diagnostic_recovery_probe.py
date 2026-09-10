"""Provider-free single-sample probe of a 144 MiB legacy freelist recovery.

Run from the repository root with:
  uv run --directory services/ai python -m tests.diagnostic_recovery_probe
This reports an observation, not a performance or installation budget gate.
"""
import hashlib
from datetime import datetime, timezone
import json, sqlite3, time, platform
from pathlib import Path
from tempfile import TemporaryDirectory
from app.core.diagnostics import DiagnosticStore
from tests.test_diagnostic_recovery import DiagnosticRecoveryTests
with TemporaryDirectory() as directory:
 path = Path(directory) / 'events.db'
 DiagnosticRecoveryTests().seed_events(path)
 with sqlite3.connect(path) as db:
  db.execute('CREATE TABLE padding(value BLOB)')
  db.execute('INSERT INTO padding VALUES (zeroblob(?))',(144*1024*1024,))
  db.execute('DROP TABLE padding'); db.commit()
 store=DiagnosticStore(path)
 before=sum(store.quota.sizes().values())
 start=time.perf_counter()
 store.start(); store.emit('lifecycle_started')
 deadline=time.monotonic()+15
 while store.queue.unfinished_tasks and time.monotonic()<deadline:
  time.sleep(.01)
 store.close()
 elapsed=(time.perf_counter()-start)*1000
 with sqlite3.connect(path) as db:
  integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
  retained,removed=db.execute('SELECT retained_events,removed_events FROM event_retention').fetchone()
 source_root = Path(__file__).parents[1]
 sources = ['app/core/diagnostic_quota.py', 'app/core/diagnostic_recovery.py', 'app/core/diagnostics.py', 'app/services/diagnostic_index.py']
 result=dict(observed_at=datetime.now(timezone.utc).isoformat(), source_sha256={name: hashlib.sha256((source_root/name).read_bytes()).hexdigest() for name in sources}, schema_version='diagnostic-recovery-local-observation-v1',platform=platform.platform(),
  sqlite_version=sqlite3.sqlite_version,quota_bytes=store.quota.max_bytes,workspace_bytes=store.oversize_recovery.workspace_bytes,
  before_bytes=before,after_bytes=sum(store.quota.sizes().values()),elapsed_ms=elapsed,attempts=store.oversize_recovery.attempts,
  completed=store.oversize_recovery.completed,retained_events=retained,removed_events=removed,integrity=integrity,
  scenario='144_MiB_freelist_legacy_event_database_200_safe_events',samples=1,
  installation_limit_certified=False)
 print(json.dumps(result,indent=2))
 assert store.oversize_recovery.completed==1 and store.queue.unfinished_tasks==0 and integrity=='ok'
 assert before>store.quota.max_bytes and result['after_bytes']<store.quota.max_bytes
