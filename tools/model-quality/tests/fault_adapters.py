"""Only used by provider-free process recovery regressions."""
import os
import time


def crash_after_reserve(context, case, variant):
    transport = context.transport
    transport.ledger.reserve(transport.campaign.id, transport.sample, 100)
    os._exit(17)


def hang(context, case, variant):
    time.sleep(60)


def invalid_metric(context, case, variant):
    return {'status': 'completed', 'metrics': {'score': float('nan')}}


def raise_after_reserve(context, case, variant):
    transport = context.transport
    transport.ledger.reserve(transport.campaign.id, transport.sample, 100)
    raise RuntimeError('synthetic adapter failure')
