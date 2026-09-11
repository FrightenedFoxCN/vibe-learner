"""Run only against an explicitly supplied disposable PostgreSQL database."""
import os, sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import text, update, delete
from app.persistence.models import StudySessionRow
from app.persistence.database import Database
from app.persistence.study_session_repository import StudySessionRepository
from app.models.domain import StudySessionRecord
url=os.environ['VIBE_INDEPENDENT_POSTGRES_URL']
assert url.startswith('postgresql')
db=Database(url); repo=StudySessionRepository(db)
if len(sys.argv)>1 and sys.argv[1]=='read':
 record=repo.require('independent-cas')
 assert record.revision==2 and set(record.prepared_study_unit_ids)=={'writer-a','writer-b'},record
 print('new process after PostgreSQL restart: revision=2, both writes retained PASS')
else:
 with db.engine.connect() as conn:
  print('migration head:',conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one())
 with db.session() as session:
  session.execute(delete(StudySessionRow).where(StudySessionRow.id=='independent-cas'))
 repo.create(StudySessionRecord(id='independent-cas',document_id='doc',persona_id='persona',study_unit_id='unit',status='active',turns=[],created_at='2026-09-11T00:00:00Z',updated_at='2026-09-11T00:00:00Z'))
 barrier=Barrier(2)
 def write(label):
  count=0
  def mutate(record):
   nonlocal count
   count+=1
   if count==1: barrier.wait(timeout=10)
   record.prepared_study_unit_ids.append(label)
  return repo.mutate(session_id='independent-cas',mutation=mutate)
 with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(write,['writer-a','writer-b']))
 record=repo.require('independent-cas')
 assert record.revision==2 and set(record.prepared_study_unit_ids)=={'writer-a','writer-b'},record
 print('forced concurrent stale snapshot CAS retry: revision=2, both writes retained PASS')
 try:
  with db.session() as session:
   session.execute(update(StudySessionRow).where(StudySessionRow.id=='independent-cas').values(status='corrupt'))
   raise RuntimeError('injected precommit failure')
 except RuntimeError: pass
 assert repo.require('independent-cas')==record
 print('injected precommit transaction rollback: exact record unchanged PASS')
db.dispose()
