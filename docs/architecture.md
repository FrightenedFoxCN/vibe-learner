# Architecture Notes

## Monorepo layout

- `apps/web`: learner-facing workspace and character shell
- `services/ai`: pedagogy API, persona engine, and performance mapper
- `packages/shared`: shared payload contracts for the web client

## Boundaries

- The web app consumes structured `reply + citations + characterEvents`.
- The AI service owns persona loading, teaching orchestration, and performance mapping.
- Character rendering is an adapter on the web side so Live2D can replace the placeholder renderer later.

## v1 defaults

- Single-user, local-first deployment
- Cloud model by default, provider abstraction for local models
- Live2D/TTS deferred, but character event schema is fixed now
