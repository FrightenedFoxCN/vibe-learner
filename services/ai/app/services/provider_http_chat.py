"""Owned, cancellable HTTP transport for compatible Chat Completions only."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Callable

from app.services.provider_cancellation import check_provider_cancellation

POLL_SECONDS = 0.25


class CompatibleChatConnectionError(ConnectionError):
    """Preserve the shared transport's bounded network-error retry policy."""


def request_compatible_chat(
    *,
    payload: dict[str, Any],
    api_base: str,
    api_key: str,
    timeout_seconds: int,
    should_continue: Callable[[], bool] | None,
) -> dict[str, Any]:
    # The caller is already the synchronous Tavern worker. Do not put an
    # uninterruptible SDK request into another executor thread and abandon it.
    check_provider_cancellation(should_continue)
    return asyncio.run(
        _request(payload, api_base, api_key, timeout_seconds, should_continue)
    )


async def _request(payload, api_base, api_key, timeout_seconds, should_continue):
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:

        async def send():
            # stream() also makes cleanup explicit for cancellation after headers
            # or while the provider is sending a partial JSON response body.
            async with client.stream(
                "POST",
                f"{api_base.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                await response.aread()
                response.raise_for_status()
                return response.json()

        task = asyncio.create_task(send())
        try:
            async with asyncio.timeout(timeout_seconds):
                while True:
                    check_provider_cancellation(should_continue)
                    done, _ = await asyncio.wait({task}, timeout=POLL_SECONDS)
                    if done:
                        check_provider_cancellation(should_continue)
                        return await task
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as exc:
            raise CompatibleChatConnectionError("provider connection failed") from exc
        finally:
            # Await cancellation and close the owned client before returning
            # control to the Tavern worker. There is no detached provider task.
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
