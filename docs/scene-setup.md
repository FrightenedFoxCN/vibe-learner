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

---

## Frontend–Backend Interface

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scene-setup` | Load saved draft state (returns empty defaults if none) |
| PUT | `/scene-setup` | Save / auto-sync draft state |
| GET | `/scene-library` | List all saved scenes |
| GET | `/scene-library/{scene_id}` | Get a single saved scene |
| POST | `/scene-library` | Create a new saved scene |
| PUT | `/scene-library/{scene_id}` | Update an existing saved scene |
| DELETE | `/scene-library/{scene_id}` | Delete a saved scene |

### Request Payloads

**PUT `/scene-setup`** and **POST/PUT `/scene-library`** both use the same field structure:

```json
{
  "scene_name": "高一物理-力学基础",
  "scene_summary": "从世界整体出发...",
  "scene_layers": [ /* SceneLayerStateRecord[] */ ],
  "selected_layer_id": "scene-classroom",
  "collapsed_layer_ids": [],
  "scene_profile": { /* SceneProfileRecord | null */ }
}
```

`scene_name` and `scene_summary` both have `min_length=1` (non-empty required). Sending an empty string produces a **422**.

### SceneLayerStateRecord (Python ↔ TypeScript)

Python backend (`SceneLayerStateRecord`) uses **snake_case**. TypeScript frontend (`SceneLayer` / `SceneTreeNode`) uses **camelCase**.

| Python field | TypeScript field | Notes |
|---|---|---|
| `id` | `id` | Unique layer ID |
| `title` | `title` | Display name |
| `scope_label` | `scopeLabel` | e.g. "宏观世界", "城市层" |
| `summary` | `summary` | Layer purpose text |
| `atmosphere` | `atmosphere` | Sensory / mood text |
| `rules` | `rules` | Constraints that children inherit |
| `entrance` | `entrance` | Transition description from parent |
| `objects` | `objects` | `SceneObjectStateRecord[]` |
| `children` | `children` | Recursive `SceneLayerStateRecord[]` |

**All string fields are required (no default)**; omitting any one causes a 422.

### SceneObjectStateRecord

| Python field | TypeScript field |
|---|---|
| `id` | `id` |
| `name` | `name` |
| `description` | `description` |
| `interaction` | `interaction` |
| `tags` | `tags` (default `""`) |

### SceneProfileRecord

| Python field | TypeScript field |
|---|---|
| `scene_id` | `sceneId` |
| `scene_name` | `sceneName` |
| `title` | `title` |
| `summary` | `summary` |
| `tags` | `tags` |
| `selected_path` | `selectedPath` |
| `focus_object_names` | `focusObjectNames` |
| `scene_tree` | `sceneTree` (same `SceneLayerStateRecord[]` shape) |

### Serialization Functions (TypeScript → Python)

Located in [apps/web/lib/api.ts](../apps/web/lib/api.ts):

- **`serializeSceneTree(nodes)`** — recursively converts `SceneTreeNode[]` to snake_case objects for the API. Converts `scopeLabel` → `scope_label`. If any `SceneLayer` in React state was not normalized (still has snake_case fields), `node.scopeLabel` would be `undefined`, which `JSON.stringify` silently omits, causing a **422** on `scope_label`.
- **`serializeSceneProfile(sceneProfile)`** — converts `SceneProfile` to snake_case for the API.

### Deserialization Functions (Python → TypeScript)

Located in [apps/web/lib/api.ts](../apps/web/lib/api.ts):

- **`normalizeSceneTreeNode(node)`** — converts a raw snake_case API layer to a `SceneTreeNode`. Correctly maps `scope_label` → `scopeLabel` and recurses into `children`.
- **`normalizeSceneProfile(scene)`** — converts raw API `scene_profile` to `SceneProfile`.
- **`normalizeSceneSetupState(payload)`** — converts `GET /scene-setup` response. Note: `sceneLayers` is passed through as raw API objects; the page normalizes them via `parseSceneImportPayload`.
- **`normalizeSceneLibraryItem(payload)`** — converts a library item. `sceneLayers` is also raw; the page must normalize before using.

### Page-Level Normalization (page.tsx)

Located in [apps/web/app/scene-setup/page.tsx](../apps/web/app/scene-setup/page.tsx):

- **`parseSceneImportPayload(input)`** — entry point for all layer data entering React state. Handles both camelCase (localStorage, JSON export) and snake_case (API response) container keys. Calls `normalizeSceneLayer` on each layer.
- **`normalizeSceneLayer(input)`** — converts a raw layer object to the page-local `SceneLayer` type. Accepts both `scopeLabel` (camelCase) and `scope_label` (snake_case) via fallback.

**Critical invariant**: all `SceneLayer[]` values stored in React state must pass through `normalizeSceneLayer` (or `parseSceneImportPayload`) before being set. Raw API snake_case objects must never be placed directly into state, as `serializeSceneTree` will produce malformed JSON.

### Data Flow Summary

```
[Page renders / edits]
  ↓
SceneLayer[] in React state  (camelCase, always via normalizeSceneLayer)
  ↓  auto-save / save button
serializeSceneTree()
  ↓  snake_case JSON
PUT /scene-setup  or  POST/PUT /scene-library
  ↓  Pydantic validates SceneLayerStateRecord[]
SceneSetupStateRecord / SceneLibraryRecord saved

[Page hydrates]
GET /scene-setup  or  GET /scene-library
  ↓  snake_case JSON
normalizeSceneSetupState / normalizeSceneLibraryItem  (raw layers)
  ↓
parseSceneImportPayload → normalizeSceneLayer  (camelCase, in React state)
```

### Known 422 Causes

1. **`scope_label` missing** — raw API snake_case layer objects set into React state without normalization. `serializeSceneTree` writes `scope_label: undefined`, which `JSON.stringify` omits. Pydantic rejects the missing required field.  
   *Fix*: always pass loaded layers through `parseSceneImportPayload` before `setSceneLayers`.

2. **Empty `scene_name` or `scene_summary`** — both fields have `min_length=1`. The frontend guards against this before sending, but callers must not bypass the guard.
