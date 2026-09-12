"""Pure observation-window controller. The ledger persists every decision."""
import math


def observe(state: dict, policy: dict, wires: list[dict], now: float, backlog: int) -> tuple[dict, str | None]:
    state = dict(state)
    if now < state['cooldown_until'] or now - state['window_started'] < policy['window_seconds']:
        return state, None
    window = [w for w in wires if w['finished'] is not None and w['finished'] > state['window_started']]
    if len(window) < policy['min_completed']:
        return state, None
    errors = sum(w['state'] == 'uncertain' or (w['metadata'] or {}).get('http_status') not in (None, 200)
                 or (w['metadata'] or {}).get('error_class') is not None for w in window)
    latencies = sorted((w['metadata'] or {}).get('elapsed_ms', 0) for w in window)
    p95 = latencies[math.ceil(len(latencies) * .95) - 1]
    unknown = any((w['metadata'] or {}).get('total_tokens') is None for w in window)
    rate = errors / len(window)
    state.update(window_started=now, last_window={'completed': len(window), 'error_rate': rate, 'p95_ms': p95, 'unknown_usage': unknown})
    if rate > policy['max_error_rate']:
        state['bad_windows'] += 1
        state['healthy_windows'] = 0
        state['current'] = max(policy['min_concurrency'], state['current'] // 2)
        state['rate_factor'] = max(.125, state['rate_factor'] / 2)
        return state, 'infrastructure_pause' if state['bad_windows'] >= 2 else 'infrastructure_down'
    state['bad_windows'] = 0
    if state['baseline_p95_ms'] is None and not errors and not unknown:
        state['baseline_p95_ms'] = max(1, p95)
    if state['baseline_p95_ms'] and p95 > state['baseline_p95_ms'] * policy['p95_multiplier']:
        state['healthy_windows'] = 0
        state['current'] = max(policy['min_concurrency'], state['current'] // 2)
        state['rate_factor'] = max(.125, state['rate_factor'] / 2)
        return state, 'latency_down'
    if errors or unknown:
        state['healthy_windows'] = 0
        return state, 'hold_incomplete_evidence'
    state['healthy_windows'] += 1
    if state['healthy_windows'] >= policy['healthy_windows'] and backlog > state['current']:
        at_capacity = state['current'] == policy['max_concurrency'] and state['rate_factor'] == 1.
        state['current'] = min(policy['max_concurrency'], state['current'] * 2)
        state['rate_factor'] = min(1., state['rate_factor'] * 2)
        state['healthy_windows'] = 0
        return state, 'at_capacity' if at_capacity else 'healthy_up'
    return state, 'healthy_hold'
