"""ASGI completion covers streamed bodies, exceptions and cancellation."""
import asyncio
import re
import time
from uuid import uuid4

from app.core.diagnostics import correlation, active_store


class DiagnosticMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith("/diagnostics"):
            return await self.app(scope, receive, send)
        store = getattr(scope["app"].state, "diagnostics", None)
        request_id = uuid4().hex
        fields = {"request_id": request_id}
        headers = dict(scope.get("headers", []))
        for field in ("client_instance_id", "page_view_id", "flow_id", "action_id"):
            value = headers.get(("x-debug-" + field.replace("_", "-")).encode(), b"").decode("ascii", errors="ignore")
            if re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", value):
                fields[field] = value
        token = correlation.set(fields)
        store_token = active_store.set(store)
        start = time.perf_counter()
        status = None
        completed = False
        disconnected = False

        def emit(name, **extra):
            if store is not None:
                route = getattr(scope.get("route"), "path", None)
                store.emit(name, method=scope["method"], route=route, **extra)

        async def receive_observed():
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        async def send_observed(message):
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []), (b"x-request-id", request_id.encode())]}
                emit("response_headers", status_code=status)
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        emit("request_started")
        outcome = "request_failed"
        try:
            await self.app(scope, receive_observed, send_observed)
            outcome = "request_finished" if completed else ("request_cancelled" if disconnected else "request_failed")
        except asyncio.CancelledError:
            outcome = "request_cancelled"
            raise
        finally:
            emit(outcome, status_code=status, duration_ms=(time.perf_counter() - start) * 1000)
            correlation.reset(token)
            active_store.reset(store_token)
