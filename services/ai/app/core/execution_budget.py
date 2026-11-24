"""Request-local cooperative checks and call limits for Harness execution."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator


_checks: ContextVar[tuple[Callable[[], None], ...]] = ContextVar(
    "execution_budget_checks", default=()
)
_call_timeout_seconds: ContextVar[tuple[Callable[[], int], ...]] = ContextVar(
    "execution_budget_call_timeout_seconds",
    default=(),
)


def check_execution_budget() -> None:
    for check in _checks.get():
        check()


def execution_call_timeout_seconds(default: int) -> int:
    """Intersect the configured provider limit with every active Harness limit."""
    limits = [max(1, int(default))]
    limits.extend(max(1, int(resolve())) for resolve in _call_timeout_seconds.get())
    return min(limits)


@contextmanager
def execution_budget_scope(
    check: Callable[[], None] | None,
    *,
    call_timeout_seconds: Callable[[], int] | None = None,
) -> Iterator[None]:
    # Nested stages retain their parent's deadline; a child cannot extend it.
    check_token = _checks.set(
        (*_checks.get(), check) if check is not None else _checks.get()
    )
    timeout_token = _call_timeout_seconds.set(
        (*_call_timeout_seconds.get(), call_timeout_seconds)
        if call_timeout_seconds is not None
        else _call_timeout_seconds.get()
    )
    try:
        yield
    finally:
        _call_timeout_seconds.reset(timeout_token)
        _checks.reset(check_token)
