"""Bound POST /documents before multipart parsing, including chunked bodies."""

from __future__ import annotations

from tempfile import SpooledTemporaryFile

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.models.document_input_limits import (
    DOCUMENT_UPLOAD_MAX_BYTES,
    DOCUMENT_MULTIPART_OVERHEAD_BYTES,
    UPLOAD_READ_CHUNK_BYTES,
    DocumentInputLimitError,
)


class DocumentUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/documents"
        ):
            return await self.app(scope, receive, send)
        maximum = DOCUMENT_UPLOAD_MAX_BYTES + DOCUMENT_MULTIPART_OVERHEAD_BYTES
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0

        async def reject(actual):
            error = DocumentInputLimitError(
                "document_upload_body_too_large", limit=maximum, actual=actual
            )
            await JSONResponse({"detail": error.detail()}, status_code=413)(
                scope, receive, send
            )

        if declared > maximum:
            return await reject(declared)
        total = 0
        with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as spool:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                body = message.get("body", b"")
                total += len(body)
                if total > maximum:
                    return await reject(total)
                await run_in_threadpool(spool.write, body)
                if not message.get("more_body", False):
                    break
            await run_in_threadpool(spool.seek, 0)
            remaining = total
            ended = False

            async def replay():
                nonlocal remaining, ended
                if ended:
                    return await receive()
                body = await run_in_threadpool(spool.read, UPLOAD_READ_CHUNK_BYTES)
                remaining -= len(body)
                ended = remaining == 0
                return {"type": "http.request", "body": body, "more_body": not ended}

            await self.app(scope, replay, send)
