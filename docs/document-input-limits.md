# Document input limits

`document-input-limits-v1` defines fixed admission limits. Python owns enforcement
in `app.models.document_input_limits`; the browser mirror and shared JSON golden
must match it. `GET /documents/input-limits` returns the current contract without
creating a domain operation.

| Input | Maximum, inclusive | Enforcement |
| --- | ---: | --- |
| One uploaded PDF file | 64 MiB (67,108,864 bytes) | Browser selection and bounded server reads |
| Complete multipart request | 65 MiB (68,157,440 bytes) | ASGI middleware before multipart parsing |
| PDF physical pages | 512 | MuPDF metadata preflight before storage/admission and again at parser entry |
| One indivisible text unit | 65,536 Python characters | Chunk builder after paragraph/sentence splitting |

The additional 1 MiB covers multipart framing and form metadata. The request cap
applies to the complete body, including multiple parts; it is not an additional
file allowance. The middleware counts actual received bytes even without
`Content-Length` or with a misleading smaller value. A declared oversized body
is refused before reading it. Accepted bodies use a temporary spool, with at most
1 MiB kept in memory before disk rollover; it is closed on rejection, disconnect
or completion. The file reader stops at the file cap plus one byte.

These are input bounds, not a guarantee that every accepted PDF will complete
OCR or satisfy downstream Harness snapshot/time/output budgets. The existing
256-page text-PDF stress case remains a regression; 512-page metadata acceptance
does not certify scanned-PDF performance. Temporary multipart staging is not
installation-wide disk certification.

## Lossless chunk policy

The 1,400-character chunk packing target remains a target. An indivisible unit
above it and at most 65,536 characters is preserved intact, with a persisted
`oversized_text_unit_preserved` parse warning. Content is never silently truncated
to fit the target. Units above 65,536 characters fail processing with
`document_text_unit_too_large` before a final report or Document result commits.
Completed page checkpoints remain available as `checkpoint_only`; they do not
prove a committed Document. PDF handles close on success and on failure.

## Rejection and recovery

Upload limits return HTTP 413 with a structured detail:

```json
{
  "detail": {
    "contract_version": "document-input-error-v1",
    "code": "document_page_limit_exceeded",
    "message": "PDF 超过 512 个物理页，请拆分后重新上传。",
    "limit": 512,
    "actual": 513,
    "recovery_action": "split_or_reexport_pdf"
  }
}
```

Codes are `document_upload_too_large`, `document_upload_body_too_large`,
`document_page_limit_exceeded`, and `document_text_unit_too_large`. `actual` is the
observed count when available, not necessarily the full file/body size; it is
null when a terminal Harness error retains only the code. A processing stream
that has already started returns `stream_error` with a readable recovery message
and failure evidence, never a successful projection.

Upload byte/page rejection creates neither a stored upload nor a Document row.
Processing/resume rechecks legacy stored inputs before domain admission; rejected
preflight does not mutate the Document, process operation or checkpoint. Stream
request diagnostics may still record the refusal. Malformed/opaque bytes that
MuPDF cannot open retain the existing process-stage invalid-PDF failure behavior;
metadata preflight is not a new PDF format validator.

Choose a smaller/re-exported PDF and retry the upload. The browser explains
oversized selection and re-enables generation after a valid replacement. Server
page/body rejections keep CORS and request diagnostics so the same recovery text
is visible to browser clients.

## Focused verification

- `npm run test:ai:document:input-limits`: byte/page equality and overflow,
  bounded reads, no admission/storage effects on preflight rejection, retained
  text, hard-limit failure/checkpoints, actual HTTP/NDJSON recovery, and
  absent/misleading request length.
- `npm --workspace @vibe-learner/web run test:workspace:input-limits`: shared
  golden, browser size guard, transport refusal, replacement-file recovery and
  readable HTTP error.
- `cd services/ai && LITELLM_LOCAL_MODEL_COST_MAP=True UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python -m app.services.harness_stage_evals --suite chunk_building_regression`:
  six deterministic cases, including lossless oversized text and hard rejection.

These checks use local synthetic inputs and no live provider or neural OCR.
