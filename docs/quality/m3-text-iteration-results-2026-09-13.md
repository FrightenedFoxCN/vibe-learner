# M3 纯文本迭代与多智能体早停记录（2026-09-13）

本轮按用户更正暂缓 multimodal 路线，复用既有并发 M3 基础设施和累计账本，只比较现有模型的纯文本提示迭代。历史 role v1–v5 的四个已曝光微任务没有重跑；容量阶梯、Planning 强制取证、坐标提示和通用 Reflection 也没有重跑。

## 方法

使用 8 个全新合成开发 family，覆盖双条件、物理/印刷页、未知分母、第三方身份、取消与生效日期、规则生效时刻、观察相关不等于因果、后续更正与缺失信息。每题交错运行三个单请求臂：原提示、静默约束清单、静默来源证据账本。所有输出继续使用严格 `Draft` schema；实验只生成 proposal，不进入生产 Harness 或领域写入。

运行沿用 `tools/model-quality/runs/m3-window-20260912.sqlite3`，并发 2、60 RPM、无自动重试。首次在沙箱内启动被 DNS 拒绝，未形成模型 wire；随后按原 campaign 身份和输出目录恢复，未新建账本规避累计成本。

## 结果与复核

| 臂 | 请求 | reported tokens | 原始严格通过 | 复核后的模型错误 |
| --- | ---: | ---: | ---: | ---: |
| baseline | 8 | 12,717 | 6/8 | 1/8 |
| constraint-checklist | 8 | 13,310 | 7/8 | 0/8 |
| evidence-ledger | 8 | 10,267 | 6/8 | 0/8 |

24 次请求全部 HTTP 200，reported tokens 36,294，unknown usage 为 0；wire P50/P95 为 6.842/18.441 秒。资源窗口累计为 1,595 次、11,509,403 charged-or-reserved、46 次历史 unknown usage，结束时无在途请求。

原始五个失败中只有一个可归给候选：baseline 在“18 人选择 K、总响应数未知”的非图表材料上无依据产生 `chart_questions`；两个单请求提示变体都避免了该字段。其余四个是 rubric 问题：三个答案正确选择了旧 20 分钟规则，但时间戳序列化与未明确格式的 gold 不同；一个正确否定因果的提问被简单禁词子串误判。实验准备器已把未来时间格式写成确定性要求，并移除无法理解否定语境的因果禁词检查；本轮原始分母不回写。

## 决定

- 第一轮暂留 `constraint-checklist` 作为下一批新文本案例的候选；它比 baseline 多 593 reported tokens（约 4.7%），本小样本观察到一个净修复，但证据远不足以改生产默认。下节第二轮已完成该复核并否定晋级。
- `evidence-ledger` 没有显示超过约束清单的新增收益，暂不晋级。
- 不运行 reviewer/self-revise 两个三请求臂。当前只有一个真实 baseline 错误，额外 48 个请求无法形成可信的多智能体收益估计，符合已有并发计划的早停规则。
- 不引入垂域小模型。当前错误可由提示约束或确定性字段检查覆盖，尚未形成需要 NLI/分类 sidecar 的稳定错误簇。
- 下一轮只有在新 entity/source-disjoint 文本材料上复现至少两个同类 baseline 错误时才扩大；否则继续优化样本与 rubric，而不是增加 agent 数量。

结构化审计见[本轮证据](evidence/m3-text-iteration-2026-09-13.json)。完整本地 report 的 SHA-256 和不可变路径已记录其中。

## 第二轮：来源与实体隔离复核

第二轮使用另外 12 个全新合成 family，按六个双例错误簇覆盖例外范围、记录时间与生效时间、嵌套转述、局部更正、未知字段和非图表结构。只运行 baseline 与第一轮暂留的约束清单，各 12 个单请求；没有运行 evidence-ledger、reviewer 或 self-revise。

24 次请求全部 HTTP 200，自动结构检查均为 12/12；总计 31,201 reported tokens、无新增 unknown usage，wire P50/P95 为 6.142/13.746 秒。baseline 使用 15,816 tokens，约束清单使用 15,385 tokens。若只看 schema、facts、分钟和空图表字段，两臂看似完全相同。

随后逐份人工对照 source、task、facts 和 `learner_prompt`，不使用关键词判定：

| 臂 | 人工通过 | 轻微语义问题 | 重大问题 |
| --- | ---: | ---: | ---: |
| baseline | 10/12 | 2/12 | 0/12 |
| constraint-checklist | 8/12 | 4/12 | 0/12 |

两臂的结构化事实、条件/例外、角色、时间、unknown、活动时长与 `chart_questions` 都正确。差异出现在自由提示：约束清单把 `recorded` 扩写为 `submission`、虚构 activity timer、把未限定的 register 改成 staff register，并加入来源没有评价依据的信息链可靠性任务。baseline 有两处轻微问题：给 registry 增加监管属性，以及把 unknown 描述成“由缺失推断”。答案可见性没有预注册，因此复述来源事实不被擅自判为泄漏。

第二轮没有出现任何一个满足“同簇两例 baseline 同向真实失败”的候选簇，故不触发 reviewer/self-revise。`constraint-checklist` 不再晋级：它未改善主答案，并在人工语义审查中产生更多轻微扩写漂移。垂域小模型同样没有稳定错误簇可接，生产默认保持不变。完整逐例人工评级见[第二轮证据](evidence/m3-text-iteration-round2-2026-09-13.json)。

实验 adapter 现将自动范围明确记录为“严格结构字段与 prompt 非空”，并标记 `learner_prompt_semantics_graded=false`、`manual_semantic_review_required=true`；未知 rubric 和畸形 gold 在 wire 前 fail closed。自动 `completed` 不再被解释为教学语义通过。

## 第三轮：最小忠实改写

第二轮暴露的主要问题不是结构 facts，而是自由提示会补写来源没有的语境。本轮在另外 12 个全新 family 上比较 baseline 与单请求 `source-minimal`；后者要求保持来源的事件、情态、身份和范围，不增加机构、现实操作、工作流或交付机制。每个 task 也统一声明 text-only、空 `chart_questions` 和禁止来源外事实。

24 次请求全部 HTTP 200、自动结构均 12/12，共 34,444 reported tokens、无新增 unknown usage；P50/P95 为 5.455/12.235 秒。baseline 使用 14,931 tokens，`source-minimal` 使用 19,513 tokens，后者高约 30.7%。

逐份人工语义审查结果：

| 臂 | 人工通过 | 轻微问题 | 重大问题 |
| --- | ---: | ---: | ---: |
| baseline | 4/12 | 6/12 | 2/12 |
| source-minimal | 9/12 | 2/12 | 1/12 |

`source-minimal` 修复了 baseline 在 `planned-rill-count` 中要求来源没有的现场 transect 做法、在 `recorded-umber-signal` 中要求推断 waiting 对应动作等问题；但它在 `scheduled-cobalt-filter` 中产生候选独有重大回归，把一条尚未执行的计划记录改写成真实拆滤芯、检查外壳、安装新滤芯和确认密封。它还两次虚构 submission 机制。

按预注册停止门，候选独有重大错误不能被总体 pass 增加掩盖，因此 `source-minimal` 不晋级、不改生产默认。baseline 的两例重大错误属于同一“要求来源无法支持的现实行动/流程答案”簇，可用于冻结坏稿的诊断性 repair replay；该 replay 不重新生成 baseline，也不能被解释为留出认证。第三轮逐例记录见[结构化人工证据](evidence/m3-text-iteration-round3-2026-09-13.json)。

## 第四轮：冻结坏稿的两角色修复回放

只回放第三轮已人工确认为 major 的两份 baseline Draft，不重新生成 baseline。对照为两次同模型 self-revision 与“fresh-context 同模型 specialist critic → repair”；两臂各严格两次 wire，运行前统一了实体、事件、现实操作、流程、时间、因果、可靠性、情态、归属及 planned/completed 缺陷本体。scheduler seed 只随机化 paired block/variant 顺序，未发送 provider seed；相同 wire 上限不代表相同 token 或算力。

8 次请求均为 HTTP 200、usage 完整，自动结构 4/4；共 13,016 reported tokens，P50/P95 为 5.123/13.228 秒。self arm 使用 5,997 tokens，specialist arm 使用 7,019 tokens，多 17.0%；specialist 的 wire P50/P95 为 7.041/13.228 秒，self 为 3.971/5.502 秒。一个 specialist repair 缺 reasoning/cache 明细，因此不汇总臂级 reasoning 或缓存收益，也没有 billing-token 结论。

逐句人工复核与另一 agent 的去标签 A/B 复核结论一致：两臂最终都是 0 pass / 0 minor / 2 major。两次 self-revision 在两个 case 上均原样保留错误。specialist 在 `planned-rill-count` 正确指出来源没有 transect 的实施方法，却在 guidance 和 final 中继续把现实 walking transect 绑定到 15 分钟学习窗口，只删掉了“how”，未降低 major 严重度；在 `recorded-umber-signal` 则返回空 issues，错误地认可“waiting 要求什么动作”，final 与冻结稿完全相同。自动 exact facts、分钟和空图表字段全部通过，正好说明这些指标不能判断 learner prompt 语义。

该结构最多称为固定 `evaluator → optimizer` 两角色 workflow。它受 [RAG-Critic](https://aclanthology.org/2025.acl-long.179/) 的错误分类—定制恢复思想和 [Building effective agents](https://www.anthropic.com/research/building-effective-agents) 的模式词汇启发，并借用 [AgentDropout](https://aclanthology.org/2025.acl-long.1170/) 的边际贡献思想决定裁剪 critic；但没有训练 critic、RAG、动态 agent elimination、orchestrator-workers、独立模型 judge 或论文方法复现。[Beyond Frameworks](https://aclanthology.org/2025.acl-long.1037/) 也提醒角色、顺序、上下文和治理是不同变量；当前只测试专项提示与角色分离的组合，不能外推一般多智能体收益。

按事前门槛，specialist 未在两例都修复原 major，也没有任何独有净修复，因此立即停止该分支，不在相同素材上追加调用、不改生产默认。结论是“当前开发回放未显示可归因增益”，不是“多智能体无效”。multimodal 继续暂停；两份已曝光坏稿也不足以同时引入垂域小模型。若新素材重现共同盲点，应先将学习任务措辞与来源中的现实事件明确分离，再在新的 entity/source-disjoint 确认集上把小模型作为单独因子比较。完整配置、逐 wire usage、prompt/draft 哈希、critic 贡献和论文边界见[结构化证据](evidence/m3-role-repair-replay-2026-09-13.json)。

## 第五轮：继续迭代 source-minimal

用户指出第三轮不应因候选出现一例 major 就终止整条提示路线：v1 同时修复了两例 baseline major，合理决策应是“不直接晋级，但允许针对回归改版”。因此另取 12 个全新 family，按学习时间/现实事件时长、planned/scheduled/proposed 模态、recorded/reported/listed/observed 边界各 4 例，比较 `source-minimal` 与 v2。task 未直接写入“不要执行/提交/验证”等目标禁令；两臂仍各一 wire。

24 次请求全部 HTTP 200，共 38,229 reported tokens、0 unknown usage；整体 P50/P95 为 5.632/10.574 秒。v1 使用 20,226 tokens，v2 使用 18,003，低 11.0%；v1 wire P50/P95 为 5.693/11.046 秒，v2 为 5.522/7.897 秒。自动结构为 v1 9/12、v2 10/12，但五个自动失败只是完整地点/设备名被截短，不能代替 prompt 语义评级。

两组 agent 分别逐句阅读六例；发现一名审查者漏看 `gauge Aster-15` 被截成 `Aster-15` 后，已回到原始 Draft 定向复核并更正。最终人工结果：v1 为 6 pass / 5 minor / 1 major，v2 为 9 pass / 3 minor / 0 major。v2 未再把学习时长变成现实事件时长，也未把计划/提议升级为已执行，且消除了 v1 在 `planned-mesa-core` 中把内容学习替换成整数拆分的 major。不过它仍把 memo 中的 `planned` 反向强化成“not yet performed”，来源不能证明后续状态；两臂也会丢掉 `Platform`、`Quay`、`gauge` 等受支持前缀。

因此 v2 进入新素材上的提示级细化，而非生产采用。v3 只改两个已观察盲点：要求复制完整 source span，并将 planned/proposed/scheduled 限定为“来源当时如此描述”，既不推断后来已执行，也不推断后来仍未执行。specialist 多智能体分支仍单独停止，不把其负结果用于否定单调用提示迭代；multimodal 继续暂停，小模型尚无必要。完整逐例结果见[第四批结构化证据](evidence/m3-text-iteration-round4-2026-09-13.json)。

## 第六轮：v3 新素材确认

在另 12 个与前四轮完全不重叠的 development family 上比较 v2/v3，各单调用。六例覆盖来源时点的 planned/scheduled/proposed，九例是完整名词短语哨兵，四例覆盖 measured/reported/observed/recorded 的认识状态；部分 case 有意交叉。task 仍不泄漏人工失败规则，且本轮在 manifest 中明确不是 independent holdout。

24 次请求全部 HTTP 200，共 34,740 reported tokens、0 unknown usage；整体 P50/P95 为 4.142/8.035 秒。v2 使用 18,535 tokens，v3 使用 16,205，低 12.6%；v2 wire P50/P95 为 3.565/17.222 秒，v3 为 4.142/7.846 秒。n=12 且 v2 有一个 17.222 秒离群点，不能据此宣称一般时延优势。

自动 exact facts 只有 v2 8/12、v3 7/12，表面上 v3 更差。逐份阅读后发现其中四个臂级失败是 rubric 规范化问题：模型保留来源支持的 `technician`、`Dispatcher`、`Biologist` 角色前缀，而 gold 只留人名，不能当语义错误。真实遗漏集中在 `specimen folio Heron-63`、`portable Raman spectrometer Elara-14`，以及 v2 的 `cargo tug Brindle-52`。这再次证明 exact/关键词指标只能 triage。

两名 agent 各审六例后的人工结果为：v2 8 pass / 4 minor / 0 major，v3 9 pass / 3 minor / 0 major。v3 修复了 `not yet performed` 的反向时点推断和一个完整实体 span；仍共同漏掉两处完整前缀，并在 `listed-cirrus-fan` 中把“台账列为位于”轻微强化成现实位置。没有出现现实作业执行、计划变已完成、reported/observed 变验证或因果、外部 workflow 等 major。

v3 因此只保留为独立确认候选，不改生产默认；相似 targeted development 素材到此停止，避免重复测试。下一步如果继续，应由未参与提示改写的人在新来源上预注册完整 span、认识状态和 learner task 评分，再做真实 UI/领域验收。当前没有稳定到需要垂域小模型的剩余错误簇；同时改变模型与提示会失去归因。完整证据见[第五批结构化记录](evidence/m3-text-iteration-round5-2026-09-13.json)。

## 实验后生产采用记录

上节“只保留为独立确认候选、不改生产默认”准确记录了第五批实验结束时的决定。实验完成后，用户于 2026-09-13 明确授权将 `source-minimal-v3` 设为生产默认；采用范围仅为 learner-facing 的 Learning Plan 与 Study Chat，不扩展到 Tavern、Persona/Scene、Harness schema 或 multimodal。multimodal 路线继续暂停，也没有因本次采用而引入垂域小模型。

这是一项实验后的产品授权，不是新的模型测试，也不应追溯改写实验结论。支撑材料仍是 entity/source-disjoint 的开发合成样本与内部逐稿人工语义审查；它们没有经过独立留出评审、真实学习效果测量或独立学习效果认证。因此生产采用与 MQ-10 独立质量门分开记录，既不重复相似开发测试，也不把 9 pass / 3 minor / 0 major 外推为一般生产质量保证。
