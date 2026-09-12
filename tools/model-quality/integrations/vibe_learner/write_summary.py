"""Summary-fact instructions, with identical native-index compatibility in both arms."""
from unittest.mock import patch
from . import study
from .common import source_manifest
from .study_wire_shape import normalize_index


def run_sample(context,case,variant):
    if variant.id not in ('baseline','fact-focus'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unknown_summary_variant'}
    original=context.transport.request
    def request(payload,**kwargs):return normalize_index(original(payload,**kwargs))
    with patch.object(context.transport,'request',request):return study.run_sample(context,case,variant)
