# Planning and Study output language

Plan Workspace has an explicit output-language field, including common languages
and a custom language tag such as `fr-CA`. The selection is saved with the plan
setup draft; generating a plan persists it in `planning_intent.output_language`.
It composes with physical PDF page ranges, including the checkpoint-to-planning
continuation. It does not modify the learner's objective or source material.

## Automatic and explicit behavior

Planning `auto` maps to the existing intent `{status: "unknown", value: null}`.
The planner chooses the goal's language first, then the textbook's main language,
then the Persona language, and records its resolved `output_language`. The Chinese
product interface is not a language signal. An explicit code maps to
`{status: "user_explicit", value: "fr"}` and remains an application constraint in
the existing operation fingerprint and read-back. The planner cannot replace it.

Guidance, explanations, tasks, questions and feedback should consistently use
the selected language. Quoted textbook content, source excerpts, proper names,
formulas and symbols remain verbatim. Persona controls delivery/style rather
than overriding the selected language. Plan revisions also keep the bound plan's
language policy; changing output language is a typed application input, not a
request for the model to infer a new hard constraint from revision prose.

Study Session creation defaults to the bound plan's explicit or resolved language.
The Study Dialog output-language field can override it for the next learner
message. A successful reply atomically saves that choice with the Session/Turn;
following messages, automatic continuations, re-entering the page and server
restart retain it. Failed or uncertain replies leave the previous committed
Session preference unchanged. `auto` in Study inherits a resolved plan language;
without one, it follows the learner's current goal/message, textbook, then Persona.

## Input and persistence boundaries

- Planning reuses `PlanningIntentV1`; language and physical page constraints
  are submitted together rather than placed in free-text instructions.
- Study JSON chat and multipart attachment chat both accept optional
  `output_language`. Omission keeps the Session preference. An explicit `auto`
  resets to automatic policy; an explicit language overrides it.
- `study-chat-request-v3` binds a present language value in the canonical
  request payload/fingerprint. Reusing a client request ID with another language
  fails with the same request-mismatch rule as other changed input.
- The v1 fingerprint algorithm is unchanged. An absent/null language field is
  omitted from serialization, preserving historical v1/v2 fingerprint bytes.
  Legacy request schemas cannot claim the new explicit input. Request-v2
  attachment read-back still verifies staged paths and file hashes.
- `StudySessionRecord.output_language` is application-owned JSON state, excluded
  when absent on historical rows. Creation defaults and a committed chat update
  it through repository row CAS. No SQL schema migration is needed.
- The repository verifies explicit language against both the admitted request
  and the archived committed response. The historical Turn-primary Harness
  projection remains unchanged; this does not expand its effect proof.
- `StudyChatInputManifest@v2` reviews a content-free language tag for trace-safe
  input evidence. Protected snapshot v3 stores the committed Session separately
  from the operation's proposed language. Snapshot v1/v2 remain readable.
- The preference never enters the model-owned Study reply schema. The browser
  strictly decodes persisted Session language and never treats a generated text
  declaration as proof that a setting was saved.

Tags are bounded to 35 ASCII characters and a BCP-47-style syntax. `unknown` is
not a user preference; Planning uses the existing unknown-intent representation
for automatic choice. The syntax check does not claim IANA registry validation.

## Local mock and model-quality scope

The offline mock uses deterministic templates for the language choices shown in
the field: Chinese (simplified/traditional), English, French, German, Spanish,
Japanese, Korean, Portuguese, Italian, Russian and Arabic. Regional tags use
their base language template. Its automatic choice is a small script/keyword
heuristic, not language-detection certification. Unsupported custom mock tags
return a recoverable refusal without a committed reply; configured model
providers receive the typed language policy instead.

The reviewed production prompts are Planning v8, Study Chat v3 and Plan Revision
v2. The Study pilot baseline for prompt v3 uses the existing deterministic
fixtures; prompt-v1/v2 baseline directories remain immutable. These are routing,
decoder and persistence checks, not independent linguistic/model-quality proof.
Live-provider quality conclusions are outside this document; it only defines output-language behavior.

## Focused checks

- `npm run test:ai:output-language`: historical fingerprint parity, changed-input
  rejection, French plan/session inheritance, mock language output, commit/failure
  behavior and HTTP read-back after restart.
- `npm --workspace @vibe-learner/web run test:workspace:output-language`:
  selection, custom-tag validation, draft restoration, Session switching and
  JSON/multipart transport.
- `npm --workspace @vibe-learner/web run test:workspace:output-language:browser`:
  real temporary SQLite/mock backend with the dev frontend; French generation,
  reload/navigation, inherited Study replies, English override, hydration errors
  and language-control hit testing. It starts no live provider or production build.

The existing plan-generation, Study-message recovery, operation/effect and
contract gates cover the changed boundaries. Full release checks remain separate.
