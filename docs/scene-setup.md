# 场景编辑器（Scene Setup）

`/scene-setup` 提供从宏观世界逐级下钻到具体教室的层级场景编辑器，支持保存草稿、场景库快照、可复用节点库以及基于关键词或长文本的 AI 场景树生成。对应的 Harness 边界见 [Scene Generation Harness](harness/scene-generation.md)。

## 1. 概念结构

推荐层级链（可按需自定义）：**宏观世界 → 区域/城市群 → 校区/街区 → 建筑/楼层 → 教室**。

- **层级节点（Layer）**：描述该尺度控制的空间范围、氛围感受、从父层进入的过渡方式、子层继承的约束规则以及本层可交互物品。
- **可交互物品（Object）**：描述名称、外观或用途、交互规则与复用标签。
- **可复用节点库（Reusable Node）**：比完整场景更细粒度的复用单元——`node_type="layer"` 保存一整棵子树及其物品，`node_type="object"` 保存单个物品。插入当前选中层时会分配全新运行时 `id`，同时保留原 `reuse_id` 维持模板血缘。

## 2. 四层契约与树预算

Scene 严格隔离四个模型边界：

1. **模型提案（`scene-tree-proposal-v1`）**：仅包含内容、标签、零基 `selected_path` 与白名单内的可选可复用节点引用；禁止包含 `id`、`reuse_id`、`revision`、时间戳或 `scene_profile`。
2. **用户保存输入（`scene-committed-save-v1`）**：`PUT /scene-setup`、`POST /scene-library` 与 `PUT /scene-library/{scene_id}` 使用；`extra="forbid"`，要求非空 `scene_name` / `scene_summary`、全局唯一的应用 `id` 与 `reuse_id`、有效 `selected_layer_id` / `collapsed_layer_ids` 以及 `expected_revision`（新建传 `0`），**拒绝调用方提交 `scene_profile`**。
3. **服务端派生轮廓（`SceneProfileRecord`）**：保存时由服务端根据校验通过的场景树自动重建，随响应返回。
4. **并发控制**：保存执行行级 revision CAS，过期写入返回 `409 scene_revision_conflict`。

全树硬上限（后端 `services/ai/app/models/scene.py` 权威定义，前端解码镜像对齐）：

| 维度 | 上限 |
| --- | ---: |
| 根层数量 / 最大树深 | 8 / 8 |
| 全树总层级数 / 总物品数 | 64 / 128 |
| 单层最大子层数 / 物品数 / 标签数 | 8 / 16 / 12 |
| 聚合文本总预算 | 60,000 字符 |

## 3. 前后端字段映射与数据流

后端模型使用 `snake_case`，前端状态使用 `camelCase`：

- **Layer 核心映射**：`id`、`title`、`scope_label ↔ scopeLabel`、`summary`、`atmosphere`、`rules`、`entrance`、`tags`、`reuse_id ↔ reuseId`、`reuse_hint ↔ reuseHint`、`objects`、`children`。
- **Object 核心映射**：`id`、`name`、`description`、`interaction`、`tags`、`reuse_id ↔ reuseId`、`reuse_hint ↔ reuseHint`。
- **SceneProfile 映射**：`scene_id ↔ sceneId`、`scene_name ↔ sceneName`、`title`、`summary`、`tags`、`selected_path ↔ selectedPath`、`focus_object_names ↔ focusObjectNames`、`scene_tree ↔ sceneTree`。

完整数据流与代码归属：

```text
前端编辑态 SceneLayer[]（camelCase）
  │  提交保存（带 expected_revision）
  ▼
apps/web/lib/api/_shared.ts :: serializeSceneTree()   → snake_case JSON（不含 scene_profile）
  ▼
PUT /scene-setup  或  POST/PUT /scene-library         → 校验 SceneCommittedSaveV1 + 树上限 + 行级 CAS
  ▼
服务端落库并重建 SceneProfileRecord
  ▼
apps/web/lib/persona-scene-decode.ts :: decodeSceneSetupState / decodeSceneLibraryItem
  │  从 unknown 递归严格解码，校验 revision / ID 唯一性 / 引用完整性 / 树预算
  ▼
前端状态 SceneTreeNode[]（camelCase）
```

外部导入的 JSON 文件经 `apps/web/lib/scene-import-structure.ts`（`validateSceneImportStructure`）与 `apps/web/lib/scene-editor-model.ts`（`parseSceneImportPayload` / `normalizeSceneLayer`）统一归一化为 `camelCase` 后再进入 React 状态。HTTP 封装位于 `apps/web/lib/api/scene.ts`，页面统一通过 `apps/web/lib/data/scenes.ts` 调用；完整接口清单见 [API 参考](api-reference.md)。

## 4. 常见错误排查

| 状态码 | 典型原因 | 处理方式 |
| --- | --- | --- |
| `422` | 未归一化的 `snake_case` 层级进入状态导致 `scope_label` 序列化丢失 | 导入或读取数据时必须经过严格解码器或 `parseSceneImportPayload` |
| `422` | `scene_name` 或 `scene_summary` 为空串，或缺失 `id` / `reuse_id` | 保持非空校验，使用服务端或模型工具生成的有效 ID |
| `422` | 保存请求携带了 `scene_profile`、提案字段（`selected_path`）或重复/悬空 ID、超出树预算 | 仅提交 `scene-committed-save-v1` 允许字段，消费响应中的服务端 `scene_profile` |
| `409` | `expected_revision` 过期（`scene_revision_conflict`） | 重新读取最新场景状态后再保存 |
| `502` | 生成提案非法（`setting_model_invalid_payload`） | 不修改现有场景，调整输入或重试生成 |
