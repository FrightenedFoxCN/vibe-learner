"""Replayable tavern-room-list-v1 fixture server and real HTTP measurements."""
from __future__ import annotations
import argparse
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import http.client
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

SERVICE_ROOT=Path(__file__).resolve().parents[2]
ROOT=SERVICE_ROOT.parents[1]
SEED='vibe-learner-tavern-1000-v1'
request_sql=ContextVar('acceptance_sql',default=None)


def serve(root,port,frontend_origin=None):
    sys.path.insert(0,str(SERVICE_ROOT))
    from sqlalchemy import event, select, func, update
    from app.app_factory import create_app
    from app.core.bootstrap import Container
    from app.core.settings import Settings
    from app.persistence.models import TavernRoomRow,TavernParticipantRow,TavernMessageRow
    from tests.test_tavern_room_pagination import TavernRoomPaginationTests
    import uvicorn
    root.mkdir(parents=True,exist_ok=True)
    if (root/'runtime.sqlite3').exists(): raise RuntimeError('requires fresh isolated root')
    def factory(settings):
        container=Container(settings)
        TavernRoomPaginationTests._seed_fixture.__func__(SimpleNamespace(database=container.database))
        # The original repository fixture deliberately has empty snapshots. Add
        # valid fixed Persona DTOs so real frontend detail/runs reads also work;
        # all versioned Room/Participant widths and counts stay unchanged.
        from app.models.domain import PersonaProfile
        with container.database.session() as session:
            for index in range(6):
                persona_id=f"persona-{index:016d}"
                snapshot=PersonaProfile(id=persona_id,name="角"*48,source="builtin",
                    summary="Fixed independent pagination fixture",system_prompt="Use fixture content only",
                    available_emotions=["calm"],available_actions=["explain"],default_speech_style="clear").model_dump(mode="json")
                session.execute(update(TavernParticipantRow).where(TavernParticipantRow.persona_id==persona_id).values(
                    persona_snapshot=snapshot,prompt_hash=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()))
        with container.database.session() as session:
            rooms=list(session.scalars(select(TavernRoomRow)))
            participants=list(session.scalars(select(TavernParticipantRow)))
            counts=dict(session.execute(select(TavernParticipantRow.room_id,func.count()).group_by(TavernParticipantRow.room_id)).all())
            messages=session.scalar(select(func.count()).select_from(TavernMessageRow))
        ordered=sorted(rooms,key=lambda r:(r.updated_at,r.id),reverse=True)
        assert len(rooms)==1000 and all(len(r.id)==24 and len(r.title)==64 for r in rooms)
        assert all(len(p.persona_id)==24 and p.persona_id.isascii() and len(p.display_name)==48 for p in participants)
        assert set(counts.values())==set(range(1,7))
        assert all(counts[r.id]==6 for r in ordered[:50])
        assert ordered[29].updated_at==ordered[30].updated_at and ordered[49].updated_at==ordered[50].updated_at
        manifest={'contract':'tavern-room-list-fixture-v1','seed':SEED,'rooms':len(rooms),
            'participants':len(participants),'messages':messages,'id_length':24,'title_unicode_scalars':64,
            'persona_id_ascii_length':24,'name_unicode_scalars':48,'timestamp_equal_group_size':7,
            'participant_counts':sorted(set(counts.values())),'first_50_all_six_participants':True,
            'boundaries_30_and_50_split_equal_timestamp_groups':True,
            'detail_support':'valid fixed PersonaProfile snapshots; summary fixture unchanged',
            'ordered_ids':[r.id for r in ordered]}
        (root/'fixture.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        def count(conn,cursor,statement,parameters,context,many):
            active=request_sql.get()
            if active is not None: active.append(statement)
        event.listen(container.database.engine,'before_cursor_execute',count)
        return container
    app=create_app(settings=Settings(database_url=f'sqlite:///{root/"runtime.sqlite3"}',storage_root=str(root/'data'),plan_provider='mock',auto_migrate_local_data=False,
        allowed_origins=('http://localhost:3000','http://127.0.0.1:3000',*((frontend_origin,) if frontend_origin else ()))),container_factory=factory)
    async def instrumented(scope,receive,send):
        if scope.get('type')!='http' or scope.get('path')!='/tavern/rooms':
            return await app(scope,receive,send)
        statements=[]; token=request_sql.set(statements); start=time.perf_counter()
        async def observed(message):
            if message['type']=='http.response.start':
                headers=list(message.get('headers',[]))
                headers += [(b'x-acceptance-sql-count',str(len(statements)).encode()),
                            (b'x-acceptance-server-ms',str((time.perf_counter()-start)*1000).encode()),
                            (b'x-acceptance-message-body-selected',str(any('tavern_messages.content' in s or 'tavern_messages.payload' in s for s in statements)).lower().encode())]
                message={**message,'headers':headers}
            await send(message)
        try: await app(scope,receive,observed)
        finally: request_sql.reset(token)
    uvicorn.run(instrumented,host='127.0.0.1',port=port,access_log=False,log_level='warning')


def measure(base_url,fixture_path,output):
    address=urlsplit(base_url)
    if address.hostname not in {'127.0.0.1','localhost'}: raise ValueError('loopback fixture only')
    fixture=json.loads(fixture_path.read_text())
    assert fixture['seed']==SEED and fixture['rooms']==1000 and fixture['first_50_all_six_participants']
    connection=http.client.HTTPConnection(address.hostname,address.port,timeout=10)
    def fetch(limit,cursor=None):
        query={'limit':limit}
        if cursor is not None: query['cursor']=cursor
        start=time.perf_counter(); connection.request('GET','/tavern/rooms?'+urlencode(query),headers={'Accept-Encoding':'identity'})
        response=connection.getresponse(); body=response.read(); elapsed=(time.perf_counter()-start)*1000
        assert response.status==200,(response.status,body[:1000])
        assert response.getheader('Content-Encoding') in (None,'identity')
        return json.loads(body),{'elapsed_ms':elapsed,'server_ms':float(response.getheader('x-acceptance-server-ms')),
            'sql_count':int(response.getheader('x-acceptance-sql-count')),'payload_bytes':len(body),
            'message_body_selected':response.getheader('x-acceptance-message-body-selected')!='false'}
    groups=[]
    for limit in (30,50):
        pages=[]; cursor=None; ids=[]
        while True:
            page,stats=fetch(limit,cursor)
            assert len(page['items']) == min(limit,1000-len(ids))
            pages.append({'cursor':cursor,'item_count':len(page['items']),'offset':len(ids)})
            ids += [item['id'] for item in page['items']]
            assert all(len(item['title'])==64 and all(len(n)==48 for n in item['participant_names']) and all(len(p)==24 and p.isascii() for p in item['participant_persona_ids']) for item in page['items'])
            assert stats['sql_count']<=4 and not stats['message_body_selected']
            if len(pages)==1 and limit==50: assert all(len(item['participant_names'])==6 for item in page['items'])
            if page['next_cursor'] is None: break
            cursor=page['next_cursor']
        assert ids==fixture['ordered_ids'] and len(set(ids))==1000
        for label,index in [('first',0),('middle',(len(pages)-1)//2),('final',len(pages)-1)]:
            anchor=pages[index]
            for _ in range(5): fetch(limit,anchor['cursor'])
            samples=[]
            for index in range(50):
                page,sample=fetch(limit,anchor['cursor']); sample['index']=index+1
                sample['item_count']=len(page['items']); samples.append(sample)
            elapsed=sorted(s['elapsed_ms'] for s in samples)
            server=sorted(s['server_ms'] for s in samples)
            group={'page_size':limit,'position':label,**anchor,'warmups':5,'sample_count':50,
                'http_p50_ms':elapsed[math.ceil(len(elapsed)*.50)-1],'http_p95_ms':elapsed[math.ceil(len(elapsed)*.95)-1],
                'http_max_ms':max(elapsed),'server_p95_ms':server[math.ceil(len(server)*.95)-1],
                'sql_max':max(s['sql_count'] for s in samples),'payload_max_bytes':max(s['payload_bytes'] for s in samples),
                'samples':samples}
            group['passed']=(group['http_p95_ms']<=(100 if limit==30 else 120) and group['sql_max']<=4
                and group['payload_max_bytes']<=(192 if limit==30 else 320)*1024 and not any(s['message_body_selected'] for s in samples)
                and all(s['item_count']==anchor['item_count'] and s['item_count']<=limit for s in samples))
            groups.append(group)
            print(json.dumps({k:v for k,v in group.items() if k!='samples'}),flush=True)
    connection.close()
    report={'schema_version':'tavern-room-http-acceptance-v1','scenario':'tavern-room-list-v1','fixture':fixture,
        'commit_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'platform':platform.platform(),'python':sys.version,'time_utc':datetime.now(timezone.utc).isoformat(),
        'timing':'perf_counter before HTTP request through complete uncompressed body read; server header through response start',
        'percentile_method':'nearest rank ceil(p*n), all measured samples retained','groups':groups,
        'measured_sample_count':sum(g['sample_count'] for g in groups),'passed':all(g['passed'] for g in groups)}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--root',type=Path)
    parser.add_argument('--frontend-origin');parser.add_argument('--port',type=int,default=8897);parser.add_argument('--base-url',default='http://127.0.0.1:8897')
    parser.add_argument('--fixture',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.serve:
        if args.root is None: parser.error('--serve requires --root')
        serve(args.root,args.port,args.frontend_origin);return 0
    if args.fixture is None or args.output is None: parser.error('measurement requires --fixture and --output')
    return measure(args.base_url,args.fixture,args.output)
if __name__=='__main__':raise SystemExit(main())
