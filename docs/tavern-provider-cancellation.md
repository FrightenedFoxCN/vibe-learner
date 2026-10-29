# Tavern provider cancellation

Tavern keeps database cancellation and local transport cancellation separate.
Cancel commits the Run/Step fence immediately. A transport that supports
cancellation then closes its local request; other transports retain the previous
bounded synchronous behavior and reject late output. Neither proves that an
upstream provider stopped computation or billing.

## Capability and routing

`TavernModelCapability.tavern_cancellation_capability()` returns an internal
`ProviderCancellationCapability`. Its fields describe supported mechanisms,
not the outcome of a particular cancellation:

| Adapter | Local transport | Provider computation/billing stop |
| --- | --- | --- |
| `compatible-chat-http-v1` | Supported for an owned asynchronous HTTP request | Unsupported/unverified |
| `litellm-sync` | Unsupported once a synchronous request is issued | Unsupported/unverified |
| Generic/custom provider default | Unsupported | Unsupported/unverified |

The production `OpenAIModelProvider` captures the adapter and endpoint at public
operation entry. The shipped SDK bundle supplies a cancellable compatible-chat
callable. Tavern selects it only when the existing model routing resolves to
the OpenAI-compatible Chat Completions protocol: an `openai/` route, an unprefixed
model on a custom compatible base URL, or an unprefixed model on the standard
OpenAI v1 base URL. Explicit other protocols such as `anthropic/`, `gemini/`,
Azure or Bedrock retain the synchronous LiteLLM path. An injected SDK without
the capability retains that fallback too.

This selection applies to Tavern actor calls only. Planning, Study Chat,
Persona/Scene, embeddings and Responses keep their existing SDK routes. Model
name/parameter adaptation, the captured Chat endpoint/key, strict actor output,
JSON Schema fallback, semantic repair and token-usage recording remain the
existing boundaries. No request key, model-owned schema or public cancellation
receipt is changed. Logs identify the chosen Tavern transport adapter.

## Local lifecycle

`provider_http_chat.py` runs one owned asyncio loop in the existing synchronous
Tavern worker. It creates an operation-call-scoped `httpx.AsyncClient` and sends
`POST <chat_base_url>/chat/completions`. It does not wrap an uninterruptible SDK
call in a second worker and abandon that worker on cancellation.

While waiting for headers or the complete JSON body, it checks the existing
claim/lease predicate every 250 ms. Actual detection also includes repository
lookup and scheduler latency; 250 ms is not a platform-wide cancellation SLA.
On cancellation it cancels and awaits the HTTP task, closes the response/client
and loop, then returns control to the worker. It checks again before accepting
a completed result. HTTP timeout covers the full request/body as well as normal
HTTPX transport timeouts; Harness call-time limits still constrain the timeout.

The shared transport does not retry `ProviderRequestCanceled`. Retry backoff is
cooperative for the supported call; schema fallback and semantic repair retain
the existing pre-call cancellation fences. Supported ordinary network/transient
failures still use the existing bounded retry policy. A canceled/incomplete
response records no invented token count or zero-cost claim; provider usage is
recorded only if a complete successful payload actually returns.

Per-call client ownership makes cleanup explicit and avoids cross-operation
socket ownership. It also forgoes a shared persistent HTTP connection pool for
this Tavern adapter. This change does not certify real-provider latency; the
separate live performance gate remains applicable.

## Durable cancellation and evidence

The Run/Step database fence wins independently of socket cleanup. A lost lease
also makes the predicate fail and stops local transport without reviving or
committing the old step. Already committed earlier actors stay committed; later
actors cannot begin after cancellation.

If generation terminates after cancellation, its real terminal v3 trace is
attached to the canceled Speaker Step through the dedicated evidence method.
The method checks the current claim count and canceled state so evidence from
a different ownership epoch cannot overwrite it. This writes evidence only;
it does not change Run/Step status, append a Message or expand the
`primary_output_only` commit policy. Repeated cancel is idempotent and recovery
of a canceled Run is query-only.

The UI continues to describe canceling receipt and explains that provider
computation/billing may continue. The cancel response is database evidence, not
a synchronous transport-cleanup acknowledgement or a provider refund receipt.

## Reproducible production-adapter check

```bash
npm run test:acceptance:tavern-transport-cancel
```

This executes five focused tests using the actual production provider adapter
and loopback HTTP peer, plus a temporary SQLite Tavern repository and the
production cancellation route. It contacts no real model service. The peer
observes socket EOF independently of the provider's return value.

- Cancel after the peer receives a request but before it sends headers.
- Cancel after headers and a partial JSON body have arrived.
- In both cases, prove one original request, socket closure, worker return and
  successful next execution in the same one-worker pool. No usage is invented
  for the canceled request.
- Cancel an actual admitted Tavern step through HTTP; check canceled status,
  terminal `not_committed` v3 trace, no actor Message, claim-fenced evidence,
  stopped lease thread, idempotent cancel, no provider replay on resume, and
  successful next operation in the same pool.
- Check compatible routing, immutable endpoint capture, parameter adaptation,
  unsupported fallback, no call for an already-canceled generation, cooperative
  backoff, schema fallback/repair and ordinary retry/error limits.

The raw [probe evidence](performance/tavern-transport-cancel-v1.json) retains
implementation digests, environment, measured worker-return times and observed
socket/commit facts. A rerun writes
`/tmp/vibe-tavern-transport-cancel.json` by default. Reported upstream computation
and billing stop remain null. These local results do not independently certify
all provider protocols, production-network behavior or every desktop platform.
