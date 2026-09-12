"""One admission per HTTP attempt, with no hidden retry and no raw response log."""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request

import certifi

from .ledger import GateClosed, Ledger, WaitForCapacity
from .protocol import Campaign

ENDPOINT = 'https://api.minimax.cn/v1/chat/completions'


class WireFailure(RuntimeError):
    def __init__(self, code: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)


def integer(value):
    return value if type(value) is int and value >= 0 else None


def usage_metadata(raw: dict) -> dict:
    usage = raw.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    prompt = integer(usage.get('prompt_tokens'))
    completion = integer(usage.get('completion_tokens'))
    total = integer(usage.get('total_tokens'))
    # Inconsistent totals are not authoritative enough to release reservations.
    if prompt is None or completion is None or total != prompt + completion:
        total = None
    def detail(key, name):
        obj = usage.get(key)
        return integer(obj.get(name)) if isinstance(obj, dict) else None
    return {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': total,
            'cached_tokens': detail('prompt_tokens_details', 'cached_tokens'),
            'reasoning_tokens': detail('completion_tokens_details', 'reasoning_tokens'),
            'billing_tokens': None}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect is another wire attempt and must never forward credentials.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MeteredTransport:
    def __init__(self, campaign: Campaign, ledger: Ledger, sample: str, deadline: float):
        self.campaign, self.ledger, self.sample, self.deadline = campaign, ledger, sample, deadline

    def complete(self, messages: list[dict], *, call_kind='generation') -> dict:
        c = self.campaign
        if (not isinstance(messages, list) or not messages or len(messages) > 100 or
            any(not isinstance(m, dict) or set(m) != {'role', 'content'} or
                m['role'] not in ('system', 'user', 'assistant') or not isinstance(m['content'], str)
                for m in messages)):
            raise GateClosed('only_plain_text_messages_supported')
        if call_kind not in ('generation', 'seed', 'critic', 'selector', 'repair', 'grader', 'summary', 'retrieval'):
            raise GateClosed('unknown_call_kind')
        payload = {'model': c.model, 'messages': messages, 'temperature': c.temperature,
                   'max_tokens': c.max_output_tokens, 'thinking': {'type': c.thinking},
                   'reasoning_split': True, 'stream': False}
        return self.request(payload, call_kind=call_kind)

    def request(self, payload: dict, *, call_kind='generation', fake_response=None) -> dict:
        """Meter a production JSON/tool payload without invoking SDK retries.

        Domain adapters may provide a deterministic response only in fake mode.
        Models, token ceilings and text-only restrictions remain runner-owned.
        """
        c = self.campaign
        if fake_response is not None and c.transport != 'fake':
            raise GateClosed('fake_response_forbidden_live')
        allowed = {'model', 'messages', 'temperature', 'max_tokens', 'response_format',
                   'tools', 'tool_choice', 'parallel_tool_calls', 'top_p', 'stop',
                   'thinking', 'reasoning_split', 'stream'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise GateClosed('unsupported_payload_fields')
        if payload.get('model') != c.model or type(payload.get('max_tokens')) is not int or not 0 < payload['max_tokens'] <= c.max_output_tokens:
            raise GateClosed('model_or_output_budget_mismatch')
        if call_kind not in ('generation', 'seed', 'critic', 'selector', 'repair', 'grader', 'summary', 'retrieval'):
            raise GateClosed('unknown_call_kind')
        messages = payload.get('messages')
        if not isinstance(messages, list) or not messages or len(messages) > 100:
            raise GateClosed('invalid_messages')
        for message in messages:
            if not isinstance(message, dict) or set(message) - {'role', 'content', 'name', 'tool_call_id', 'tool_calls'} or message.get('role') not in ('system', 'user', 'assistant', 'tool'):
                raise GateClosed('unsupported_message')
            content = message.get('content')
            if not (isinstance(content, str) or content is None or isinstance(content, list) and all(
                    isinstance(part, dict) and set(part) == {'type', 'text'} and part['type'] == 'text' and isinstance(part['text'], str) for part in content)):
                raise GateClosed('only_text_and_tool_messages_supported')
        payload = {**payload, 'thinking': {'type': c.thinking}, 'reasoning_split': True, 'stream': False}
        data = json.dumps(payload, ensure_ascii=False).encode()
        # Text-only envelope guard; this is not a vendor token/billing bound.
        if len(data) > c.input_reservation_tokens:
            raise GateClosed('input_envelope_exceeds_reservation')
        if c.transport == 'minimax' and not os.environ.get('K3_API_KEY', '').strip():
            raise GateClosed('missing_K3_API_KEY')
        while True:
            if time.monotonic() + c.timeout_seconds >= self.deadline:
                raise GateClosed('sample_deadline')
            try:
                wire = self.ledger.reserve(c.id, self.sample, c.input_reservation_tokens + c.max_output_tokens, c.sample_wire_limit)
                break
            except WaitForCapacity:
                time.sleep(0.1)
        start = time.monotonic()
        meta = {'call_kind': call_kind, 'image_count': 0, 'tool_count': len(payload.get('tools', [])),
                'offered_tools': [t['function']['name'] for t in payload.get('tools', []) if isinstance(t, dict) and isinstance(t.get('function'), dict) and isinstance(t['function'].get('name'), str)],
                'request_bytes': len(data), 'max_tokens': payload['max_tokens'], 'temperature': payload.get('temperature'),
                'thinking': c.thinking, 'http_status': None,
                'prompt_tokens': None, 'completion_tokens': None, 'total_tokens': None,
                'cached_tokens': None, 'reasoning_tokens': None, 'billing_tokens': None}
        settled = False
        try:
            if c.transport == 'fake':
                # Fake exercises concurrency/ledger only; it is never model evidence.
                time.sleep(0.03)
                raw = fake_response if fake_response is not None else {'model': c.model, 'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}],
                       'usage': {'prompt_tokens': 20, 'completion_tokens': 1, 'total_tokens': 21}}
            else:
                opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(
                    context=ssl.create_default_context(cafile=certifi.where())))
                req = urllib.request.Request(ENDPOINT, data=data, headers={
                    'Authorization': 'Bearer ' + os.environ['K3_API_KEY'], 'Content-Type': 'application/json'})
                with opener.open(req, timeout=c.timeout_seconds) as response:
                    meta['http_status'] = response.status
                    # Bounded response read, including separate reasoning.
                    body = response.read(8_000_001)
                    if len(body) > 8_000_000:
                        raise WireFailure('response_too_large', uncertain=True)
                    raw = json.loads(body)
                if not isinstance(raw, dict):
                    raise WireFailure('invalid_envelope', uncertain=True)
            meta.update(usage_metadata(raw))
            choices = raw.get('choices')
            finish_reason = choices[0].get('finish_reason') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            meta['finish_reason'] = finish_reason if finish_reason in ('stop', 'length', 'tool_calls', 'content_filter', 'function_call') else None
            # Persist only allowlisted scalar telemetry, never provider error bodies.
            meta['response_model'] = raw.get('model') if isinstance(raw.get('model'), str) else None
            meta['elapsed_ms'] = round((time.monotonic() - start) * 1000)
            base_response = raw.get('base_resp')
            provider_error = ('error' in raw or (isinstance(base_response, dict) and
                              base_response.get('status_code', 0) not in (0, '0')))
            self.ledger.finish(wire, meta, meta['total_tokens'], stop_reason='provider_error_envelope' if provider_error else None)
            settled = True
            if provider_error:
                raise WireFailure('provider_error_envelope')
            return raw
        except urllib.error.HTTPError as exc:
            meta.update(http_status=exc.code, elapsed_ms=round((time.monotonic() - start) * 1000))
            retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
            meta['retry_after_seconds'] = int(retry_after) if retry_after.isdigit() else None
            # Conservative halt instead of automatic capacity escalation or retry.
            stop = 'authentication' if exc.code in (401, 403) else 'provider_overload' if exc.code in (429, 529) else None
            self.ledger.finish(wire, meta, None, uncertain=exc.code >= 500, stop_reason=stop)
            raise WireFailure('http_' + str(exc.code), uncertain=exc.code >= 500) from None
        except Exception as exc:
            if settled:
                raise
            meta.update(error_class=type(exc).__name__, elapsed_ms=round((time.monotonic() - start) * 1000))
            self.ledger.finish(wire, meta, None, uncertain=True)
            raise WireFailure('transport_or_envelope', uncertain=True) from None
