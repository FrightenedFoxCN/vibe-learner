# MiniMax-M3 质量检定 v1

2026-09-12 用户授权恢复真实模型质量工作，持续迭代，逐次记录依据并提交。
旧 QG-002 / web-strict-decode-adversarial-v1 保持不可变。本记录属于
QG-MODEL-QUALITY-001；没有完成独立人工校准前不关闭质量门。

## 实测约定

- 使用环境变量 K3_API_KEY，仅向确认的 MiniMax 官方 API 发送认证头；报告和 Git 不包含凭据。
- 使用合成教材、人物、关系、场景与历史；完整领域检定使用隔离数据库，不修改用户资料。
- 分开记录直接 prompt/provider 探针、领域 Harness admission/commit/read-back 和前端展示证据。直接探针不能证明完整 Harness 通过。
- 每项先跑至少 3 次探索样本，确认协议后扩展到至少 10 个独立案例、每例 3 次；覆盖正常、冲突指令、格式、关系 grounding、长上下文与恢复。样本数是起点，不能单独证明质量足够。
- 报告成功率的分母包含全部计划样本；上游、数据、grader、度量失败单列，不能当作候选成功。记录初次成功率和修复后成功率。
- 优化前后使用相同案例配对并交错运行，保存配置、Git revision、prompt 版本、原始 usage、延迟及具体输出问题。新发现进入开发集；另保留未用于改写 prompt 的评估集。
- Markdown 需验证 JSON 外无围栏、正文实际换行、代码块/表格/数学与 Mermaid 的渲染；人格需核对措辞、关系、称呼、角色权限与不替他人发言。机器格式检查和主智能体语义评审分别报告。

## 覆盖矩阵

| 范围 | 实测重点 | 证据要求 |
| --- | --- | --- |
| Document、逐页抽取、Section、切块 | 双语、标题噪声、顺序、引用完整性 | 真实解析结果与人工可核对的合成原文 |
| OCR、Study Unit 清洗 | 扫描识别、丢字、公式、错误合并 | 真实 OCR 和清洗；M3 只作辅助评审，不冒充 OCR 引擎 |
| Planning、六个工具、Plan revision | 目标/时间约束、引用、工具参数、修改范围 | 真实 provider + 严格 proposal + 持久化读回 |
| Persona | 关键词、文本、整体/单槽辅助、关系与称呼 | 内容提案、用户字段保护、持久化投影 |
| Scene | 关键词/文本生成、层数、空间规则 | 严格树提案与领域读回 |
| Study Chat、31 个工具 | 指令、Markdown、教学/判分、引用、人格 | 工具按能力覆盖；私有答案不进入提交前公开投影 |
| Tavern | 单人/多人、续写、锚点、人格、长历史 | 验证后提交及原始失败/恢复证据 |
| Frontend decode | 对真实生成产物严格解码和渲染 | 原基线 + 新版本案例，不修改旧基线 |

## 官方依据与待验证假设

2026-09-12 读取：

1. [API 概览](https://platform.minimax.io/docs/api-reference/api-overview)：模型 ID `MiniMax-M3`，标称上下文 1,000,000 tokens。
2. [OpenAI SDK](https://platform.minimax.io/docs/api-reference/text-openai-api)：`https://api.minimax.io/v1`；M3 默认开启 thinking，`reasoning_split` 控制是否将其与正文分离。
3. [自动缓存](https://platform.minimax.io/docs/api-reference/text-prompt-caching)：512 input tokens 起，按工具→system→messages 前缀匹配，OpenAI usage 中 `prompt_tokens_details.cached_tokens` 可观测。缓存寿命随负载调整。
4. [显式缓存](https://platform.minimax.io/docs/api-reference/anthropic-api-compatible-cache)：当前支持表未列 M3，不能直接假设 M3 支持 cache_control。

优先检验稳定工具/schema/人物前缀、动态请求后置的收益。缓存字段缺失记为未知，不能记为零命中或自行估算真实计费。比较完整历史、当前最早优先裁剪、候选有来源的记忆策略；分别统计早期约定、人物关系、近期锚点、事实召回和 P50/P95。不得通过静默提高预算或丢弃约束换取性能通过。

## 轮次 0：仓库基线

- 起始 Git revision：`26dfdf9`。
- `npm run eval:harness:pr`：退出码 0，全部 14 个既有确定性套件通过，包含 Plan revision 的 7 个案例。仅证明确定性回归，未证明真实模型质量。
- 代码观察：Tavern preflight 按最早优先逐条裁剪 transcript，persona/scene 超限则拒绝。早期事实丢失及裁剪成本需实测后判断，当前未更改生产算法。
- 国际端点认证返回 401 authorized_error；[国内官方文档](https://platform.minimaxi.com/docs/api-reference/text-openai-api) 确认 `https://api.minimax.cn/v1`。国内端点最小探针返回 200、model=MiniMax-M3、正文 OK、约 1.015 秒。后续样本均使用国内端点。

## 轮次 1：Tavern 原生传输探索

命令（从 services/ai 执行）：

```bash
PYTHONPATH=. uv run python tests/acceptance/minimax_quality_probe.py --output /tmp/minimax-tavern-baseline-v1.jsonl --repetitions 3
```

[12 个原始样本](evidence/minimax-tavern-baseline-v1.jsonl)。四个固定合成案例各三次；复用生产 RemoteTavernProvider 的 prompt、decoder 和恢复，但注入 urllib 原生 HTTP，尚未覆盖 LiteLLM、领域校验和 admission/commit。

- 12/12 一次解码成功，无恢复调用；12/12 原生正文含 think 标签，因此不是直接可解析的 JSON 对象。生产宽容提取成功与严格传输格式分别报告。
- 三条 Markdown 列表 3/3、Python 围栏 3/3；称呼案例 3/3 含阿岚。主智能体检查，未做浏览器渲染或独立人工校准。
- **确认的 grounding 失败**：role_boundary 第三次编造“上回替你回了一句‘好’，你反悔了三回”。输入没有任何历史，且人格明确禁止编造具体共同经历；解码仍成功。此样本说明 schema 通过不代表关系/记忆可靠。
- 同一回复还出现“淋了雨没擦干脑子”；对温厚人物而言可能过度冒犯，列为人格评审问题，不将主观判断伪装成确定性硬门。
- 列表第二次建议雨大时在“大树下”停留，缺少雷雨边界，列为内容质量问题。
- 下一步：对照 reasoning_split；扩展未见过的 grounding 案例，再以完整领域 Harness 验证修复结果。
- 检查：14 套确定性评测通过，Tavern provider 5 项单测通过，探针 Python 编译和 git diff --check 通过。

## 轮次 2：传输核对与事实约束候选

- [reasoning_split 对照](evidence/minimax-tavern-split-v1.jsonl)：12/12 一次解码，12/12 正文直接为 JSON。原生基线中位延迟 6195ms，对照 5719ms；顺序小样本且缓存波动明显，不能宣称统计显著性能提升。
- [生产 SDK 核对](evidence/minimax-tavern-sdk-baseline-v1.jsonl)：4/4 一次解码，4/4 正文直接为 JSON，无需额外配置。LiteLLM 已处理原生推理内容，不更改生产适配器。仍出现无依据的“刚才路上碰见一阵急雨”的具体记忆。
- [grounding-experiment-v1](evidence/minimax-tavern-grounding-candidate-v1.jsonl)：在探针中追加事实来源、不得替用户决定和温厚拒绝约束，12/12 一次解码。三次边界回复未再出现智力/精神状态嘲讽；但 relationship 第二次仍编造“皖南、四天雨、卖伞”等事件。
- **结论：暂不采用候选**。JSON 成功不等于语义问题消失；扩展无历史/缺失记忆的明确上下文及新问法后再测。未修改已注册生产 prompt，因此无生产组件版本变更。
- 当前完成 40 个 Tavern 候选样本与 2 次区域连通性请求；仍未完成所有领域的 Harness 质量检定。
