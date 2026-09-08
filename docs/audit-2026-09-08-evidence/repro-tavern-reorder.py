import logging
logging.disable(logging.CRITICAL)
from tests.test_tavern_api import TavernApiTests
from app.models.api import CreatePersonaRequest
from app.models.tavern import build_tavern_persona_message_committed_projection
case = TavernApiTests()
case.setUp()
try:
    b = case.persona_engine.create_persona(CreatePersonaRequest(name='Second', summary='Independent review', relationship='friend', learner_address='you', system_prompt='Respond naturally', slots=[]))
    ids = [case.persona.id, b.id]
    room = case.client.post('/tavern/rooms', json={'title':'Review', 'persona_ids':ids,'opening_prompt':'','idempotency_key':'review-create-123456'}).json()['room']
    url = '/tavern/rooms/' + room['id']
    turn = case.client.post(url+'/turns', json={'input':{'kind':'user_message','content':'Hello'},'mode':'facilitated','target_persona_ids':ids,'idempotency_key':'review-turn-123456','expected_room_revision':0})
    print('turn', turn.status_code)
    assert turn.status_code == 200, turn.text
    message_id = turn.json()['generated_messages'][0]['id']
    def verify():
        m,r,s,p,a = case.repository.get_actor_commit_read_back(message_id=message_id)
        return build_tavern_persona_message_committed_projection(message=m,run=r,step=s,participants=p,reply_anchor=a)
    verify()
    print('before reorder: commit projection valid')
    changed = case.client.patch(url, json={'persona_ids':ids[::-1], 'expected_revision':1})
    print('reorder', changed.status_code)
    try:
        verify()
        print('after reorder: commit projection valid')
    except Exception as e:
        print('after reorder:', type(e).__name__, str(e))
finally:
    case.tearDown()
