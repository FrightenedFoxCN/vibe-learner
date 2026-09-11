"""Request-local cooperative budget checks across nested synchronous callbacks."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator


_checks: ContextVar[tuple[Callable[[], None], ...]] = ContextVar("execution_budget_checks", default=())


def check_execution_budget() -> None:
    for check in _checks.get():
        check()


@contextmanager
def execution_budget_scope(check: Callable[[], None] | None) -> Iterator[None]:
    # Nested stages retain their parent's deadline; a child cannot extend it.
    token = _checks.set((*_checks.get(), check) if check is not None else _checks.get())
    try:
        yield
    finally:
        _checks.reset(token)
