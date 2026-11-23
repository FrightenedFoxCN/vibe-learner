# Scene Generation Harness

Scene Setup 的关键词或长文本场景生成进入 `scene:scene_generation`，操作准入存于 `harness_workflow_operations`。模型提案、用户保存输入、已提交 Scene Profile 与公开 API DTO 四层严格隔离。

## 输出约束

- 严格解码为 `SceneTreeProposalV1`：根层 ≤ 8、树深 ≤ 8、总层级 ≤ 64、总物品 ≤ 128、聚合文本预算 ≤ 60,000 字符。
- 每层最多 8 个子层、16 个物品、12 个标签；字段长度以 `services/ai/app/models/scene.py` 的 Pydantic 契约为准。
- 模型提案不得携带 committed ID、revision、时间戳或未授权节点引用；应用投影阶段校验 `selected_path`、解析白名单可复用节点并分配全部 committed ID。

## 恢复与保存边界

- 结构错误允许最多 1 次低温 JSON 修复；关键词搜索在 Provider 不支持时降级为无网络生成。
- 长结构生成上限为 `max(setting_max_tokens, 8192)`。
- 适配器执行闭世界树结构校验；失败则操作终结为 `failed`，不改动当前已保存场景。
- 用户保存草稿或场景库使用 `scene-committed-save-v1` 与 `expected_revision` 行级 CAS，并由服务端重建 `SceneProfile`。详见 [场景编辑器](../scene-setup.md)。
