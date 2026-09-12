"""Read-only native load sample with the production Tavern prompt and decoder.

Thread-safe: a fresh provider and callback per invocation; no patches, database,
commit, or mutable shared model state. This is transport capacity evidence only.
"""
import time

from app.models.domain import PersonaProfile
from app.services.provider_tavern import RemoteTavernProvider
from .common import persona, source_manifest


class ProposalRepairRequested(RuntimeError):
    pass


def run_sample(context, case, variant):
    c = context.transport.campaign
    actor = PersonaProfile(id='capacity-synthetic-persona', source='synthetic', **persona())
    issued = False
    def request(payload, *, request_kind, model):
        nonlocal issued
        if issued:
            raise ProposalRepairRequested()
        issued = True
        start = time.monotonic()
        raw = context.transport.request(payload)
        return raw, round((time.monotonic()-start)*1000)
    provider = RemoteTavernProvider(c.model, c.temperature, c.max_output_tokens, request)
    try:
        reply = provider.generate_tavern_actor_reply(persona=actor, participants=[], scene_profile=None,
            recent_messages=[], user_message=case.source+'\n'+case.request, guidance='', allowed_target_ids=[])
    except ProposalRepairRequested:
        # Only the first proposal is measured. Reject repair before any transport
        # validation/reservation, including providers that increase repair budgets.
        return {'status': 'candidate_failed', 'failure_owner': 'candidate',
                'metrics': {'strict_proposal': False},
                'scope': 'provider-proposal-only; no domain admission, commit or read-back'}
    return {'status': 'completed', 'failure_owner': None, 'metrics': {'strict_proposal': bool(reply.text)},
            'scope': 'provider-proposal-only; no domain admission, commit or read-back'}


CAPACITY_SAFE = True
