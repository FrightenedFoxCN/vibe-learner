import json,os
from pathlib import Path
from app.services.model_provider import OpenAIModelProvider
from app.models.domain import PersonaSlot
root=Path('/Users/ffox/vibe-learner/docs/acceptance-wave45-2026-09-09/persona-scene')
p=OpenAIModelProvider(api_key=os.environ['K3_API_KEY'],base_url='https://api.minimax.cn/v1',plan_model='MiniMax-M3',setting_model='MiniMax-M3',timeout_seconds=90,setting_max_tokens=4096)
original=p._request_openai_chat_completion
responses=[]
def capture(*a,**kw):
 result=original(*a,**kw); responses.append(result[0]); return result
p._request_openai_chat_completion=capture
slot=PersonaSlot.model_validate(json.loads((root/'persona-before-fix.json').read_text())[0]['slots'][1])
try:
 result=p.assist_persona_slot(name='Wave45 M3 Observatory Tutor',summary='Patient astronomy tutor',slot=slot,rewrite_strength=.3)
 outcome={'status':'passed','slot':result['slot']}
except Exception as e:
 outcome={'status':'failed','error':str(e)}
(root/'slot-provider-diagnostic.json').write_text(json.dumps({'outcome':outcome,'responses':responses},ensure_ascii=False,indent=2))
print(json.dumps({'status':outcome['status'],'error':outcome.get('error'),'provider_calls':len(responses)}))
