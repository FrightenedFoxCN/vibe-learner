# M3 Persona/Scene → Tavern shadow quality experiment（2026-09-13）

本轮建立了一个不进入正式 Harness registry 的 production-shaped shadow suite。它用四个全新合成 family 依次执行 Persona proposal、Scene proposal、用户保存/read-back、Tavern Room 快照、源 Persona/Scene 修改、direct turn、幂等 replay 和进程重启 read-back。生产 v3 trace 只负责 admission、protected snapshot、严格 decode 和真实 commit；语义检查与独立人工复核单独记账，不能升级为 commit evidence。

## 502 根因

首个真实诊断批次的 Scene generation 为 0/4。数据库终态 trace 和 wire allowlist 将 502 分成两类，而不是上游 HTTP 错误：

1. 实验领域 adapter 没有传 `openai_setting_max_tokens`，所以实际首次 Scene 上限只有 1400、JSON repair 只有 2200。多数响应为 HTTP 200 + `finish_reason=length`，严格 JSON 无法闭合，最终记录 `setting_model_invalid_json`。
2. 一份完整 JSON 把可省略的 `reuse_hint` 输出为 `null`。`SceneTreeProposalV1` 正确要求 string，但严格 decode 发生在 provider repair 回调之后，因此直接记录 `setting_scene_proposal_invalid:scene_layers.0.reuse_hint:string_type` 并映射为 502。

修复包括：实验 adapter 明确使用 4096 setting 上限、runner 预留一次最多 6144 的 repair；Scene 的完整 strict decode + projection validation 移入既有的一次 bounded repair 内，同时保留二次失败的精确路径。没有放宽 schema、没有把 `null` 归一化为空串，也没有改变 Persona/Scene proposal 的 `not_applicable` commit 语义。

修复后 adaptive 批次中 Persona 4/4、Scene 3/4、Tavern 4/4 完成生产边界。剩余 Scene 失败在首次 4096 和 repair 6144 都耗尽输出预算，均为 HTTP 200 + `finish_reason=length`，属于真实模型修复耗尽，不再是 adapter 配置或 repair 位置错误。

后续 confirmation 复查再次确认：6/6 production-shaped chain 没有 502；conditional Tavern exact-repair 的 5 条真实 wire 也全部是 HTTP 200。其两个失败分别是 `auditor-false-clearance-platform` 的 2048-token 输出耗尽，以及 `three-cell-seed-vault` 的 stop 后 strict decode 失败，均不是该 Scene 502 的复发。复查同时发现共享 content extractor 会在 Tavern 最终 `message.content` 不可用时回退到独立的 reasoning channel。该通道不是用户可见的 `TavernActorReply`，现已让 Tavern final-content 解析 fail closed；research adapter 也只记录 finish reason、通道类型/字符数和 allowlisted error code，不保存 reasoning 或生成文本。历史 raw envelope 按设计未落盘，因此不能把当时的一条 fallback 日志无证据地绑定到具体样本。

## Harness 策略对照

本轮保留三层结果：

- `production-v3 operational gate`：Proposal trace 必须是 `passed|repaired + not_applicable`；Tavern Message 必须是 `committed`，并验证房间快照、幂等 replay 和重启 read-back。
- `research lexical shadow ledger`：只对模型拥有字段做 required/forbidden 词面 triage；`search_keywords` 等应用回显字段不参与评分。独立代码审阅后，词面结果不再决定 runner 的 candidate 状态，runner 只报告 operational boundary 与 failure ownership。
- `independent manual review`：独立子智能体逐句评 Persona fidelity、Scene fidelity、relationship invention、task/format adherence。词面 triage 不能取代这一层。

Scene proposal 失败时，实验使用显式标注的确定性 Scene fixture 继续 Tavern，以免 Scene 失败吞掉下游分母。fallback 永远不计作 Scene 模型成功，也不是生产恢复策略。

另以相同四个 family 比较 `adaptive` 与 `thinking=disabled`：

| 模式 | Persona v3 | Scene v3 | Tavern committed/read-back | wires | reported/reserved tokens | wire P50 / P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive | 4/4 | 3/4 | 4/4 | 15 | 45,969 | 13.075s / 43.642s |
| disabled | 4/4 | 3/4 | 4/4 | 14 | 26,092 | 3.040s / 19.757s |

disabled 在这个小批次显著减少 token 和延迟，但没有消除 Scene 失败：另一例在两次严格校验后仍为 `scene_selected_path_invalid`。两种模式失败的 case 不同，不能把 disabled 晋级为生产默认。

## 独立内容复核

独立审阅没有查看实现代码，也没有采用自动布尔值。其原始 8×4 轴评分为：

- adaptive：6 pass / 4 minor / 6 major；
- disabled：5 pass / 5 minor / 6 major。

其中每批各有一个 Scene 使用下游 fixture fallback，所以相应 Scene 分数只描述可见实验产物，不是 M3 Scene 质量归因。主要可归因发现：

- “姐姐”案例的 Persona 在两批都漂移成学习者/陪伴型引导关系；disabled 还直接写成“医生朋友”。
- “职业未知”案例在 disabled Tavern 中接受了用户的“修伞同行”假前提，是明确关系/身份发明。
- adaptive 的两个成功 Scene 给“只有两个空间”的输入增加前厅、公共动线、走廊、设备和规则，属于重大来源漂移。
- disabled 改善了部分空间约束，但仍大量扩写；并未降低总 major 数。
- 词面 checker 有明显假阴性（否定句中出现“学生/患者”）和假阳性（命中必需词却漏掉第三空间、额外物件和关系重写），只能用于 triage。

v5/v6 原始 report 生成于这一审阅修正之前，因此其中 `candidate_failed` 受词面布尔值影响；不能把该 state 当内容失败率。保留它是为了不回写历史运行，正式内容结论以上述独立逐句复核为准。当前 adapter 已让 lexical triage 只进入 evidence，并把 4xx、内部 500、已知模型 502 与 transport uncertain 分开归属；非候选失败禁止使用 gold fixture 继续。

因此本轮只采用 502 的工程修复与 shadow suite，不采用 thinking 模式或内容 prompt 变体。下一步应在新 held-out family 上试高置信、可机读的 source-fidelity validator + 一次定向 repair；自由文本关系和场景忠实度继续要求独立人工复核。多候选/reviewer 仅保留为高成本实验臂，不能用同一 M3 的自评代替独立质量判断。

## 证据与验证

结构化摘要见 [`m3-persona-scene-tavern-shadow-2026-09-13.json`](evidence/m3-persona-scene-tavern-shadow-2026-09-13.json)。本轮五个保留真实 campaign 共 72 wires、178,790 reported-or-reserved tokens、0 新增 unknown usage；累计账本结束于 1,771 wires、11,839,823 charged-or-reserved、46 个历史 unknown usage，无 stop 状态。

本地验证：

- `npm run test:ai:provider:scene`：修正前 4/4；最终 provider Scene 定向矩阵 5/5；
- Persona/Scene/Tavern 定向后端矩阵：138/138；
- provider Persona/Scene：18/18；
- model-quality adapter/integration：8/8；
- 新 shadow helper：6/6（包含 Tavern 502 的权威 run/step/Harness 终态读回与伪造 `run_id` 拒绝）；
- model-quality 全量 integration：72/72；
- Tavern provider/API/facilitated 归因回归：47/47；其中 provider wire envelope 故障使用独立的 `tavern_actor_transport_payload_invalid`，不再与候选 JSON/schema 失败合流；
- fake production-shaped campaign：4/4。

这些测试与本轮独立子智能体审阅仍不是独立专家、真实 UI 或跨平台质量认证。
