# 页面命名与术语

由原 `AGENTS.md` 迁出。改前端或讨论页面结构时按需阅读；AGENTS.md 只保留“必须按这套名字”的规则。

Use the following standard names when discussing frontend pages and page blocks. Avoid vague terms such as "that panel on the left" when a stable block name exists.

### Page Names

- `/` = `Navigation Home`
- `/plan` = `Plan Workspace`
- `/study` = `Study Dialog`
- `/persona-spectrum` = `Persona Spectrum`
- `/scene-setup` = `Scene Setup`
- `/tavern` = `Tavern Workspace` (frontend and backend active)
- Debug is a global overlay, not a standalone page.

### `Tavern Workspace` Block Names

- `Tavern Header`: page title, active room title, create action, and status.
- `Tavern Session Panel`: recent rooms and room switching. Archive/restore is currently in `Tavern Header`; broader room management remains backlog work.
- `Tavern Setup Panel`: persona multi-select, optional scene, title, and room creation.
- `Tavern Conversation Panel`: ordered user/director/persona/system transcript.
- `Participant Roster`: cast, target selection, and per-persona generation state.
- `Interaction Composer`: visible message, optional next-round guidance, recipient preview, and send/stop actions.
- `Reliability Details`: collapsed user-readable Harness recovery summary; raw trace belongs in debug UI.

### `Learning Workspace` Block Names

- `Hero Header`: the top banner area in `apps/web/components/learning-workspace.tsx` with product title, status notice, and debug link.
- `Persona Selector`: the persona dropdown block rendered by `apps/web/components/persona-selector.tsx`.
- `Study Column`: the main left-column flow container on the home page.
- `Document Setup Panel`: the upload-and-generate block rendered by `apps/web/components/document-setup.tsx`.
- `Plan History Panel`: the historical plan selection block rendered by `apps/web/components/plan-history.tsx`.
- `Plan Overview Panel`: the current plan summary block inside `LearningWorkspace`, showing overview, main themes, and today tasks.
- `Study Console`: the chapter chat/request block rendered by `apps/web/components/study-console.tsx`.
- `Character Shell`: the right-column teacher/persona block rendered by `apps/web/components/character-shell.tsx`.
- `Character Event Snapshot`: the JSON event preview area inside `Character Shell`.

### `Document Debug Console` Block Names

- `Debug Hero Header`: the top banner with page title, current status message, and back link.
- `Document List Sidebar`: the left-side document picker.
- `Parse Summary Card`: the summary block titled `解析摘要`.
- `Process Stream Panel`: the block titled `流式处理反馈`.
- `Plan Stream Panel`: the block titled `流式生成学习计划`.
- `Section Guess Panel`: the block titled `章节猜测`.
- `Study Unit Cleanup Panel`: the block titled `学习编排清洗结果`.
- `Planning Outline Panel`: the block titled `计划输入目录`.
- `Planning Tools Panel`: the block titled `计划工具与章节详情`.
- `Planning Trace Panel`: the block titled `计划模型 Trace`.
- `Parse Warning Panel`: the block titled `解析告警`.
- `Chunk Inspector Panel`: the block titled `切块结果`.
- `Page Extraction Panel`: the block titled `逐页抽取`.

### Naming Rules

- Use `Panel` for standalone content cards inside a page.
- Use `Header` for the top banner area of a page.
- Use `Sidebar` only for the document picker inside the global `Document Debug Console` overlay.
- Use `Shell` only for the persona/character container, not for ordinary study cards.
- Use `Study Unit` for cleaned planning units, not `section`, unless referring to raw parser-detected `sections`.
- Use `Section` for raw parse structure or cited textbook structure.

### Data-Term Mapping

- `Document`: uploaded textbook file plus derived processing status.
- `Section`: raw parser-detected chapter/subchapter structure in debug artifacts.
- `Study Unit`: cleaned planning unit derived from sections and OCR text cleanup.
- `Learning Plan`: persisted planner output.
- `Study Session`: interactive tutor session bound to one document, persona, and active section.
- `Character Event`: structured performance instruction consumed by the character layer.
- `Tavern Room`: durable free-interaction container with an optional scene and persona snapshots.
- `Tavern Participant`: room-scoped immutable persona snapshot plus prompt hash.
- `Tavern Message`: append-only attributed message with a monotonic room sequence.
- `Tavern Run`: idempotent, revision-checked generation attempt with a server-owned schedule, normalized speaker steps, context digest, and Harness traces.
- `Tavern Speaker Step`: one scheduled persona attempt with pending/generating/completed/failed/blocked state and a reply anchor.
- `Harness Trace`: workflow-neutral validate/repair evidence; it applies across parsing, planning, generation, study, Tavern, and frontend decoding.
