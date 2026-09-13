# M3 Planning intent 本地修复与真实复测（2026-09-13）

## 判定

本轮已在隔离分支 `codex/planning-intent-skeleton` 修复旧 smoke 报告中可由应用边界阻断的问题，并在取得针对指定法文页段与 MiniMax 国内端点的明确授权后完成一次真实 M3 复测。该样本通过 scoped gate，但单次成功仍不能证明跨样本稳定性。

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
| MiniMax-M3 在真实法文样本上遵守新契约 | 1 次真实运行，machine gate 通过 | 本样本已证明；稳定性未证明 |
| MiniMax-M3 tokens、调用数、repair 与时延 | 2 calls / 28,069 tokens / 47.3 秒 / 无 repair | 本样本已测量 |
| 真实页 100–103 的定义/命题语义忠实度 | 原页 PNG 视觉核对与计划人工复核 | 本样本通过 |

## 验证记录

- `npm run test:ai`：908 项通过。
- `npm run check`：共享契约、Web TypeScript、Web reliability、Harness PR eval、十项 stage regression 与 Plan Revision eval 全部通过。
- 新增定向 Planning intent/证据范围回归通过。
- `git diff --check` 通过。

## 真实 MiniMax-M3 复测

复用已解析的《Groupes Algébriques Tome 1》样本，只发送物理 PDF 100–103 相关文本、结构元数据与必要工具结果到 MiniMax 国内端点。请求约束为：

- `pdf_page_ranges = user_explicit(100–103)`
- `session_count = user_explicit(2)`
- `minutes_per_session = user_explicit(30)`
- `output_language = user_explicit(fr)`
- `outline_targets = unknown`

结果：

- `HTTP 200`，Planning operation 为 `committed`，严格 read-back 相等，Harness generation/tool terminal traces 均为 `passed`。
- 2 次 provider completion，共 23,757 input + 4,312 output = 28,069 reported tokens；总耗时 47.3 秒。第一轮调用一次 `read_page_range_content(100–103)`，第二轮完成计划；无 schema repair、无工具失败。
- 旧 smoke 法文结果为 2 calls / 62,297 tokens；本次同为两次调用，reported tokens 减少 34,228（约 54.9%），但总时延由约 34.9 秒增至 47.3 秒，不能宣称时延改善。
- committed schedule 恰好两项，每项 30 分钟；两项 anchor/content slice 均为物理 PDF 100–103。原始 `outline_targets` 保持 `unknown / null`，resolved Section 为 `model_inferred`；其余四项 resolved provenance 均为 `user_explicit`。
- 原页视觉核对：PDF 100 为 Définition 2.1，PDF 101 为 Proposition 2.2，PDF 102 出现 Corollaire 2.3，PDF 103 出现 Proposition 2.4。计划正确围绕这四项安排阅读/复述/核对，不再使用旧 smoke 中错误的 quasi-compact/quasi-séparé 定义，也未虚构 Proposition 2.5。
- 两次课各自成为独立 schedule 进度原子，但都使用同一个 100–103 章节 anchor；这是合法重复引用，不是把两次课压进一个 schedule。

安全机器摘要见 `m3-planning-intent-live-summary-2026-09-13.json`。教材正文、API key 和完整 provider reasoning 未写入 Git。

## 保留问题与放行边界

- 这是一个真实样本的一次成功，不是跨教材、跨语言、重复运行或 held-out 稳定性结论。
- 本次使用现有文本层，未启用页图工具；人工原页视觉核对不能证明生产模型已获得视觉证据。
- 本地 `planning_trace` 仍保留完整 provider thinking 与最终原始输出。本次两轮 thinking 长度分别为 2,373 与 10,171 字符；这一旧 smoke 风险仍未修复，安全摘要没有复制这些内容。
- 因此本轮可放行“显式 Planning intent 的应用边界与该法文样本”，不能据此整体放行所有真实教材 Planning 语义质量或 trace 留存政策。
