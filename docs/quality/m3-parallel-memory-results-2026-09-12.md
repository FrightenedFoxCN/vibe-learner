# MiniMax-M3 并行记忆实验与生产交接（2026-09-12）

本轮完成有界并行领域实验和实验 infra 改进。**96 个真实样本、186 次 HTTP 200、provider reported total tokens 1,053,685**；严格联合检查通过 24 个，候选失败 70 个，领域 uncertain 2 个。另保留 32 个沙箱 DNS 受阻样本及其未知预留，不混入模型质量分母。所有批次实际 wire 峰值均为 4。

最明确的工程发现是原生 MiniMax 工具 envelope 可带 `index`，与现有严格 decoder 的字段集合不兼容。实验适配候选消除了该批的工具形状拒绝，但仍存在原文标点改写、重复写入和无效最终载荷。**本轮没有修改生产默认配置或关闭 MQ-02/MQ-10，也不构成完整高并行探索计划的全部领域验收。**

## 证据入口

- [机器可读审核](evidence/m3-parallel-memory-2026-09-12/audit.json)：冻结案例/条件、逐样本结果、成本、延迟、错误类型、字符差异与重新计算的 memory exact。
- [完整证据包](evidence/m3-parallel-memory-2026-09-12/evidence.zip)：四批原 manifest/report、128 份领域证据、累计账本脱敏快照与审计、实验源码及逐文件 SHA-256。
- [交付清单](evidence/m3-parallel-memory-2026-09-12/delivery.json)：包摘要、验证结果、恢复核对和边界说明。
- [工具操作说明](../../tools/model-quality/README.md)、[原探索计划](m3-parallel-exploration-2026-09-12.md)、[统一质量 TODO](TODO.md)。

原始数据库和日志留在本机 `tools/model-quality/runs/` 及本轮临时日志中，未导出数据库或 provider 推理。证据包只包含合成资料产生的公开 receipt 和必要审计，不包含密钥。历史 capacity 批的旧版本配置也保留在累计账本中，不被本轮覆盖。

## 环境与预注册方法

接口固定为 `https://api.minimax.cn/v1/chat/completions`，模型 `MiniMax-M3`，认证仅从环境 `K3_API_KEY` 读取。使用服务 uv 环境、`LITELLM_LOCAL_MODEL_COST_MAP=True`，生产 Study prompt、tool catalog、严格 decode、admission、effect commit、Session read-back 与容器重启读回；SDK 网络入口由 native 计量 bridge 替换。因此这是实际领域生命周期证据，尚非原 LiteLLM/SDK transport 的等价认证。

每样本独立 spawn 进程、SQLite、storage、Document 和 Study Session；样本内写入、读取等依赖顺序执行。合成英文教材 PDF 用于进入真实 Study 生命周期，实验记忆内容另行给定。没有使用用户教材、正式 Session 或生产数据库。

8 个案例覆盖中英法标点、取消/重新启用、否定/未确认、数值与换行，按 4 个相关 family 分组。所有案例均为维护者编写的 development cases；不声称独立留出。跨批复用案例，96 次运行不是 96 个独立问题。seed 912 仅控制 case/repetition block 和条件交错，不代表 provider sampling seed。

共同配置：temperature 0.1、最多 4 worker / 4 wire 在途、60 RPM、4M 预留 TPM、单请求超时 60 秒、单样本期限 300 秒、最多 6 次 wire、输入预留 100,000 tokens。输入预留是保守操作值，不是实际输入 token 数。逐字请求明确给出 `experiment_reference` key、write/read 工具及禁止翻译要求。

联合检查要求 Session committed、receipt/read-back/restart 一致、恢复不调用 provider、memory 字符一致、typed effect batch 和 v3 committed，以及相应 memory effect。历史 effect rubric 还要求该 key 恰好一个匹配效果，严格于“最终原文保存正确”；下面保留这个原分母，同时报告最终 memory exact 和重复写入，避免事后美化结果。

## 批次与结果

| 批次 / 条件 | 样本 | 联合通过 | 候选失败 | uncertain | wire | reported tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 指令对照：baseline | 16 | 1 | 15 | 0 | 20 | 102,177 |
| 指令对照：加强回执提醒 | 16 | 3 | 13 | 0 | 24 | 132,761 |
| 配置对照：baseline | 16 | 3 | 13 | 0 | 23 | 124,590 |
| 配置对照：adaptive | 16 | 5 | 10 | 1 | 46 | 274,555 |
| 配置对照：首轮指定写入 | 16 | 2 | 14 | 0 | 23 | 122,824 |
| envelope 对照：adaptive baseline | 8 | 5 | 2 | 1 | 27 | 160,697 |
| envelope 对照：adaptive + strip-index | 8 | 5 | 3 | 0 | 23 | 136,081 |

指令批 `m3-memory-pairs-20260912-v2`：2,048 输出上限、thinking disabled，两条件只改变用户附加指令。加强提醒未稳定阻止仅用文字描述“写入并核对”。32/32 Session/Turn 均提交并通过重启读回，专门记忆成功只有 4/32；两者不可混为一谈。

配置批 `m3-memory-policy-20260912-v1`：统一 4,096 输出上限与加强指令，两个候选分别只开启 adaptive thinking、或只改变首轮 `tool_choice`。adaptive 的成功工具写入和读取各为 10/16，但联合通过为 5/16。观察到 14 条 tool shape rejection；首轮指定写入臂另有 1 条。它们不是成功执行。adaptive 有 1 例 `study_chat_uncertain_chat_model_invalid_payload`，HTTP 均为 200，不能归为供应商 HTTP 故障。

Envelope 批 `m3-memory-shape-20260912-v1`：统一 adaptive/4,096 输出上限，8 案例×2 条件×1 次重复。直接观测 38 个原生 tool-call envelope：23 个只有 `id/type/function`，15 个另带非负整数 `index`，没有未知字段，function 均为 `name/arguments`。baseline 产生 8 条 shape rejection；仅删除精确四字段 envelope 的整数 index 后，候选无 shape rejection，8/8 成功写入和读取，最终 memory exact 为 6/8，严格联合通过 5/8。baseline 联合也是 5/8：不能宣称整体质量胜出或统计显著。

跨批输出上限、thinking、遥测和实验适配器版本有变化；仅各批内部条件用于比较。原 manifest 冻结执行源码和配置。后续汇总代码和导出源码版本不同会单独保留摘要，不伪装成原执行版本。

## 失败审阅与测量边界

1. **文字声称保存与实际状态分离。** 指令批存在“已原样写入临时记忆，并读回核对”等回答，但没有工具 trace，也没有 memory_upsert。Turn 持久化正常不能证明专门记忆存在。
2. **原生 envelope 与严格契约冲突。** `tool_provider_projection.decode_provider_tool_call` 只接受两种精确字段集合。第三批提供了 index 的直接结构证据；前两批没有该遥测，不能回填每次旧拒绝的精确原因。候选仅在实验 bridge 处理已审阅的字段，不放宽未知字段或 domain 参数。
3. **逐字内容仍有偏移。** 实测把 U+2019 `’` 替换为 ASCII `'`，把 U+201C/U+201D 弯双引号改为 ASCII 双引号。第三批 strip-index 的 en-quotes、zh-scope 因此失败。字符审核从公开 persisted memory 与冻结 gold 重新计算，具体差异见 audit。
4. **重复写入与最终状态区分。** 第二批 adaptive 有 6/16 最终 memory exact，而严格 effect 检查仅 5/16；第三批 strip-index 分别为 6/8 与 5/8。多次同 key 写入使旧 rubric 的 `len(memory_effects)==1` 失败。这是额外严格的实验要求，不足以单独判定最终保存错误。生产决策应另审最终效果及写入顺序，先校准 grader 再确认。
5. **uncertain 保留原样。** 第二批 en-quotes/adaptive/1、第三批 en-identifiers/baseline/0 均为最终载荷无效，terminal trace 为 failed/not_committed。未自动重试或伪造成功；两个批次的同源码 `--resume` 保持 wire 分别为 92 和 50。
6. **独立性不足。** 字符与工具结果做了另一个只读脚本的确定性重算，但仍由同一维护者设计案例和程序；没有独立人工校准、真实前端、全平台或原 SDK transport 验收。MQ-01 引用与 MQ-03 多轮检索没有在本轮实测，状态类文本仅用于原文写入，不代表记忆时间推理通过。

## 延迟、容量与费用

| 条件 | 样本耗时 P50 / P95 秒 | wire P50 / P95 毫秒 |
| --- | --- | --- |
| 指令 baseline | 5.79 / 17.01 | 3013 / 5863 |
| 指令加强 | 5.22 / 28.67 | 2787 / 5801 |
| 配置 baseline | 8.41 / 21.78 | 3658 / 8749 |
| adaptive | 15.33 / 35.13 | 4266 / 9502 |
| 首轮指定写入 | 8.52 / 19.25 | 3661 / 6975 |
| envelope baseline | 17.07 / 32.97 | 3796 / 8520 |
| strip-index | 12.22 / 33.35 | 3840 / 7783 |

nearest-rank 分位数包含失败样本，样本耗时包含 worker/bootstrap/领域处理及等待，wire 是单次 HTTP 尝试。小样本 P95 不用于 SLA。186 次请求均有自洽 reported usage，没有新增 429/529；实际峰值 4 只证明本次有界工作负载运行情况，不是重新完成容量测量或发现供应商硬上限。计费金额、额度权重和供应商到账均未知，不按 reported tokens 推断费用。

复用本机 `tools/model-quality/runs/m3-window-20260912.sqlite3`：旧窗口 512 wire / 674,112 charged-or-reserved；本轮先对预算作审计调整（保留 50M token、10,008 wire 累计上限，降低在途/RPM/TPM，必要时延长期限），再显式恢复历史 overload。没有清账本。

沙箱 DNS 受阻批 `m3-memory-pairs-20260912-v1` 的 32 次已预留尝试全部无 HTTP status，保留 3,265,536 token 预留；这是未知操作性预留，不是声称供应商实际消费。受控网络权限下创建了独立 v2 诊断批，未把旧 uncertain 改回 pending。**本记忆诊断证据包导出时为 730 次账本尝试、4,993,333 charged-or-reserved，其中包含全部历史、受阻预留和该阶段真实 usage。后续三条优先 lane 与最终累计值见[总记录](m3-parallel-results-2026-09-12.md)。**

## 本轮 infra 变更

- `model_quality.reopen`：overload-only、无在途、冷却/期限/容量所有权检查，原子审计旧状态与新固定策略，保留旧成本及未知记录。
- DNS 预检：真实 worker admission 前检查解析；失败时不建新的 wire 或领域 operation，后续按原配置 resume。
- 固定矩阵生成器：instruction/policy/shape，明确 family、重复和单因素条件，实验代码与生产服务隔离。
- 工具观测：固定字段结构遥测，分开 observed 与 successful，保留 strict schema rejection；不保存参数或推理。
- 只读审核与证据导出：保留失败分母、逐样本公开 receipt、原 manifest、累计预算审计、逐文件摘要和复现源码；拒绝导出当前密钥字节、非终态或在途账本。

没有改动 `services/ai/app`、共享产品契约、数据库 migration、Web 或发布配置。工作区原有 desktop icon 改动未处理。

## 后续生产区更新建议

| 优先级 | 具体工作 | 生产采用前证据 |
| --- | --- | --- |
| P1 | 在 provider transport 投影处评审原生 index 兼容，保留 domain strict decoder | 对真实 SDK/native 两条路径采集同样结构证据；未知字段、非法 index、错误参数仍拒绝；有效工具执行与原子 receipt/read-back 回归 |
| P1 | 用户可见“已保存”必须有实际 memory effect / read-back 支持 | 明确仅 Turn 保存与专门记忆写入的区别；失败/未执行时不展示假成功；通过独立端到端审核 |
| P1 | 逐字保存策略避免依赖模型重新生成源字符串 | 对受保护原文引用/应用侧效果绑定做独立契约设计；验证授权和模型/应用字段归属，再用新中英法素材及 Unicode gold 确认 |
| P1 | 修订并独立校准记忆 grader | 区分最终 exact、重复写入、曾写错后修正、工具拒绝和未提交；保持旧批原始分母，不回写旧结果 |
| P2 | thinking 与工具策略重新评估 | 对未参与开发的新案例作受控确认，完整计入 reasoning、修复、失败、延迟；当前 5/16 或 5/8 不足以切换默认 |
| P2 | 继续 MQ-01、MQ-03、Planning/Tavern/图像等原计划 | 增加相应领域 adapter、完整记账与独立 review；本轮记忆实验不能替代这些门 |

生产代码更新仍需遵守 Harness ownership 与受保护 snapshot/effect 边界，并运行对应后端/前端契约门及最终 `npm run check:release`。本轮仅改独立实验工具，执行工具单元与领域适配回归，不宣称完成发布门。
