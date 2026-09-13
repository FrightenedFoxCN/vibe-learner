# MiniMax-M3 Planning 新版本复测（2026-09-13）

## 范围与口径

- 被测版本：`ae5989e`（`fix(planning): bound evidence flow and repair M3 output`）。
- 目标：在独立 production Web build、无 reload 后端、隔离 SQLite/存储中，以真实 MiniMax-M3 API 和真实 PDF 复测 Planning。
- 样本：Terence Tao《Higher Order Fourier Analysis》英文全文本数学 PDF；Demazure–Gabriel《Groupes Algébriques Tome 1》法文噪声 OCR 文本层 PDF。
- 本轮只修改验收文档，不修改产品实现。提交自带探针、合成样本或作者运行记录只作为背景，不计为本轮独立通过。
- 对照基线：`docs/acceptance/m3-production-smoke-2026-09-13.md` 中旧 production smoke 结果。

## 新版本预期修复边界

- Planning 提示从“反复细化目录”收敛为一次关键证据工具轮；工具后强制输出，减少上下文重复和工具预算耗尽。
- `read_page_range_content` 返回实际已覆盖页、`truncated` 与 `next_page_start`，避免把请求范围误当成已核验范围。
- 每个 Study Unit 只注入一个最多 240 字符的代表性摘录，作为有限内容提示而非整章摘要。
- 仅在标题、页范围或 Section 证据明确表明切分错误时允许 `revise_study_units`；长单元或缺少子标题不再构成重写依据。
- 明确限制 `today_tasks` 数量、`focus` 长度和 JSON 引号，降低 M3 schema/repair 失败率。

## 实时观察日志

### 环境

- `npm run build:web` 成功：Next.js 16.2.3 production build，14 个静态路由完成生成；使用 `next start` 在 `127.0.0.1:3000` 运行。
- 后端为无 reload Uvicorn，`127.0.0.1:8000`；隔离 SQLite `/tmp/vibe-m3-planning-retest-20260913/retest.db` 与隔离存储 `/tmp/vibe-m3-planning-retest-20260913/data`。
- Runtime：`litellm` → `https://api.minimax.cn/v1` → `MiniMax-M3`，超时 120 秒；API key 仅来自进程环境，不写入证据。

### Tao 配对复测

- **首次完整尝试仍失败**：保持页面不离开、目标与旧版一致（4×45 分钟，只覆盖 §1.1；每次包含定义/命题、公式解释、练习；区分 PDF/印刷页码；不得假装覆盖整章），最终 502 `plan_model_invalid_payload`。内部失败为 `plan_proposal_schema_invalid:schedule.0.unit_id:unknown_ref`，operation `learning-plan-op-cf0efcc71715458a` 为 `not_committed`，无 Learning Plan。
- **边界收敛但 schema 可靠性未修复**：UI 显示 2 个模型轮次；第 1 轮调用两次 `read_page_range_content`，第 2 轮无工具并收束输出，没有旧版 11 轮工具循环，也没有调用 `revise_study_units`。然而最终输出引用了不存在的 Study Unit ID，repair 后仍失败。
- **成本较旧首次失败反而上升**：本次完整失败尝试实际发生 3 次 provider completion：8,648 + 22,807 + 6,249 = **37,704 tokens**（第一轮、第二轮、schema repair）；约 147.2 秒。旧版同目标首次失败为 3 calls / 27,052 tokens，因此调用数相同，tokens 增加约 39.4%，时延也超过 120 秒设置所暗示的单次等待预期。
- **UI 与审计少算 repair**：Plan Workspace 的“生成进度”显示“轮次 2 / 调用 2”，调用细节只有两轮（约 30,913 ms 与 107,555 ms）；Model Usage 实际记录 3 次 completion。repair 的第 3 次、6,249 tokens 与约 30.9 秒对用户不可见。
- **失败 trace 仍不足**：Harness `plan_generation` 只有一个 generate failed attempt、0 checks，duration 147,152 ms，错误只到 `schedule.0.unit_id:unknown_ref`；`GET /documents/{id}/planning-trace` 返回 `has_trace=false`，成功的两次页读取、repair 输入/结果和模型究竟使用了哪个错误 ID 均无法事后复核。UI 顶部反而显示“教材处理失败”，把已成功 committed 的 Document 与 Planning schema 失败混为一谈。
- **同目标第二次成功，成本显著下降但非提交内探针水平**：2 provider calls、30,506 tokens、约 50.4 秒，operation committed 为 `plan-54d126c93b`；相比旧版成功重试 11 calls / 184,842 tokens，tokens 降约 83.5%。第一轮自然选择 `get_study_unit_detail` + `read_page_range_content`，第二轮直接输出，无 repair、无 `revise_study_units`。但本轮从首次完整尝试到成功仍花 **68,210 tokens**；若计入专门做跨页测试的中断请求，Planning 累计为 76,928 tokens。
- **§1.1 范围仍被错误截短**：计划 overview 声称“仅覆盖 §1.1”，唯一 schedule chapter 却锚定 PDF 12–25、content slice 12–15，并写“§1.1 确切终止页与 §1.1.2 标题待学习时回查”。原页显示 §1.1 从 PDF 13 / 印刷 2 开始，§1.1.2 从 PDF 22 开始，而 §1.2 到 PDF 37 / 印刷 26 才开始；因此 PDF 26–36 的 §1.1 内容被漏掉，Exercise 1.1.23（PDF 30）也不在锚点范围内。bounded evidence 避免了虚构细分，但会在关键范围未核实的情况下提交“覆盖 §1.1”的不完整计划。
- **起始页偏移一页**：today task 把“§1.1 引言”写为 PDF 12–15 / 印刷 1–4；原页视觉核对显示 PDF 12 只是 Chapter 1 标题页（印刷 1），§1.1 正文从 PDF 13 / 印刷 2 开始。计划同时正确指出 PDF 14 页眉为印刷 3，说明不是整本偏移未知，而是锚点选择不精确。
- **公式命名较旧版改善**：计划把 (1.1) 作为渐近等分布定义相关公式，没有再错误称为 Weyl equation；PDF 14 原页确认 (1.1) 是 vague convergence 的定义式。关于 Exercise 1.1.23 的 ε 依赖、旧版“四格/五节点”问题，本计划因范围截短而没有覆盖，不能算修复通过。
- **四次课仍投影为一个任务**：API/UI 只有 1 个 schedule、1 个 schedule chapter、进度 `0 / 1`；四次 45 分钟只在标题/focus 中用自然语言概括，不能逐次开始、完成或复盘。`today_tasks` 只细化第一次学习，后 3 次没有独立任务与时长边界。
- **显式“不使用场景”未生效**：Plan Workspace 选择器显示“不使用场景库场景”，提交计划却绑定了完整“深夜山顶天文台 / 观测室” scene profile，UI 也显示“场景 观测室”；随后自动创建的 Study Session 继续继承该场景。这不是模型风格选择，而是用户选择与提交投影不一致。
- 核对点：首次成功率、时延、provider calls/tokens、工具选择、是否调用 `revise_study_units`、repair/trace 可见性；Exercise 1.1.1、公式 (1.1)、§1.1.2、Exercise 1.1.23 的 ε 依赖、四格/五节点、四次 45 分钟投影。

### 法文噪声 OCR 配对复测

- **形式成功、语义失败**：真实 736 页解析约 55 秒；Planning 2 rounds / 2 provider calls / 62,297 tokens / 约 34.9 秒，committed 为 `plan-5c2baa9258`；第一轮调用 `read_page_range_content` + `get_study_unit_detail`，第二轮直接输出，无 repair、无 `revise_study_units`。但最终计划读取了错误物理页并把错误定义作为教学中心，不能按用户场景视为通过。
- **成本相对旧版回退**：旧版同目标为 2 calls / 53,927 tokens；新版本增加 8,370 tokens（约 +15.5%）。法文 Document 有 44 个 Study Units，新版本为每个单元注入代表性摘录可能使初始上下文增大；本轮尚不能只凭相关性断言因果，但需专项测量 request chars/tokens。
- **工具页码体系误用**：用户明确写 PDF 100–103 / 印刷 70–73，模型 trace 却推理“tools likely refer to printed pages”，选择物理 70–73 对应的 `study-unit:4`，而不是读取物理 100–103。最终 `anchor_page_start/end` 和 `content_slices` 均提交为 70–73，违反 Planning 契约中“所有页码均为从 1 开始的 PDF 物理页”的约束；严格 schema/invariant 没有拦截。
- **Définition 2.1 被替换为另一概念**：计划声称定义包含 a) `quasi-compact`、b) `quasi-séparé`、对角态射 `Δ_{X/Y}: X → X ×_Y X`。原页 PDF 100 / 印刷 70 实际为：`Un k-schéma X est dit localement k-algébrique (resp. est dit k-algébrique) si le morphisme structural p_X : X → Sp k est localement de présentation finie (resp. est de présentation finie).` 原页没有所声称的 a)/b) 或对角态射。模型虽在文字中承诺“精确保留”，教学任务本身完全错误。
- **旧记号与命题序号继续失真**：计划未保留核心旧记号 `Sp k`，反而要求抄写不存在于目标页的 `×_Y`/`Δ`；today task 把 Définition 2.1 放到印刷 71（实际印刷 70），把 Proposition 2.2 放到印刷 72（实际从印刷 71 开始），并虚构“Proposition 2.5, p.73”（原页 PDF 103 / 印刷 73 是 Proposition 2.4；Corollaire 2.3 从印刷 72 开始）。
- **OCR 不确定性标注不能补救错误证据**：模型列出 `fidélement`/`fidèlement`、`méme`/`même`、`diagog` 等疑点，看似遵守目标，但这些提示建立在错误页段/错误定义上；“声明不确定”并不等于正文已被原页核验。
- **计划标题泄露解析噪声**：唯一 schedule 标题为 `Alors l'application canonique`，直接沿用错误 Study Unit 的 OCR 句片；UI 仍显示 `0 / 1`，两次 30 分钟塞进一个 focus，和旧版相同。
- **production trace 违反自身数据口径**：成功计划的 `GET /documents/{id}/planning-trace` 返回完整 `thinking` 与 `assistant_content`，包含用户目标、教材推理、错误摘录和最终原始 JSON；这与提交内 `summary.json` 的 `provider_reasoning_committed=false`、`raw_book_text_committed=false` 声明冲突。工具 arguments/results 虽标为 redacted/content-free，但完整 reasoning 仍可从 API 与全局 Debug 读取，需重新界定留存、隐私和版权边界。
- **再次自动 Study prelude**：法文 Planning 提交后，未点击“开始”也自动创建 Session 并发生 2 chat calls / 21,002 tokens；需与 Tao 的 4 calls / 48,736 tokens 合并评估 P0，而不能算入 Planning 成功成本。
- **自动 prelude 提交到错误 Study Unit**：法文计划唯一 schedule 引用 `study-unit:4`，自动创建的 Session `session-224a7a7d0d` 却绑定 `study-unit:2`（PDF 11–36 的目录/前置材料），并已 committed 1 Turn。该 Turn 用中文讲 `TABLE DES MATIÈRES`，citation 指向 PDF 11–12，还继续把错误的“quasi-compact/quasi-séparé Définition 2.1”强化进教学；用户未开始课程就获得与计划不一致的持久状态。
- 原页视觉基准：PDF 100 / 印刷 70 使用旧记号 `Sp k`，纤维积为 `X ×_Y Y′`；Proposition 2.2 从 PDF 101 / 印刷 71 开始；Corollaire 2.3 从 PDF 102 / 印刷 72 开始。

### Production UI / 任务持续性

- **离页会中断而非持续（已复现）**：通过 Plan Workspace 上传 Tao 并启动生成；Document 在约 11.3 秒后 committed。Planning 已向 MiniMax 发出真实请求时切换到 Model Usage，前端自动调用 Document 与 Planning 两个 stream 的 cancel endpoint。Document 因已完成而保留，Learning Plan operation `learning-plan-op-61fa592dc6c8467e` 最终为 `interrupted / learning_plan_interrupted`，没有计划提交。
- **已花费但没有产物**：MiniMax 请求仍完成并进入审计，1 call、8,023 input + 695 output = 8,718 tokens；Plan History 为空。中断边界本身可防止晚到输出提交，但用户仅做普通导航便丢失正在进行的工作和已发生费用。
- **跨页状态不可见**：Model Usage 初次进入显示 0（请求尚未完成）；全局 Debug 显示大量请求时间线，但首屏没有“另一个页面的 Planning 正在运行/因离页中断”的聚合状态。返回 Plan Workspace 后按钮恢复为“生成计划”，没有中断、费用或恢复提示。
- **Planning 成功会自动启动昂贵 Study prelude**：Tao 重试提交后，仍停留在 Plan Workspace、未点击“开始”，前端自动创建 `session-e7b29f4481` 并调用 Study Chat。真实审计为 4 chat completions、48,736 tokens；最终 Session revision 仍为 0、turns 为空。用户只要求生成计划，却在无可见回复的情况下承担接近本次成功 Planning 1.6 倍的额外 tokens。
- **累计成本口径**：截至 Tao 成功及其自动 prelude，10 次 completion、125,664 tokens；其中 Planning 6 calls / 76,928 tokens，自动 Study 4 calls / 48,736 tokens。Plan Workspace 只展示本次成功 Planning 的“调用 2”，无法解释此前失败、中断、repair 与自动 Study 的合并成本。
- **用户指出的 Settings 卡片错位仍存在**：在同一 production viewport 中，`计划生成`、`学习对话`、`设定辅助` 三卡的 DOM/CSS 都声明 `15px / 22.5px` 标题、`4px` grid gap，但实际 layout rect 不同：计划生成标题/描述高 25.04/21.73 px，另外两卡为 22.5/19.20 px；因此计划生成描述基线低约 2.54 px、标题+描述块高约 5.08 px。视觉截图与测量都确认不是文案换行造成，疑似浏览器 text autosizing / 容器上下文差异。该 UI TODO 不能关闭。
- **Navigation Home 卡片未复现同类错位**：九宫格中前三个功能卡的标题与描述起点视觉一致；本轮精确问题位于 Settings 的“连接与模型分配”三张模型卡，而非首页入口卡。

## 修复优先级（复测后）

### P0：数据已提交但用户状态分裂，或昂贵长任务结果整体丢失

1. **自动 Study prelude / 重入重试会在无用户显式开始时产生高额费用且可能提交错误状态**：Tao 自动发生 4 calls / 48,736 tokens 后仍 0 Turn；法文自动发生 2 calls / 21,002 tokens，并把计划的 `study-unit:4` 错绑为 Session `study-unit:2`、提交了目录段 Turn；旧版还复现 uncertain 后重入以不同 operation key 再次触发。
2. Study Chat 后端已 committed 的 Turn 被前端 decoder 拒绝，导致服务端/用户可见状态分裂。（已修复：Session decoder 现读取共享 Study Tool Manifest 名称，字段级失败位置进入 content-free 诊断。）
3. 297/297 页 OCR 已完成后才命中总 wall-time，全部解析产物不可读、不可恢复。

### P1：教材可信度、Planning 可靠性与费用控制

1. **生成中普通导航会自动取消 Planning**；真实 provider call 仍可能完成并计费，但产物不提交，且跨页无运行/中断/费用提示。本轮已以 8,718 tokens 无产物复现，列为 P1 首位。
2. **严格验证只保证 schema，不保证教材语义**：法文计划读取 PDF 70–73 代替 100–103，却成功提交为 70–73，并把另一概念冒充 Définition 2.1；应在工具层、页码契约和语义 eval 共同阻断，而不是依赖 prompt。
3. Planning/Study 的 PDF 页码、印刷页码、数学公式与法文旧记号错误会直接污染教学内容；Tao 还把 §1.1 截到 PDF 25，漏掉 PDF 26–36。
4. 噪声 OCR 文本层被当作可靠正文；模型对同一噪声文本“重读”不能替代原页图像核验。
5. **M3 schema/repair 仍不可靠且观测口径分裂**：本轮首次完整 Tao 以 `unit_id:unknown_ref` 失败；UI 显示 2 calls，但用量审计记录 3 calls，repair 与成功工具结果不进入可回放 Planning trace。
6. **Planning trace 留存边界与文档声明冲突**：production API/Debug 持久化完整 provider thinking 与原始输出，需先决定是否允许、如何脱敏和谁可访问，再谈独立 replay。
7. 单一用户动作的 provider 调用与 token 未聚合，动作前无成本提示；新 Tao 首次完整失败已花 37,704 tokens，另有离页中断 8,718 tokens；法文成功又花 62,297 tokens。
8. Material Preview 白屏，使 citation 无法由学习者核对。
9. Tavern facilitated 调度与选择顺序不一致。
10. Plan Workspace 的“不使用场景库场景”没有约束提交结果，计划与自动 Session 仍绑定全量默认场景。

### P2：信息架构、视觉一致性与可发现性

1. 同级功能卡片的标题—描述间距不一致，尤其“计划生成”卡与另外两卡。
2. 多次课程被藏在一段 `focus` 中而只显示一个进度原子；宽屏利用和长文本扫描性不足。
3. Persona Spectrum、Scene Setup、Sensory Settings 的密度、筛选与危险动作层级。
4. Model Usage 的时区、分类、筛选、导出，以及 Manual 与当前实现不一致。

## 最终判定

- **不放行真实教材 Planning 的语义可信度**。新版本已把工具循环显著收敛，Tao 成功重试从旧版 184,842 tokens 降到 30,506 tokens，且不再误称公式 (1.1)；这是明确改善。但相同 Tao 目标首次仍以错误 Unit ID 失败，repair 不可见；成功计划又漏掉 §1.1 的 PDF 26–36。法文计划读取了错误物理页，把完全不同的定义作为教学中心，却通过 schema/invariant 并 committed。
- **不放行跨页/自动启动可靠性**。普通导航会取消 Planning，已花 provider 成本却没有产物；Planning 成功又会在未点击“开始”时自动发起 Study，且法文案例提交到错误 Study Unit。
- **本轮总审计**：14 provider completions / 208,963 tokens；Planning 8 calls / 139,225 tokens，自动 Study 6 calls / 69,738 tokens。明细为 Tao 离页中断 1、Tao 完整失败 3、Tao 成功 2、法文成功 2、Tao 自动 Study 4、法文自动 Study 2。
- **待办已分流**：Settings 模型卡、自动 Study、离页取消、committed read-back、PDF 页范围应用约束、trace/usage、场景绑定、OCR checkpoint、Material Preview、Tavern 顺序及课程进度投影进入根 [`TODO.md`](../../TODO.md)；教材语义、页码/范围/时长质量、工具与 repair 成本、噪声 OCR 原页核验分别进入 [`MQ-04`、`MQ-05`、`MQ-09`](../quality/TODO.md)。本报告保留验收事实，不再作为状态真源。

## 建议实施顺序

1. **P0-1：禁止未显式开始的 Study provider 调用**；生成计划只提交 Plan，不自动创建/调用 Session。若产品坚持 prelude，必须由用户动作触发、绑定计划唯一 schedule Unit、显示预计成本，并对 same-key recovery 做单一状态机。
2. **P0-2（已完成）：修复 Study committed/read-back 与前端 decoder 的状态一致性**；自动恢复仍须遵守原 operation 的 query-only 边界。
3. **P0-3：让长 OCR 在阶段性产物上可恢复**，总 wall-time 不能在 297/297 后抹掉全部结果。
4. **P1-1：把物理 PDF 页范围变成服务端约束**：用户显式 PDF 100–103 时，工具参数、schedule anchor/content slice 必须落在 100–103；模型输出 70–73 应 invariant fail，而不是 committed。
5. **P1-2：建立原页视觉/专家语义 gate**：先覆盖数学边界与公式、法文旧记号/箭头/定义，schema success 不能算教材成功；OCR 文本重读不得当作独立核验。
6. **P1-3：统一 provider call/repair/trace/usage 口径**：每个用户 operation 聚合轮次、工具、repair、tokens、最终产物；失败也保留安全的字段级 evidence，同时停止无政策的完整 reasoning 留存。
7. **P1-4：Planning 任务跨页持久化或明确阻止离页**；至少在导航前说明会取消并展示已发生费用。全局 Debug 应有活动任务摘要与恢复入口。
8. **P1-5：修复“无场景”选择和 Plan→Session Unit 绑定**；两者应作为提交前的应用 invariant，而不是模型可选语义。
9. **P2：拆分多次课程进度原子、修复 Settings 卡片 text autosizing/基线、改善长 focus 扫描性与 Model Usage 筛选导出**；之后再独立复核 Persona/Scene/Sensory/Manual 的现有关闭标准。
