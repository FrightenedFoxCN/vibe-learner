# Scene Generation Harness

Scene Setup 的关键词或长文本生成进入 `scene:scene_generation`；operation admission 存在 `harness_workflow_operations`。模型返回 `SceneTreeProposalV1`，adapter 投影为 generated projection，用户确认保存才进入 `scene_setup_states` 或 scene library。

## 输出限制

- 根层最多 8、树深最多 8、总 layer 最多 64、总 object 最多 128、总文本预算 60000。
- 每 layer 最多 8 children、16 objects、12 tags；字段长度由 `services/ai/app/models/scene.py` 的 Pydantic contract 限制。
- proposal 中禁止可复用节点引用；应用投影阶段生成 committed IDs，并校验 selected path。
- Scene model proposal、user-authored save input、committed profile 与 public API DTO 是四个边界，不能复用一个宽松 schema。

## 恢复和提交

结构错误允许一次低温 JSON repair；关键词 web search 不兼容可回退无网络生成。长结构输出为 `max(setting_max_tokens, 8192)`。adapter 再做 closed-world tree validation；失败为 generation operation failed，不修改当前 Scene。

保存阶段使用 `expected_revision` CAS，并重新执行 committed-tree validation。生成成功只证明候选 projection，不证明用户已保存。前端 Scene 限制是后端值的跨语言镜像，相关 decoder tests 必须同时覆盖。

