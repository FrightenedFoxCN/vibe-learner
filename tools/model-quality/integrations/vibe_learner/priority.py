"""Mix three ready lanes in one bounded process scheduler and shared wire gate."""
from .common import source_manifest
from . import citation,temporal,write_binding


def run_sample(context,case,variant):
    lanes={'citation':(citation,'normalized'),'temporal':(temporal,'oracle-context'),'verbatim':(write_binding,'source-binding')}
    if case.lane not in lanes or variant.id not in ('baseline','candidate'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unsupported_priority_lane'}
    module,candidate=lanes[case.lane]
    selected=variant.model_copy(update={'id':candidate if variant.id=='candidate' else 'baseline'})
    return module.run_sample(context,case,selected)
