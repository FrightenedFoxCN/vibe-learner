# M3 Persona / Scene / Tavern confirmation 与 repair 复核（2026-09-13）

本轮在原四个开发 family 之外冻结六个独立编写的 confirmation family。每例都走 Persona proposal、Scene proposal、用户保存与读回、Tavern Room 快照、direct turn、幂等 replay 和进程重启读回；完整来源被 canonicalize 到 case source，proposal 与 commit 所有权保持原契约：Persona/Scene 是 `not_applicable`，Tavern Message 是 `primary_output_only`。

## Baseline 与 exact guard

production-shaped baseline 为 6/6 完成：Persona proposal 6/6、Scene proposal 6/6、Tavern commit/read-back 6/6。共 22 wires、68,563 reported-or-reserved tokens、0 unknown usage，P50/P95 为 10.413/41.284 秒；没有 502。这只证明生命周期和严格结构，不证明生成内容忠实。

研究级 exact guard 共 15 项检查，9 pass / 6 fail，并触发 5/6 Tavern repair。它能抓逐字开头、称呼、两项预注册 Scene topology 和 credential-like 数字，却漏掉多数人工 major：Persona 把远程业务关系教学化、Scene 在“只有”约束下增添走廊/码头/门禁/设备、Tavern 把日志说成现场观察或引入提货单。exact guard 因此只能是窄触发器，不能作为 source-fidelity validator。

## Conditional Tavern repair

repair 保持一例最多一条 wire，不覆盖已提交 Message，也不写生产 v3 trace。六例中一例无需 repair，五例发出真实 wire；结果为 4 completed / 2 candidate_failed，共 18,317 tokens、0 unknown usage，P50/P95 为 5.982/13.322 秒。`auditor-false-clearance-platform` 是 HTTP 200 后 2048-token 输出耗尽；`three-cell-seed-vault` 是 HTTP 200/stop 后 strict decode failure。两例均没有可评 repaired reply。

repair 明显改善了逐字拒绝：姨妈假关系、静默信号站的要求开头，以及未知职业/红海同行前提得到更直接纠正；但它没有移除冻结 draft 中的认识论或 closed-world 发明，例如信号站额外设备细节和包裹站的提货单。

## 双盲配对人工复核

生成器把 authoritative source 与 A/B Tavern replies 写入盲包，另存随机 key。两名隔离子智能体只读盲包，没有读取 key、report、自动分数、实现或彼此结果；strict repair 不可用的回复一律 `not_evaluable`。四个 pair 可评，两个不可评。

为修正第一轮审阅只有会话摘要、没有逐例评分表的证据缺口，另请两名隔离审阅者 C/D 重做盲评并冻结完整 JSON。解盲后，C 的可评轴从 initial 的 9 pass / 3 minor / 4 major 变为 intervention 的 13 / 1 / 2，识别出两项 task-adherence major reduction；D 从 9 / 3 / 4 变为 11 / 2 / 3，只识别出一项。两人共同确认的 major reduction 只有 `mediator-not-aunt-cinema:task_adherence`；均未发现新 major。第一轮 A/B 摘要不再作为可审计结论使用。

本轮事前没有冻结可验证的晋级门，因此只能使用明确标记为 post-hoc 的保守判定规则：至少三项由所有审阅者共同确认的 paired major reduction、零新增 major、且全部 repair 候选可评。实际只有一项共同 reduction，且 2/6 repair 无可评候选，因此 **不晋级生产**。这不是正式门控实验的通过/失败结论，而是拒绝把当前有限收益提升到生产的保守决定。下一轮 Scene 实验将在任何 live wire 之前冻结门槛。

## 下一 Harness 策略边界

下一实验应把变量收窄到 Scene closed-world fidelity：冻结当前成功的 Scene drafts，对明确写有“只有/仅/恰有/不要添加”的 source，使用 typed topology/object issue contract 先判定新增空间、对象、入口/动线和权限，再对命中的 draft 做一次 proposal-only repair。自由关系与知识来源仍需独立人工复核；generic same-model critic→repair 已在另一批 frozen major 上 0/2，多候选生成约需 3–4 倍调用，暂不作为第一选择。任何研究 repair 都不得改写 committed Tavern Message、Room/Run/Step 或生产 v3 evidence。

完整路径、哈希、分母和盲评汇总见[结构化证据](evidence/m3-persona-scene-tavern-confirmation-2026-09-13.json)。
