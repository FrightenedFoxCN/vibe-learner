"""Content-free diagnostics for the final Planning JSON envelope."""
import json
from app.services.provider_payload import _extract_json_payload


def observe_planning_content(content):
    result = {'content_type': type(content).__name__}
    if not isinstance(content, str):
        return result
    result.update(content_characters=len(content), empty=not content.strip(),
                  starts_with_code_fence=content.lstrip().startswith('```'))
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        result.update(strict_json_object=False, json_error_offset=exc.pos)
    else:
        result['strict_json_object'] = isinstance(decoded, dict)
    try:
        _extract_json_payload(content)
    except RuntimeError as exc:
        code = str(exc)
        result['provider_object_decode'] = code if code in {
            'plan_model_invalid_json', 'plan_model_invalid_payload'} else 'unclassified_decode_error'
    else:
        result['provider_object_decode'] = 'accepted_object'
    return result
