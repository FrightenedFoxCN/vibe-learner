# M3 Scene closed-world repair 结果（2026-09-13）

本轮在 6 个全新合成 family 上评估一次条件式 Scene repair。实验只覆盖 model-owned proposal；baseline 虽经过 production `/scene-setup/generate` admission，仍不保存产品 Scene，repair 更不具备 domain admission、commit 或 read-back。closed-world policy 是 research-only 的确定性 fidelity gate，没有注册为 production Harness component。

## 502 归因边界

历史诊断 campaign `m3-persona-scene-tavern-shadow-20260913-v2` 的四个 Scene API 请求均返回 502，但对应 8 条 Scene provider wire 全部为 HTTP 200：4 条 initial 使用 1400 token，4 条 repair 使用 2200 token；7 条以 `finish_reason=length` 结束，1 条以 `stop` 结束。这个提交内可独立复算的结论是：所见 502 发生在本地 API 边界之后，不是这 8 条 wire 的 upstream HTTP 状态。`services/ai/app/api/routes.py::_map_setting_generation_error` 会把 `setting_model_invalid_json` 和 `setting_scene_proposal_invalid:*` 映射为 HTTP 502。

历史本地 SQLite 终态 trace 曾进一步把四例分为三个 `setting_model_invalid_json` 和一个 `setting_scene_proposal_invalid:scene_layers.0.reuse_hint:string_type`，与 7 条 length 和 1 条 stop 相符；但原始数据库含 protected snapshot，未纳入本提交。因而这个 3+1 细分是本地复查诊断，不是本证据包可独立 replay 的认证结论。历史 manifest 的 source hashes 也只对应当时 revision，不应拿当前代码替代重放。

这项历史归因与本轮 closed-world campaign 分开：本轮 baseline 6 条、repair 4 条，共 10 条 upstream wire，也全部为 HTTP 200。paired-review key v2 绑定两个 report 的 SHA-256，exporter 逐 wire 校验唯一 ID、sample、campaign、finished state、call kind、HTTP status 和 token 对账。它只能证明本轮 10 条 wire 的事实，不能替代历史诊断 campaign。

## 冻结结果

| Arm | 样本终态 | Wires | Tokens | Unknown | Wire P50 / P95 |
| --- | --- | ---: | ---: | ---: | ---: |
| production-shaped baseline | 4 completed / 1 infrastructure_failed / 1 uncertain | 6 | 23,388 | 0 | 14,009 / 21,874 ms |
| conditional one-wire repair | 3 completed / 1 candidate_failed / 1 inherited infrastructure_failed / 1 inherited uncertain | 4 | 19,049 | 0 | 4,877 / 24,895 ms |

Baseline 的 `observatory` 首次 wire 为 HTTP 200/stop；production retry 将上限从 4096 提到 6144，但冻结 campaign ceiling 仍为 4096，因此第二条 wire 发出前被拒绝，历史终态保持 `uncertain`。`print_workshop` 的 production proposal/trace 成功，但 research policy 对其结构不可评，旧 adapter 将其记为 `infrastructure_failed`；proposal 未保存，不能进入 repair。四个 eligible case 各使用一条 repair wire，其中三个得到 strict DTO 且 deterministic issues 为零；`seed_archive` strict repair decode 失败。因此只有 3/6 strict repaired candidates。

## 独立盲审与决策

旧 `paired-review-packet-v1`、reviewer E/F 和 aggregate v1 因单侧 unavailable 泄漏、重复 case 可膨胀计数、packet/key 联合伪造和 run 绑定不足而全部排除。

新 packet 对 unavailable pair 使用双侧完全相同 sentinel。两个全新隔离审阅者 G/H 只能读取 packet，不读取 key、run、代码、旧审阅或彼此输出。两人均在三个可评 pair 上确认三项 topology-fidelity major reduction，且均未发现新增 major regression。解盲聚合器从 frozen runs 重建 packet/key，并拒绝重复 case、伪造 unavailable、重复 reviewer、相同 review body 与 packet/key 联合改写。

预注册 promotion gate 要求至少 5/6 strict repaired candidates、至少三项双方共同确认的 major reduction、且无新增 major regression。后两项通过，但第一项只有 3/6，因此 `promotion_passed=false`。不补样本、不追加第二条 repair wire、不修改 production registry，也不将 research policy 当语义认证。

结构化证据见 [m3-scene-closed-world-results-2026-09-13.json](evidence/m3-scene-closed-world-results-2026-09-13.json)。
