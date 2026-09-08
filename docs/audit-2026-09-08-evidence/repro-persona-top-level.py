import logging
logging.disable(logging.CRITICAL)
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app.services.model_provider import OpenAIModelProvider
from app.services.local_store import LocalJsonStore
from app.services.harness_broad_adoption import HarnessProposalRuntimeService, PersonaGenerationInputManifest, PersonaGenerationProposalV1
p=OpenAIModelProvider(api_key='test',base_url='http://127.0.0.1:9/v1',plan_model='test',setting_model='test')
raw={'summary': {'bad':True}, 'relationship':['bad'], 'learner_address':77, 'cards':[{'title':'Valid','kind':'custom','label':'Valid','content':'Valid','tags':[],'source_note':''}]}
with patch.object(p,'_request_setting_json_chat',return_value=raw):
    output=p.generate_persona_cards_from_text(text='test',count=1)
proposal=PersonaGenerationProposalV1.model_validate({'request_kind':'card_batch',**output},strict=True)
with TemporaryDirectory() as d:
    store=LocalJsonStore(Path(d))
    try:
        h=HarnessProposalRuntimeService.from_database(store.database)
        out,trace=h.run_persona(manifest=PersonaGenerationInputManifest(request_kind='card_batch',mode='long_text',requested_count=1,input_char_count=4),protected_input={'input_text':'test'},generate=lambda _:proposal)
        print({'trace':trace.status.value,'summary':out.summary,'relationship':out.relationship,'learner_address':out.learner_address})
    finally:
        store.close()
