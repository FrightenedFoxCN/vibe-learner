"""Wire envelopes for injected provider requests."""
import json


def setting_wire_reply(payload, *, responses=False):
    content = json.dumps(payload, ensure_ascii=False)
    return ({"output_text": content} if responses else {"choices": [{"message": {"content": content}}]}, 1)
