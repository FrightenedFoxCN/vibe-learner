# M3 Persona Source Constraint Capsule 预注册（2026-09-13）

本实验只比较 Persona model-owned proposal，不创建、保存或读回 Persona。目标是检验人工预作者的 typed Source Constraint Capsule 是否能降低生产 long-text prompt 把普通关系教师化、升级权限、断言未知职业、虚构共同经历或洗白认知来源的风险。Capsule 不是从任意自由文本自动抽取的 authority；其来源坐标和 claim polarity 由人工基于冻结合成来源预先编写。

## 为什么选择这一 Harness 策略

既有 Persona/Tavern exact repair 会看到 frozen draft，容易受到原错误锚定；词面 marker 又漏掉自然语言同义发明，不能认证语义。本轮采用两个互不读取对方输出的 fresh one-shot arm：baseline 精确复用当前 production long-text prompt，candidate 只在相同 system prompt 后追加 source-coordinate capsule。两个 payload 除 appendix 外完全相同；appendix 不复制任何 source span 或称呼文本，不包含 fixture 中 case-specific 的 forbidden transformation literals、marker policy、issue code、gold proposal 或 mutation。它包含预注册的通用 source-fidelity 指令，这是本轮明确的 treatment，而不是自动评分 gold。

已评估但本轮不混入的替代策略包括 issue-only fresh regeneration、claim-ledger sidecar、same-draft repair、多候选生成以及 Tavern counterfactual twins。若 Persona gate 通过，Tavern transfer 将另设独立预注册实验，不能把两个域合并成一个成功率。

## 冻结矩阵与调用上限

- Fixture：8 个从未用于既有 Persona/Scene/Tavern campaign 的合成 family；每个 family 一份来源、一个人工 capsule 和六个 provider-free 单点 mutation。
- Arms：`production-prompt-fresh` 与 `capsule-prompt-fresh`。
- 调度：seed `91317`，按 family 内 AB/BA 交错；8×2=16 samples。
- Provider：`MiniMax-M3`、adaptive thinking、temperature 0.2、max output 4096、timeout 90 秒。
- 每 sample 最多一条 Chat Completions wire；16 个 sample 均正常派发时恰为 16 条。Pre-wire data/gate failure 可以是 0 条，但仍保留在分母；无 retry、web search、reasoning fallback、Persona admission/save/read-back。
- `candidate_failed`、`data_failed`、`infrastructure_failed`、`uncertain` 与缺失 strict candidate 全部保留在八对分母中，不补样本、不追加 wire。

冻结 live manifest 的文件 SHA-256 为 `b575efe51aae993697cbb3d4460e13911bf6028f3436618d36a57cc07bb29659`，canonical campaign digest 为 `c4b4bdf1bcd1a31688c3463502a98feaa521df784be066fbf7a0f6241a5332ea`。Fixture SHA-256 为 `bf24f623b4644765133d0a9e94fb24f96984c92252a13323f9584c0e79106a23`。实现冻结到提交 `5115ed822c411b6afee1327f74f7b18c542f401c`；基础实现提交为 `b0e58de9d474b06450b8958bf1143e534c3d2741`。

## 校准与证据边界

Provider-free 校准要求：8/8 pristine、8/8 hard-negative、48/48 single-pointer mutation 精确命中唯一预期 code；source SHA、capsule SHA、Unicode character/UTF-8 byte coordinates 和文本 slice 均 fail closed。Exact marker 只证明合成 mutation 的窄规则，没有自然语言蕴含能力，不参与 live semantic promotion。

每个 live evidence 绑定 source、capsule、prompt projection、完整 provider payload 和完整 campaign config digest，只保存最终 `message.content` 解码出的 proposal 与 allowlisted wire 摘要，不保存 reasoning 或原始 envelope。Persona proposal commit evidence 固定为 `not_applicable`；用户保存是独立边界。

## 双盲人工语义门

Live run 终态后先生成 manifest/report/全部 sample evidence 的 frozen-run anchor，并把 anchor 与安全 run artifacts 提交到 Git。只有验证该 anchor 字节存在于指定 40 位 Git commit 后，才允许导出盲包。任一臂不可用时，packet 对 A/B 两侧都放完全相同的 unavailable sentinel，避免失败位置泄漏。

两名全新隔离审阅者只能读取 packet，不读取 key、run、代码、自动 marker、旧 review 或彼此结果。逐候选评价：

- `relationship_fidelity`
- `permission_fidelity`
- `profession_uncertainty`
- `shared_history_invention`
- `epistemic_provenance`
- `task_format_adherence`

等级为 pass/minor/major/not_evaluable。聚合使用 worst-of-two，并拒绝重复 reviewer ID、重排后的相同 review body、重复 case、单侧 unavailable、packet/key 联合伪造及 anchor 后 run 改写。

Promotion 必须同时满足：

- 8 对全部进入分母，至少 7 对两臂均有 strict candidate；
- 至少 4 个 case×axis major reduction 被两名审阅者共同确认；
- 任一审阅者报告的 candidate-only major 为 0；
- capsule arm 的 relationship major 为 0；
- capsule arm 的 permission major 为 0。

失败时不修改 production registry，不追加样本或第二次调用。通过也只形成独立 Persona 后续采用候选，不自动授权生产修改，更不证明 Tavern transfer。

完整机器可读预注册见[结构化证据](evidence/m3-persona-source-capsule-preregistration-2026-09-13.json)，冻结调用配置见[live manifest](evidence/m3-persona-source-capsule-live-manifest-2026-09-13.json)。
