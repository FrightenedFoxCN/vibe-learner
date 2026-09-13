# M3 Planning intent 本地修复复核（2026-09-13）

## 判定

本轮已在隔离分支 `codex/planning-intent-skeleton` 修复旧 smoke 报告中可由应用边界阻断的问题，但尚未获得针对法文教材指定页段发往 MiniMax 的具体授权，因此**不把本地通过等同于真实 M3 model-quality 放行**。

已证明的边界：

- 用户未指定的五项 Planning intent 均保留为 `unknown / null`；模型推断不回写用户 intent，而进入独立 `planning-resolved-intent-v1`，来源标为 `model_inferred`。
- `user_explicit` 页范围、Section、课次数、单次时长和输出语言均为服务端硬约束；违反者在 proposal 应用或前端严格解码阶段失败。
- 模型 proposal 使用 request-local `unit_index`，不能提交 Study Unit、Plan、Schedule 或章节 ID。
- 显式物理页范围同时收窄初始代表性正文、详情工具正文和页读取结果。跨越边界、无法证明完全位于范围内的 chunk 不会进入模型证据。
- 历史法文 smoke 的精确回归已固化：在一个覆盖 PDF 70–110 的宽 Study Unit 中，显式要求 PDF 100–103 时，使用 70–73 的 proposal 被拒绝；使用 100–103、2 次、每次 30 分钟、法语的 proposal 可生成 committed projection。
- 上述成功路径仍把未指定的 `outline_targets` 保留为原始 `unknown`；提交投影中的实际 Section 来源单独标记为 `model_inferred`。

## 需求—证据矩阵

| 需求 | 当前证据 | 判定 |
| --- | --- | --- |
| 未指定字段保留 `unknown` | `PlanningIntentV1` 默认值、后端与 Web decoder 回归 | 已证明 |
| 用户显式值不可改写 | 工具参数、proposal invariant、committed projection 与 Web decoder 回归 | 已证明 |
| 模型可自行推断 | `LearningPlanProposalV2` 提供语言、排期时长、页与 Section 来源；resolved projection 记录结果 | 已证明结构路径 |
| 推断来源可验证 | `planning-resolved-intent-v1` 与前端 provenance/几何交叉校验 | 已证明结构路径 |
| 旧法文错误页不得提交 | `test_smoke_regression_rejects_70_73_and_commits_100_103` | 已证明应用边界 |
| 初始/工具正文不受错误页污染 | 显式范围 evidence-scoping 回归 | 已证明应用边界 |
| MiniMax-M3 在真实法文样本上稳定遵守新契约 | 尚无新 provider 请求 | 未证明 |
| MiniMax-M3 tokens、调用数、repair 与时延改善 | 尚无新 provider 请求 | 未证明 |
| 真实页 100–103 的定义/命题语义忠实度 | 尚无新 provider 请求与人工复核 | 未证明 |

## 验证记录

- `npm run test:ai`：908 项通过。
- `npm run check`：共享契约、Web TypeScript、Web reliability、Harness PR eval、十项 stage regression 与 Plan Revision eval 全部通过。
- 新增定向 Planning intent/证据范围回归通过。
- `git diff --check` 通过。

## 待完成的真实质量复测

待具体外发授权后，复用已解析的《Groupes Algébriques Tome 1》样本，只发送物理 PDF 100–103 相关文本、结构元数据与必要工具结果到 MiniMax 国内端点。请求约束为：

- `pdf_page_ranges = user_explicit(100–103)`
- `session_count = user_explicit(2)`
- `minutes_per_session = user_explicit(30)`
- `output_language = user_explicit(fr)`
- `outline_targets = unknown`

复核必须记录安全摘要中的 operation/HTTP 状态、provider calls、reported tokens、时延、工具物理页、repair、schedule 数量与时长、原始/resolved intent provenance；再人工核对 Définition 2.1、Proposition 2.2、Corollaire 2.3 与 Proposition 2.4。教材正文、API key 和完整 provider reasoning 不进入仓库。
