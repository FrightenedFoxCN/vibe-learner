from __future__ import annotations

from typing import Callable


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)



def _call_interrupt(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    callback()

