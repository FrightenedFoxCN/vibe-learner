# Persona Spectrum

This document defines the data chain and interface contract used by the `/persona-spectrum` page.

## Goal

- Configure persona profile fields.
- Maintain editable persona settings, including background story.
- Preview persona behavior in chapter-linked study chat sessions.
- Provide template snippets and AI-assisted setting refinement.
- Surface explicit interaction state (emotion/action/speech) in preview.

## Frontend Data Flow

1. Load persona list and document list in parallel.
2. Select one persona as editable draft source.
3. Create or update persona via API.
4. Load persona assets for renderer metadata display.
5. Create or reuse study session and send preview chat messages.

## API Chain

### `GET /personas`

- Purpose: list available personas.
- Used by: persona selector and draft initialization.

### `POST /personas`

- Purpose: create a new persona record.
- Required body fields:
  - `name`
  - `summary`
  - `system_prompt`
  - `teaching_style`
  - `narrative_mode`
  - `encouragement_style`
  - `correction_style`
- Optional body fields:
  - `background_story`
  - `available_emotions`
  - `available_actions`
  - `default_speech_style`

### `PATCH /personas/{persona_id}`

- Purpose: update existing persona settings in place.
- Request body shape is the same as `POST /personas`.
- Returns updated `PersonaProfile`.
- Builtin personas are readonly and return `403` (`persona_readonly_builtin`).

### `POST /personas/assist-setting`

- Purpose: generate a draft refinement for `background_story` and `system_prompt`.
- Used by: `人工智能辅助完善设定` action in Persona Spectrum page.

### `GET /personas/{persona_id}/assets`

- Purpose: fetch renderer metadata and asset manifest.
- Used by: Persona Spectrum preview card.

### `GET /documents`

- Purpose: provide document and section/study-unit options for live preview routing.

### `POST /study-sessions`

- Purpose: create chapter-linked study session used for preview messages.

### `POST /study-sessions/{session_id}/chat`

- Purpose: request real chat response and character events under selected persona and section.

## Scene Layer Split

The layered scene editor moved to `/scene-setup`.

- Use it to define the macro world, regional layers, campus layers, and the final classroom.
- Put interactive objects and local rules in the layer they belong to.
- Keep persona drafting focused on who the teacher is and how they speak, not on the room they stand in.

## Persona Setting: Background Story

`background_story` is intended for narrative identity and role flavor.

- Typical content:
  - origin and growth background
  - teaching beliefs
  - speaking quirks and catchphrases
  - interaction tone boundaries
- Non-goal:
  - replacing chapter-grounded teaching constraints
  - storing learner private notes

## Setting Templates

Background story editor includes one-click snippet templates for:

- world origin
- teaching method
- tone and catchphrases
- interaction boundaries
