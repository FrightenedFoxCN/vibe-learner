# M3 Persona Source Constraint Capsule 结果（2026-09-13）

本轮按预注册比较 Persona model-owned proposal 的两个 fresh one-shot arm：当前 production long-text prompt 与追加人工 typed Source Constraint Capsule 的候选 prompt。实验不创建或保存 Persona，proposal commit evidence 固定为 `not_applicable`；本轮也不修改 production registry。

## 冻结调用与失败所有权

8 个全新合成 family 各运行两个 arm，共正常派发 16 条 wire；每 sample 至多一条，无 retry、web search 或 reasoning fallback。Campaign 使用 `MiniMax-M3`、adaptive thinking、temperature 0.2、max output 4096、timeout 90 秒，共记账 135,782 charged-or-reserved tokens，1 条 usage unknown，wire P50/P95 为 13,235/90,086 ms。

| 终态 | 数量 | 说明 |
| --- | ---: | --- |
| completed | 13 | strict Persona proposal 可用 |
| candidate_failed | 2 | `coastal_beacon` 与 `wetland_count` 的 production arm 均为 HTTP 200/stop 且有 final content，但 strict DTO decode 失败 |
| uncertain | 1 | `wetland_count` capsule arm 在请求发出后 90 秒超时，HTTP/usage 未知；不重试 |

任一臂不可用时，盲包对 A/B 两侧都使用完全相同 sentinel。因此 `coastal_beacon` 与 `wetland_count` 均不可评，全部 8 对仍进入 promotion 分母，strict paired candidates 为 6/8。

Manifest、report 与 16 份 allowlisted sample evidence 由 [frozen-run anchor](evidence/m3-persona-source-capsule-frozen-run-anchor-2026-09-13.json) 逐文件绑定，并冻结在 Git commit `570e84c5bbd7a06925d59e919c9b94e563814a93`。冻结 evidence 不含 provider reasoning、原始 envelope 或 protected snapshot。

## 双盲人工语义结果

两名全新隔离审阅者只能读取匿名 packet，不读取 key、run、代码、自动 marker、旧 review 或彼此结果。A/B 映射按独立 seed 平衡为 4/4。聚合器重新从 Git-anchored run 构造 packet/key，拒绝单侧 sentinel、重复 case/reviewer、重排后的同体 review、伪造 unavailable、packet/key 联合改写和 anchor 后 run 改写。

在 6 个可评 pair 上，两名审阅者共同确认 4 项 major reduction：

- `canal_notebook:shared_history_invention`
- `prop_registry:shared_history_invention`
- `rooftop_garden:permission_fidelity`
- `rooftop_garden:shared_history_invention`

但 worst-of-two 同时发现 capsule-only major：

- `ceramic_archive:permission_fidelity`
- `ceramic_archive:shared_history_invention`
- `radio_bench:permission_fidelity`

Capsule relationship major 为 0；capsule permission major 出现在 `ceramic_archive` 与 `radio_bench`。Exact-marker 校准不计入语义成功。完整解盲统计与各 review 摘要见[结构化聚合](evidence/m3-persona-source-capsule-paired-review-aggregate-v1.json)。

## 预注册决策与 Harness 含义

Promotion 必须同时满足 strict paired candidates 至少 7/8、双方共同确认至少 4 项 major reduction、candidate-only major 为 0、capsule relationship/permission major 均为 0。本轮只有共同 reduction 门通过；strict 门、candidate-only major 门和 capsule permission 门均失败，所以 `promotion_passed=false`。

这个结果支持一个较窄的结论：source-coordinate capsule 能降低部分共同经历和权限扩张错误，但不能作为稳定的 Persona 生成修复。它既没有通过语义 gate，也没有生产 adoption、Persona save/read-back 或 Tavern transfer 证据。按预注册，不补样本、不重跑 uncertain、不修改 production registry，也不启动依赖 Persona gate 通过的 Tavern transfer/counterfactual-twins campaign。Tavern 方向仍保留，下一轮必须另设独立策略和预注册，而不能把本轮局部 reduction 当作跨域成功。
