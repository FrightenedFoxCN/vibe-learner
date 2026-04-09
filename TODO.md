# TODO

## Now

- Wire historical learning plans into the homepage flow more cleanly so plan selection, session creation, and debug trace lookup share the same source of truth.
- Tighten OCR cleanup around exercise blocks, appendices, and review pages that still leak into plannable study units.
- Keep improving planner timeout behavior when tool calls are enabled, especially for `gemini-2.5-*` and other slower OpenAI-compatible providers.
- Make `/debug` streaming more legible by grouping parser events, model rounds, tool calls, and final artifacts in one timeline view.

## Next

- Persist study-session turns in a way that supports full history replay on the main learning page, not only in raw backend storage.
- Add stronger validation between backend snake_case payloads and frontend camelCase normalization to catch contract drift earlier.
- Expand automated tests around planning context generation, tool-call traces, and streamed learning-plan completion.
- Document the local JSON storage layout under `services/ai/data/` with examples for documents, debug records, plans, and traces.

## Later

- Add a real provider abstraction beyond the current OpenAI-compatible planner path and the mock provider.
- Introduce a formal asset manifest for persona portraits, expressions, and future Live2D-compatible renderers.
- Replace more heuristic-only parser cleanup with model-assisted reconciliation once OCR quality and cost are acceptable.
- Prepare character-event streaming for future TTS / Live2D adapters without breaking the current web placeholder renderer.
