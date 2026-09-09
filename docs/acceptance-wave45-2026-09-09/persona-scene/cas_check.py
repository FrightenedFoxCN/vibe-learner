import httpx,json
from pathlib import Path
from app.models.api import UpdatePersonaRequest, UpsertSceneLibraryRequest
c=httpx.Client(base_url='http://127.0.0.1:64052')
p=next(x for x in c.get('/personas').json()['items'] if x['name']=='Wave45 M3 Observatory Tutor')
s=next(x for x in c.get('/scene-library').json()['items'] if x['scene_name']=='Wave45 M3 Observatory Text')
pr={k:v for k,v in p.items() if k in UpdatePersonaRequest.model_fields};pr['expected_revision']=p['revision']-1
sr={k:v for k,v in s.items() if k in UpsertSceneLibraryRequest.model_fields};sr['expected_revision']=s['revision']-1
out=[]
for kind,path,payload in [('persona','/personas/'+p['id'],pr),('scene','/scene-library/'+s['scene_id'],sr)]:
 r=c.patch(path,json=payload) if kind=='persona' else c.put(path,json=payload)
 assert r.status_code==409,(kind,r.status_code,r.text)
 out.append({'case':kind+'_stale_revision','status':r.status_code,'detail':r.json()})
p2=next(x for x in c.get('/personas').json()['items'] if x['id']==p['id']);s2=c.get('/scene-library/'+s['scene_id']).json()
assert p2==p and s2==s
out.append({'case':'stale_writes_left_records_unchanged','passed':True})
Path('/Users/ffox/vibe-learner/docs/acceptance-wave45-2026-09-09/persona-scene/cas-live.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
