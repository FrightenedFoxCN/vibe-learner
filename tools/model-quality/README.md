# Model Quality Lab

可复制到其他仓库的模型实验基础设施。独立 Python 项目、依赖锁、CLI 和故障测试；通用核心不导入 Vibe Learner；项目适配器在 `integrations/` 下按需加载，不接入应用 `npm test`、Harness registry 或生产启动。需要 Python 3.12+、uv 和 POSIX 本地文件系统（macOS/Linux）；当前不支持 Windows、网络共享盘或分布式主机。

## 最小使用

从本目录运行。默认 fake transport 不联网，只验证基础设施：

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python examples/prepare_preflight.py --output /tmp/mq-fake.json
uv run python -m model_quality --manifest /tmp/mq-fake.json --output /tmp/mq-fake-run --ledger /tmp/mq-fake-window.sqlite3
uv run python -m model_quality --manifest /tmp/mq-fake.json --output /tmp/mq-fake-run --ledger /tmp/mq-fake-window.sqlite3 --resume
```

M3 国内官方源预检使用已设置的 `K3_API_KEY`，不写入 `.env` 或命令行参数：

```bash
uv run python examples/prepare_preflight.py --transport minimax --id m3-preflight-v1 --output /tmp/mq-live.json
uv run python -m model_quality --manifest /tmp/mq-live.json --output /tmp/mq-live-run --ledger /tmp/mq-live-window.sqlite3
```

仅向 `https://api.minimax.cn/v1/chat/completions` 发至多 **4 次**合成文本请求，4 个独立进程；不自动重试，该示例未启用自动扩容。真实资源窗口内后续 campaign 必须沿用同一个 ledger 的绝对路径和同一份 `budget`；明确扩展额度时使用下述审计式预算调整命令。示例创建的额度只适用于该预检，不能反复新建账本声称全日累计受控。不同窗口的预算配置由操作者确认，程序无法识别账外调用或供应商到账。

只重建报告可使用相同参数加 `--report-only`；它不要求 API key、不执行 worker、不改变 uncertain/running 状态，允许使用更新的汇总代码并记录其摘要。

CLI exit code：全部 `completed` 为 0；候选失败、未完成、不确定或预算停止为 1；配置/运行器错误为 2；中断为 130。CLI 不输出原始异常字符串。样本错误归属和停止原因查看 `report.json`；严格协议见 [protocol.py](model_quality/protocol.py)。

## 协议与隔离

Manifest 冻结案例、关联 family、split、合成来源、source/request、gold/rubric、variant、随机种子、调用上限和有效模型配置。按 case/repetition 分块随机 AB/BA，重复不计为新的独立 family。`reserved` 案例禁止派发，不提供未经独立审查的 held-out 标签。首个适配器只支持合成纯文本、精确比较；模板中的两条语言控制用于基础设施预检，不是模型泛化质量样本。

`seed` 只控制调度交错顺序，不代表供应商支持采样 seed。

每个 `case/variant/repetition` 使用全新 spawn 进程及专属 `domain.sqlite3`、`storage/`、工作目录。同一样本内的有依赖步骤由适配器串行执行。外层进程数和全资源窗口 wire 在途数分别受限。旧探针的全局 monkeypatch 不会因线程共享而串扰，但旧探针不能原样接入：必须让其所有 wire 调用经过计量 transport，并明确传入专属数据库/存储设置。

Manifest 记录 Git HEAD、tracked dirty digest、运行器及适配器源码摘要、依赖版本和锁文件摘要；保留源文档配置，不保存密钥。恢复要求配置、源码、依赖及 ledger 路径一致。适配器可通过 `source_manifest()` 扩展冻结范围。Vibe Learner 适配器会记录完整 `app/**/*.py`、自身源码、服务锁文件和关键依赖版本；任意外部资料仍需适配器作者冻结。

## 预算、观测与恢复

- SQLite `BEGIN IMMEDIATE` 在 wire 之前原子检查全窗口 token、wire、RPM/TPM、在途并发、样本调用次数和到期缓冲。RPM/TPM 使用保守的滑动 60 秒窗口，不是自适应 token bucket。
- 每次预留输入配置上限 + 最大输出；文本请求体字节数超过输入预留则不发请求。只有完整且自洽的 prompt/completion/total usage 才校正预留。缓存、reasoning、计费 token 缺失保留 null；无 usage、超时或崩溃均不释放预留。实际 usage 超过预留立即停止新请求。
- **这是操作性预算控制，尚非供应商计费硬上限证明。** M3 额度权重、reasoning/缓存口径和绝对单次 token 上界未核验；不得仅凭账本宣称 2G 绝不超额。当前不支持图片输入，也不提供货币额度执行器。
- 一个 transport 调用就是一个已预留的 HTTP 尝试，无 SDK 隐藏重试。禁止跟随重定向。401/403 停止全窗口新请求；固定并发模式下 429/529 也停发，自动模式下则立即降档和冷却，记录数值 Retry-After；已经发出的请求可能继续到超时。恢复不会自动解除停止闸或回收未知额度。
- 样本结果逐个事务提交。`report.json` 从 checkpoint 重建并原子替换，包含预期分母、所有失败、case 配对、family 数、wire 账本、P50/P95 和跨 campaign 总计；崩溃不依赖 JSONL 最后一行是否完整。
- campaign 文件锁禁止双调度器，样本文件锁阻止在原 worker 尚存活时恢复。恢复发现 `running` 则标记 `uncertain`，不重新发模型请求；已完成、失败、不确定样本都不自动重跑，只启动尚未派发的 pending 样本。需要确认或领域 query-only read-back 时由领域适配器和人工处理，不能将 uncertain 改成 pending。
- 截止期限终止 worker 并保留未知结果；无法保证上游同步请求同时停止。checkpoint 和 wire 不跨两个数据库原子提交，因此极端崩溃可以留下“已计量但样本 uncertain”，不据此虚构成功。

输出留在操作者指定目录。参考适配器仅保存指标和脱敏 usage，不保存原始回答、推理、provider 错误正文或密钥。通用适配器属于可信代码，运行器不是网络/文件沙箱。

## 接入自己的项目

在相同 Python 环境中提供可导入函数，把 manifest 的 `adapter` 设为 `your_package.experiments:run_sample`。签名是 `run_sample(context, case, variant) -> dict`，参考 [adapters.py](model_quality/adapters.py)。

`context.transport.complete(messages, call_kind=...)` 接收简单文本，`context.transport.request(payload, call_kind=...)` 接收生产 JSON Schema/function-tool 请求。两者共享预算闸；后者允许 assistant/tool 消息及文本分块，仍拒绝图片。seed、critic、selector 和修复分别计量，`sample_wire_limit` 限制总调用。`context.database` / `context.storage` 是专属路径，适配器负责将它们绑定到项目设置，并在有状态步骤后按领域规范 read-back。调度器不会自动让旧项目 bootstrap 采用这些路径。

结果须通过 `AdapterResult`：`completed`、`candidate_failed`、`data_failed`、`grader_failed`、`metric_failed`、`infrastructure_failed`、`uncertain` 与相应 `failure_owner`；metrics 只接受有限数值、布尔值或 null。异常默认归 infrastructure，评分器/数据异常需适配器明确归属。领域结果使用 `domain-primary-output-readback` 范围及 `evidence` 文件引用，运行器校验文件存在且是 JSON，领域适配器负责验证实际 receipt、提交图和重启读回。Harness 身份来自真实 admission；不能把基础设施成功当成领域成功。

当前版本没有阶段子池、加权 lane 公平调度、跨主机分片合并、独立 grader 校准或统计显著性推断。这些可以按实际研究需求增加，基础运行器不自动启动质量研究或修改生产策略。

## 自动扩容

在 manifest 中加入：

```json
"concurrency": 2,
"autoscale": {
  "min_concurrency": 1,
  "max_concurrency": 4,
  "window_seconds": 60.0,
  "min_completed": 30,
  "healthy_windows": 2,
  "p95_multiplier": 1.25,
  "max_error_rate": 0.05
}
```

真实请求强制每窗至少 60 秒、30 个完成请求，连续两个健康窗且仍有足够 pending 工作才将并发翻倍，最多到明确配置的上限；usage 未知、出现错误或缺少低负载基线均不能升档。P95 超过初始健康窗的 1.25 倍则减半。两个窗口的基础设施失败率均超过 5% 时停止全资源窗口。候选内容失败不算供应商基础设施失败。

429/529 在 wire 结束事务内立即将全局在途上限与发放速率减半，冷却至少 5 秒并尊重数值 Retry-After，加少量随机抖动；失败请求不自动重试。RPM/TPM 仍是滑动窗口，其硬上限不会被扩容提高。在途请求可以完成 read-back；降档不伪称取消上游请求。所有控制状态、冷却与决策都保存在共享账本，恢复不重置。多个 campaign 必须使用同一控制策略；并发硬闸覆盖所有进程。升档决策使用当前调度器的 pending 数，因此多 campaign 下可能保守少扩容。

本机容量由操作者设置 `max_concurrency` 与 `budget.max_inflight`；没有自动探测供应商最大容量或本机内存的机制。默认不会为满足窗口样本数额外生成案例。fake 测试允许缩短窗口，不能把该设置用于真实接口。

## Vibe Learner 领域适配与测试

从本工具目录运行，显式借用服务自己的依赖环境。工具的通用依赖不因此增加 FastAPI/LiteLLM；应用测试命令也保持不变：

```bash
export PYTHONPATH="$PWD:$PWD/integrations:$PWD/../../services/ai"
export LITELLM_LOCAL_MODEL_COST_MAP=True
uv run --project ../../services/ai python -m unittest discover -s integration_tests -v
uv run --project ../../services/ai python -m vibe_learner.prepare --output-dir /tmp/mq-domains
uv run --project ../../services/ai python -m model_quality --manifest /tmp/mq-domains/study.json --output /tmp/mq-study --ledger /tmp/mq-domain-window.sqlite3
uv run --project ../../services/ai python -m model_quality --manifest /tmp/mq-domains/tavern.json --output /tmp/mq-tavern --ledger /tmp/mq-domain-window.sqlite3
```

准备真实预检时给 `vibe_learner.prepare` 加 `--transport minimax`，需要 `K3_API_KEY`。生成器只准备两个 Study、两个 Tavern 合成样本，两个 campaign 共用一份预算；每样本最多 6 次 wire。它们用于接入验收，不计作四个独立内容质量案例。Study 保存合成 PDF 并走 Document process → Session → Chat admission → memory effect → receipt → 容器重启读回；Tavern 走 Persona → Room → direct turn → actor commit graph → replay → 容器重启读回。专门记忆、Turn 提交与模型“已保存”的口头声明分别核对。

适配器在进程内替换 SDK 的网络入口，将完整生产 prompt/schema/tool messages 交给计量 native transport；Embedding 和 Responses 旁路直接拒绝。生产生命周期与校验仍由应用执行，但这不是原 SDK transport 的等价认证。当前领域覆盖 Study 记忆和 Tavern direct；Planning、Scene、图像与 facilitated 队列需继续增加专门适配器。

`storage/domain-evidence.json` 保存合成输入产生的公开 receipt、真实 operation/effect 身份、受限 trace 摘要与 read-back 指标，不保存模型推理。外层 sample 因进程崩溃成为 uncertain 后，不自动再执行领域 adapter；需要另行 query-only 审核其已记录的领域身份。

## 扩展同一资源窗口预算

后续批次超出初始小额预检的上限时，用新 manifest 明确给出累计上限和期限，并执行：

```bash
uv run python -m model_quality.budget --ledger /absolute/path/window.sqlite3 --manifest /absolute/path/next.json --reason 'Authorized bounded adapter acceptance; retain previous usage'
```

这记录旧/新配置与原因，保留所有历史 wire、已花、未知 usage 和停止状态；拒绝在请求仍在途时修改，累计 token/wire/期限不能缩减。它不会自动确认额度到账，也不会解除认证或基础设施停止闸。策略变更不在预算调整范围内。

## 真实并发容量测量

`model_quality.capacity` 提供持续补充在途请求的分档测量，默认 4/8/16/32/64，每档两窗，每窗至少 60 秒且至少 30 个完成请求；单窗最多 180 秒。达到窗口条件后停止补充并等在途结束。发生供应商停止条件、窗口不合格、未知 usage 或基础设施失败就不再升档；高档 P95 超过低档基线 1.25 倍也停止升档。全档通过只能证明“至少支持已测最高档”，不能推导供应商硬上限。

它只接受显式声明 `CAPACITY_SAFE = True` 的可信、线程安全、无领域副作用适配器。`vibe_learner.capacity:run_sample` 每请求新建 Tavern provider，使用生产 prompt/schema/decoder，原生计量 HTTP；不使用全局 monkeypatch，不写 Room/Session，也不声称领域提交成功。候选校验失败会记录，修复在回调入口拒绝，保证一条负载样本恰好最多一次 wire，且不会因拒绝修复而提前结束观测窗。禁止用此入口并发执行 Study/Tavern 领域写入适配器。

准备一个使用上述适配器、`autoscale: null`、`sample_wire_limit: 1` 的 campaign manifest，并确保累计预算、RPM/TPM、`max_inflight` 足够覆盖计划档位。从本工具目录使用服务依赖环境运行：

```bash
export PYTHONPATH="$PWD:$PWD/integrations:$PWD/../../services/ai"
LITELLM_LOCAL_MODEL_COST_MAP=True uv run --project ../../services/ai python -m model_quality.capacity \
  --manifest /absolute/path/capacity.json --output /absolute/path/capacity-run \
  --ledger /absolute/path/existing-window.sqlite3 --levels 4,8,16,32,64
```

测量期间通过显式审计事件调整档位，同账本其他 campaign 的新请求被阻止；档位变更要求已排空在途。结束后恢复原控制策略，保留所有费用、未知预留和供应商停止状态。若整个进程被强制杀死，不自动恢复或重发，应先检查原 worker/在途状态及 `previous-control.json`。容量探针不提供自动 resume。

`c*-w*-result.json` 按窗口保存脱敏 wire 与样本状态；`report.json` 记录实际峰值在途、完成吞吐、P50/P95、状态码、unknown usage、最高稳定档和停止原因。重复合成负载可能命中缓存，不代表不同内容长度、图片、长 Planning 或多轮 Study 的吞吐；schema 通过率也不是内容质量评分。

## 2026-09-12 并行记忆实验与交付

[完整实验记录与生产交接](../../docs/quality/m3-parallel-memory-results-2026-09-12.md)记录了 96 个真实领域样本、186 次 HTTP 200 请求，以及另行保留的 32 个 DNS 受阻样本。新增命令全部属于实验工具；没有改变生产默认模型、工具解码或写入策略。

准备三种冻结矩阵，仍使用上文的服务依赖环境与 `PYTHONPATH`：

```bash
python -m vibe_learner.prepare_quality --transport minimax --experiment instruction --id your-instruction-batch --budget-from /absolute/path/window-budget.json --output /absolute/path/instruction.json
python -m vibe_learner.prepare_quality --transport minimax --experiment policy --id your-policy-batch --budget-from /absolute/path/window-budget.json --output /absolute/path/policy.json
python -m vibe_learner.prepare_quality --transport minimax --experiment shape --id your-shape-batch --budget-from /absolute/path/window-budget.json --output /absolute/path/shape.json
```

`window-budget.json` 的顶层为 `{"budget": ...}`，使用当前账本的完整 budget；不要按每批重建日累计窗口。instruction 为 8 案例×2 条件×2 重复，policy 为 8×3×2，shape 为 8×2×1；最多分别 192/288/96 次 wire。policy 的 `adaptive` 改变 thinking，`force-write-first` 只改变第一次请求的 tool_choice；shape 两臂均为 adaptive，候选只删除精确工具 envelope 中非负整数 `index`，其余结构仍走生产严格解码。这些是开发诊断条件，不是可直接启用的生产配置。

显式恢复已经排空的历史 `provider_overload` 停发：

```bash
python -m model_quality.reopen --ledger /absolute/path/window.sqlite3 --concurrency 4 --reason 'Explain the authorized new experiment and reduced load'
```

恢复仅接受 overload，必须无在途、已过至少 60 秒及数值 Retry-After、窗口未过期且容量控制器已释放；最多 4 并发，切换固定策略并事务记录旧状态和理由。不会解除 authentication、reservation_underestimated 等其他停止原因，不重置费用，不重跑历史样本。预算或期限变更仍先走 `model_quality.budget`。操作者应先确认旧调度器已结束；跨 campaign 的应用进程管理不由账本替代。

真实 campaign 在派发 worker 前检查 DNS；DNS 失败保留 pending，修复网络后可用相同源码和配置 `--resume`。这个检查不证明 TLS、认证或供应商可用性。已有 wire 的传输失败仍保留未知预留。

新证据将 observed tool 与 successful tool 分开；工具 trace 的出现不代表执行成功。`tool_call_shapes` 只保存固定字段是否出现、未知字段数量和形状检查，不保存参数、provider ID、推理或未知字段名。历史 `read_memory_tool_executed` 指标只代表观察到调用，请用下面的 receipt 审核重新区分成功/拒绝。当前严格 memory rubric 要求恰好一次同 key 的匹配效果；重复写入但最终正确的情况要单独报告，不能由严格失败率推导最终状态错误率。

完成后生成机器可读审核和可移交证据包：

```bash
python examples/summarize_campaigns.py --campaign-dir /absolute/path/completed-run --output /absolute/path/audit.json
python -m model_quality.export --campaign-dir /absolute/path/completed-run --ledger /absolute/path/window.sqlite3 --output /absolute/path/evidence.zip
```

两个命令都可重复指定 `--campaign-dir`。export 持有所选 campaign 文件锁、拒绝非终态和在途账本，保留原 manifest/report、合成公开 receipt、预算/恢复审计和工具源码，并提供逐文件 SHA-256；检测当前密钥字节后才写入新文件。不会导出数据库、诊断日志或推理。源码是导出时版本，各次执行版本以 manifest 中冻结的摘要为准。该工具只用于可信的合成实验目录，不能作为任意用户数据的通用脱敏器。

## 三条优先 lane、摘要评分与源码快照

[并行实验总记录](../../docs/quality/m3-parallel-results-2026-09-12.md)是本轮生产交接入口。引用 24 来源、事件 30 场景、逐字 24 来源共 156 样本在同一调度器中随机交错，仍只有 4 个 worker；这是有界混合调度，不是加权 lane 公平队列。摘要另有 8 场景×2 条件，按事实对象而非字符比较。

在本目录、已配置服务环境的 `PYTHONPATH` 下：

```bash
uv run --project ../../services/ai python -m vibe_learner.prepare_lanes --lane mixed --transport minimax --budget-from /absolute/path/current-budget.json --id your-mixed-batch --output /absolute/path/mixed.json
uv run --project ../../services/ai python -m vibe_learner.prepare_summary --transport minimax --budget-from /absolute/path/current-budget.json --id your-summary-batch --output /absolute/path/summary.json
uv run --project ../../services/ai python -m model_quality --manifest /absolute/path/mixed.json --output /absolute/path/mixed-run --ledger /absolute/path/window.sqlite3
```

`--lane citation|temporal|verbatim` 可单独准备对应矩阵。混合 batch 的 `candidate` 按 lane 映射到 normalized tokenizer、oracle-context、source-binding；映射在冻结的 `priority.py` 中。oracle 仅从本样本真实已提交 seed 原话取回，不是生产策略。source-binding 只在已经提出且参数合法的同 key 逐字写入上绑定原文；不允许拿它替代 summary，也不创造新的写入动作。verbatim 两臂均有相同的 index 兼容，不能和未经兼容的旧 baseline 直接作因果比较。

真实运行生成 `manifest.json` 后、改动任何执行源码前，另开终端捕获逐文件匹配的执行源码：

```bash
python examples/capture_vibe_source.py --campaign-dir /absolute/path/mixed-run --repo /absolute/path/vibe-learner --output /absolute/path/mixed-run/execution-source.zip
```

脚本核对 manifest 中每个源码/锁文件摘要，任意不符便拒绝，不能把新版代码冒充旧版。`model_quality.export` 自动包含该快照并校验内层摘要和当前密钥字节。早期已有 manifest 而源码已改变的批次仍只能保留原摘要和已存在的导出源码；不要伪造补录。复现实验时，在隔离副本恢复记录的 Git revision 和执行快照、安装锁定依赖，再分配新 campaign ID 与有效累计预算；旧 manifest 的过期时间不能直接重用于新模型调用。

只读汇总和来源选择重放：

```bash
python examples/summarize_priority.py --campaign-dir /absolute/path/mixed-run --output /absolute/path/mixed-audit.json
uv run --project ../../services/ai python examples/audit_citation_selection.py --campaign-dir /absolute/path/mixed-run --output /absolute/path/citation-replay.json
```

`mixed-audit` 保留原指标；旧批中未提交却空引用的记录须以 `citation-replay` 的 unavailable 分类解读。离线重放是 selector 算法证据，不是新 domain commit。JSON 事实 exact 也不等于自然语言语义正确率；总记录保留独立于格式的辅助复核及其非独立限制。

最终本地验证：36 项通用测试、15 项领域测试。数据入口检查合成 PDF 文本抽取；seed 失败回归证明保留首个失败 receipt、不会继续派发 query。没有触发应用发布门或修改生产默认值。
