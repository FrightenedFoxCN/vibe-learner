# Scene Setup

This page defines the layered environment editor used by `/scene-setup`.

## Goal

- Build a scene from world scale down to a specific classroom.
- Let each layer carry its own summary, atmosphere, entry transition, and local rules.
- Add interactive objects to any layer so the scene can be queried or staged later.

## Recommended Layer Chain

- World overall
- Region or city cluster
- District or campus block
- Building or floor
- Classroom

## Layer Content

Each layer should describe:

- what this scale controls
- what it feels like
- how the user enters it from the parent layer
- which objects are interactive in this scope
- what constraints apply to children

## Object Content

Interactive objects should usually include:

- name
- short appearance or purpose note
- interaction rule
- tags for later search or reuse