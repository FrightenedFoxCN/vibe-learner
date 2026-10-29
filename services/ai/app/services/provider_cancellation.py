"""Cancellation means local transport cleanup, never provider/billing rollback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class ProviderCancellationCapability:
    adapter: Literal["compatible-chat-http-v1", "litellm-sync", "unsupported"]
    local_transport: bool = False
    upstream_execution: bool = False
    upstream_billing: bool = False


class ProviderRequestCanceled(RuntimeError):
    def __init__(self) -> None:
        super().__init__("tavern_actor_generation_canceled")


def check_provider_cancellation(should_continue: Callable[[], bool] | None) -> None:
    if should_continue is not None and not should_continue():
        raise ProviderRequestCanceled()
