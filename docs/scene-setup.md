# Scene Setup

This page defines the layered environment editor used by `/scene-setup`.

## Goal

- Build a scene from world scale down to a specific classroom.
- Let each layer carry its own summary, atmosphere, entry transition, and local rules.
- Add interactive objects to any layer so the scene can be queried or staged later.
- Support generating a scene tree from keyword search or long-form setting text.
- Ensure every layer and object carries explicit reuse metadata for later recombination.

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
| POST | `/scene-setup/generate` | Generate a reusable scene tree from keywords or long text |
| GET | `/reusable-scene-nodes` | List reusable layer/object nodes |
| POST | `/reusable-scene-nodes` | Save one layer or object into the reusable node library |
| DELETE | `/reusable-scene-nodes/{node_id}` | Delete a reusable node |

### Request Payloads

**PUT `/scene-setup`** and **POST/PUT `/scene-library`** use the strict `scene-committed-save-v1` field structure:

```json
{
  "contract_version": "scene-committed-save-v1",
  "expected_revision": 7,
  "scene_name": "高一物理-力学基础",
  "scene_summary": "从世界整体出发...",
  "scene_layers": [ /* SceneLayerCommittedInputV1[] */ ],
  "selected_layer_id": "scene-classroom",
  "collapsed_layer_ids": []
}
```

`scene_name` and `scene_summary` both have `min_length=1` (non-empty required). Sending an empty string produces a **422**. Create requests use `expected_revision=0`; update requests send the revision returned by the last successful read/write. The server rebuilds `scene_profile` from the validated tree and never accepts a caller-authored profile. A stale update returns **409** `scene_revision_conflict` instead of overwriting a newer editor.

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
| `tags` | `tags` | Search and reuse tags for this node |
| `reuse_id` | `reuseId` | Stable reusable-node identifier |
| `reuse_hint` | `reuseHint` | How this node should be reused later |
| `objects` | `objects` | `SceneObjectStateRecord[]` |
| `children` | `children` | Recursive `SceneLayerStateRecord[]` |

Committed layer identity/content fields and `reuse_id` are required. `tags` and `reuse_hint` may be omitted and default to empty strings. The full tree is additionally bounded to depth 8, 64 layers, 128 objects, 8 children per layer, 16 objects per layer, and a 60,000-character aggregate text budget.

### SceneObjectStateRecord

| Python field | TypeScript field |
|---|---|
| `id` | `id` |
| `name` | `name` |
| `description` | `description` |
| `interaction` | `interaction` |
| `tags` | `tags` (default `""`) |
| `reuse_id` | `reuseId` |
| `reuse_hint` | `reuseHint` |

### Scene Tree Generation

`POST /scene-setup/generate`

```json
{
  "mode": "keywords",
  "input_text": "赛博校园, 物理实验, 夜间自习",
  "layer_count": 5
}
```

- `mode` supports `keywords` and `long_text`.
- Keywords mode may use web search when the runtime setting model allows it.
- The response returns `scene_name`, `scene_summary`, `selected_layer_id`, and `scene_layers`.
- Returned nodes are expected to already contain `tags`, `reuse_id`, and `reuse_hint`.

### Reusable Node Library

Reusable nodes are a smaller-granularity library than the full scene library.

- `node_type="layer"` stores one `SceneLayerStateRecord`, including all nested children and objects.
- `node_type="object"` stores one `SceneObjectStateRecord`.
- The frontend inserts a saved layer as a child of the currently selected layer.
- The frontend inserts a saved object into the currently selected layer's object list.
- Inserted copies receive fresh runtime `id`s, but preserve `reuse_id` so the semantic template identity survives cloning.

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
- Scene saves deliberately do not serialize a caller Scene Profile; the response profile is application-owned committed state.

### Deserialization Functions (Python → TypeScript)

Located in [apps/web/lib/api.ts](../apps/web/lib/api.ts):

- **`decodeSceneSetupState(payload)`** and **`decodeSceneLibraryItem(payload)`** consume `unknown`, recursively decode snake_case layers into `SceneTreeNode`, and validate revision, committed-ID uniqueness, selected/collapsed references, profile/tree consistency, and depth/count/text budgets.
- List and reusable-node decoders also enforce unique aggregate identity and discriminated layer/object projections.

### Page-Level Normalization (page.tsx)

Located in [apps/web/app/scene-setup/page.tsx](../apps/web/app/scene-setup/page.tsx):

- **`parseSceneImportPayload(input)`** — entry point for imported/generated/library layer data entering React state. Handles both camelCase (localStorage, JSON export) and snake_case compatibility containers. Calls `normalizeSceneLayer` on each layer.
- **`normalizeSceneLayer(input)`** — converts a raw layer object to the page-local `SceneLayer` type. Accepts both `scopeLabel` (camelCase) and `scope_label` (snake_case) via fallback.

**Critical invariant**: all untyped or imported `SceneLayer[]` values must pass through the strict API decoder or `normalizeSceneLayer` / `parseSceneImportPayload` before being set. A raw snake_case object placed directly into state makes `serializeSceneTree` produce malformed JSON.

### Data Flow Summary

```
[Page renders / edits]
  ↓
SceneLayer[] in React state  (camelCase)
  ↓  auto-save / save button with expected_revision
serializeSceneTree()
  ↓  snake_case JSON
PUT /scene-setup  or  POST/PUT /scene-library
  ↓  strict SceneCommittedSaveV1 + tree invariants + row CAS
SceneSetupStateRecord / SceneLibraryRecord saved; Scene Profile rebuilt server-side

[Page hydrates]
GET /scene-setup  or  GET /scene-library
  ↓  snake_case JSON
decodeSceneSetupState / decodeSceneLibraryItem
  ↓  strict recursive decode to camelCase
SceneTreeNode[] in React state
```

### Known 422 Causes

1. **`scope_label` missing** — an imported or untyped snake_case layer was placed into React state without normalization. `serializeSceneTree` writes `scope_label: undefined`, which `JSON.stringify` omits. Pydantic rejects the missing required field.
   *Fix*: consume API results through the strict decoder and pass imported JSON through `parseSceneImportPayload` before `setSceneLayers`.

2. **Empty `scene_name` or `scene_summary`** — both fields have `min_length=1`. The frontend guards against this before sending, but callers must not bypass the guard.

3. **Caller sends `scene_profile`, duplicate IDs, or dangling selected/collapsed IDs** — the committed-save DTO is `extra="forbid"` and tree invariants fail closed. Send only committed tree fields; consume the server-built profile from the response.

4. **Stale `expected_revision`** — this is a **409** conflict, not a 422. Reload the current Scene projection before applying a deliberate retry.
