# MiniMax-M3 真实生产构建探索式 Smoke Test（2026-09-13）

> 持续记录。发现即写入，避免长任务上下文压缩丢失信息。本文只记录验收证据和改进项；本轮不修改产品实现。

## 范围与环境

- 当前工作树：包含用户已有未提交改动；本轮不覆盖、不整理这些改动。
- Web：`npm run build:web` 成功；Next.js 16.2.3 production build，14 个静态路由完成生成；使用 `next start` 在 `127.0.0.1:3000` 运行。
- Backend：无 reload 的 Uvicorn，`127.0.0.1:8000`；全新隔离 SQLite `/tmp/vibe-m3-smoke-20260913/smoke.db` 与隔离存储 `/tmp/vibe-m3-smoke-20260913/data`。
- Provider：LiteLLM SDK → `https://api.minimax.cn/v1` → `MiniMax-M3`；密钥只来自进程环境，未写入文档或制品。
- 浏览器：Codex in-app browser 的全新应用数据路径；真实页面交互，不使用前端 mock。
- 真实样本：Oxford Reading Tree `Macbeth`（英文叙事）、Terence Tao `Higher Order Fourier Analysis`（英文原生全文本数学）、`Groupes Algébriques Tome 1`（法文内嵌噪声 OCR 文本层）、《巴别塔之后》（中文 297 页全扫描长文档）。
- 测试维度：主流程可用性、UI/UX、语义准确性、模型可靠性、Planning/Study 教学工具调用、持久化/刷新读回、真实用量与时延。

## 探索结果

### 构建与首次配置

- **通过**：production Web build 成功，Navigation Home 可达，九个主入口均出现。
- **通过**：Settings 从隔离后端正确读出 LiteLLM、MiniMax 国内地址和三个 `MiniMax-M3` 模型槽。
- **通过**：Settings 的计划代表请求返回“计划工具请求：可调用”。
- **通过**：Settings 的学习代表请求返回“学习对话：可调用”和“酒馆严格输出：可调用”。
- **通过**：Settings 的设定代表请求返回“人格生成：可调用”和“场景生成：可调用”。
- **观察**：三次分功能验证都会让页面上所有“拉取/验证/能力刷新”控件同时进入全局 loading 状态，即使实际只验证一个模型槽。用户难以判断正在验证哪一项，也无法并行检查其他项。
- **观察**：上游 `/models` 成功列出 8 个模型，但图像输入与联网能力字段均无法识别；UI 如实显示“未知/未读取到”，但首次用户仍缺少“应该手工开启还是保持关闭”的决策说明。
- **UI 问题（用户现场指出，已复核）**：同级卡片中，“计划生成”卡片的标题与描述性文字间距和另外两个卡片不一致。需要统一同级 Card header/title/description 的垂直节奏，而不是只验证控件存在。

### Plan Workspace / 视觉一致性

- **UI 问题**：当前桌面宽视口下主体内容只占左侧约一半宽度，右侧留下大片空白；表单和结果纵向堆叠，未利用可用横向空间。需在大屏检查内容最大宽度、双栏策略和阅读行长。
- **UI 问题**：选中 PDF 后，完整超长文件名在上传按钮和紧邻的“已保留”说明中重复出现，信息冗余并显著拉长控件；建议使用截断名称 + tooltip/详情，并只保留一个权威状态位置。
- **可访问性/自动化问题**：AX 树把“学习目标”显示为有名称的文本框，但按显式 label 定位失败，只能按 textbox role/name 定位；需要核对 `<label for>` / `id` 关联是否真实存在，而不只依赖附近文本或 aria 投影。
- **通过（流程）**：真实 `Macbeth` PDF（92 个 PDF 页）上传、解析、Planning commit、计划历史读回、自动创建 Study Session 与初始化对话均完成；计划 ID `plan-f6bef29e7c`，Session ID `session-6930469bf0`（隔离数据，仅用于本轮证据）。
- **工具调用**：Planning 共 3 轮、8 次工具调用、0 个页面报告问题。第 1 轮 5,058 ms，依次调用 3 次 `get_study_unit_detail` 与 1 次 `read_page_range_content`；第 2 轮 2,423 ms，调用 4 次 `read_page_range_content`；第 3 轮无工具，`finish=stop`，耗时 **84,140 ms**。工具选择表现出先取 Study Unit 详情、再补多个页段的合理分解，但最终组织答案占总时延绝大部分。
- **UX 问题**：规划最终轮持续约 84 秒，页面只显示轮次/调用数与“第 3 轮开始”，没有本轮已等待时间、总耗时、超时边界或“模型正在组织最终计划”的阶段解释。长等待下用户很难区分正常思考、卡死和可否安全离页。
- **UX 问题**：计划已经渲染后，因系统自动创建 Session 并执行初始化 Study Chat，页面顶部仍显示“处理中…”，且计划编辑、展开、开始、完成、重置、历史刷新和删除全部禁用。该跨领域隐式后处理没有单独文案，用户会误以为计划仍未完成；应区分“计划已提交”和“学习会话初始化中”，并只锁定真正冲突的动作。
- **模型内容优点**：计划遵守 5 天、每天约 30 分钟、原文证据、人物视角比较和最终自测要求；结构压缩为 3 个 Study Unit、5 个日程，任务大体可执行。没有把标准 Shakespeare 原剧与该 Oxford 改编本混为同一页码系统。
- **模型语义问题（页码边界）**：计划大量使用书内印刷页码，但未显式说明“页码为印刷页码，不是 PDF 页序”；该文件两者相差约 2 页。抽查确认 `blinding sun` 在 PDF 第 15 页、书内约第 13 页，计划却把该阶段归入书内 `p.14–16`；`An Unexpected Guest` 章节实际从书内 p.45（PDF 47）开始，而计划标题写 `Ch.8（p.47–61）`，遗漏章节开头 p.45–46。其余抽查锚点如 `machine for murder`（PDF 20/书内 18）、`Looks like rain`（PDF 48/书内 46）、`His throat is cut`（PDF 49/书内 47）、`No one could be worse than Macbeth`（PDF 69/书内 67）存在且上下文匹配。结论是内容总体 grounded，但章节范围/锚点页码精度不够稳定。
- **模型语义问题（引文质量）**：计划把 `I'll give you rain!` 在 UI 文本中显示成 `I'll give you rain!` 的同时，PDF 提取实际为排版/OCR 异体 `T’ll give you rain!`；这类字符差异不应被当作“逐字原文”成功。计划还用了 `Were you drunk…?` 等缩略引文，后续需在 Study 中检查引用投影是否给出真实可读来源，而不是只在自由文本写页码。

### Study Dialog / 初始化 Turn

- **通过（持久化）**：自动初始化 Turn 已提交并可由 `GET /study-sessions/session-6930469bf0` 完整读回；revision=1，Turn sequence=1。模型调用了 `read_learning_plan_progress`、`update_learning_plan_progress`、`write_session_memory`，没有 recovery。完成度更新被正确呈现为待用户确认，不直接越权应用。
- **模型/工具行为优点**：初始化回复把两天节奏、当前页段和结尾自测自然串联；读取计划后提出 `schedule-1 -> in_progress`，并写入 session memory，体现了多工具组合而非只生成自由文本。
- **语义/信任问题**：回复对用户说“我已经……在临时记忆里钉下了……”，工具确实执行成功，但该表述与待确认的计划状态挤在同一句中，用户不易分辨“记忆已写入”和“计划进度尚未应用”是两个不同提交边界。建议 UI 以独立 receipt/status 呈现，不让自然语言承担事务状态解释。
- **引用质量问题**：三个 citation 的标题全是 OCR 噪声 `CHAP TE Re`，且都绑定同一个 Section ID，却覆盖 p.14–15、p.22、p.34 三个分散区间。标题没有可辨识章节名，citation chip 对用户几乎不能解释“为何引用这页”。
- **引用相关性问题**：初始化正文主要讨论 p.14–19 与 Day 2 总览，却额外给出 p.22 与 p.34 引用；当前可见回复没有逐条说明这两个页段支持哪一陈述。需要检查 citation-to-claim 对齐，而不只验证页段存在。
- **可访问性问题**：持久化 API 明确含有 `assistant_reply`，视觉截图也能看到教师正文，但 AX 树只朗读/暴露角色动作、delivery cue、focus、引用和待确认进度，没有暴露教师正文。读屏用户可能完全错过对话主内容；这是高优先级的语义可访问性缺陷。
- **UI 问题**：Study Dialog 在宽桌面视口仍只使用约左半屏宽度，右侧大片空白；Conversation 与 Composer 之间又被固定高度拉出很大垂直空白。信息密度既不紧凑也没有形成有意义的双栏，首轮回复、待确认效果和输入框被迫分散在很远的位置。
- **UI 问题**：顶部状态仍显示上一流程的“学习计划已生成”，不是当前 Study Session 的同步/生成状态；页面内另有“状态 已同步”，状态源重复且语义层级不一致。
- **UI 文案问题**：角色动作、delivery cue 与正文的视觉层级较接近，工具派生事件还以“指向当前重点”出现；普通学习者难以区分教师说的话、表演提示和系统工具回执。应对调试/表演信息做更强的渐进披露。

### Study Dialog / 真实取证问答与互动题

- **测试输入**：要求模型实际查阅相关页，用两处原文解释 Macbeth 从接受封号到 Lady Macbeth 推动时的动机变化；明确区分 PDF 页序与书内印刷页码；证据不足应直说；最后给一道不泄露答案的单选题。
- **通过（教学结构）**：回复以两段原文、逐步解释、证据缺口声明和一句话总结组织；首轮在未取到完整 Lady Macbeth 段落时明确说证据不足，没有直接编造缺失引文。
- **通过（互动题安全）**：生成四选一题，提交前没有显示正确答案或解析；选择 B 后显示“回答正确 · 已记录”，选项锁定，`提交答案` 禁用，出现折叠的“查看解析”。题目与前文学习目标一致，干扰项可辨但不是荒谬格式噪声。
- **严重语义错误（页码体系）**：模型明确声称“PDF 第 14–19 页，与本册内文印刷页码 14–19 一致；页码不再区分”，此结论为假。PDF 共 92 页，抽查页脚证明 PDF 页序约比印刷页码大 2（例如 PDF 16 的页脚是 14，PDF 20 的页脚是 18，PDF 48 的页脚是 46）。用户已直接要求区分两套编号，模型仍给出高置信错误，属于来源坐标/工具语义没有可靠传递给模型。
- **严重语义错误（逐引文标页）**：回复把 `blinding sun` 标为印刷 p.14，实际位于 PDF 15、书内约 p.13；把 `Inside his head thoughts raged like a storm...` 标为印刷 p.15，实际位于 PDF 16、书内 p.14；答题后的自动反馈又把 `machine for murder` 标为 p.19，实际在 PDF 20、书内 p.18。三处都呈系统性一页偏移，不是随机拼写误差。
- **优点与局限（语义分析）**：从“预言被动兑现”到“自问是否亲手推动”、再到 Lady Macbeth 外部施压的解释总体忠于文本；但“所以 Day 2 弑君之夜他真正要对抗的不是 Duncan，而是她已经替他下了的决定”属于强解释性断言，未标明是教师解读而非教材事实。
- **工具灵活性与成本问题**：第一次用户问答走了 3 次 provider call；提交本地互动题答案后，系统自动发起新的 Study Chat，累计又观察到 6 次 provider completion 才完成反馈，期间 Composer 与计划动作全部禁用。自动反馈调用了 `read_page_range_content`、`write_session_memory`，能补齐之前的证据缺口，但一次正确答案触发多轮真实模型和记忆写入，成本、时延及用户控制感不透明。
- **教学连续性问题**：答题后自动反馈最后提出“下面哪一个细节……”的问题，但没有提供选项、输入提示或新的 `interactive_question` 卡片；紧接着只出现普通 Composer。它看起来像一道未完成的选择题，用户不知道应自由作答还是点击“再来一题”。
- **UI/状态问题**：提交互动题后页面先立即显示“回答正确 · 已记录”，同时全页又进入“更新中”、禁用 Composer/计划动作，直到额外模型反馈完成。正确性记录和教学续接是两个阶段，却没有拆分进度；用户容易把额外等待误认为评分尚未落盘。
- **材料预览严重问题**：点击 citation chip 后 Material Preview 正确打开、标题与 `14 / 92` 页码控件可见，后端 `/documents/{id}/file` 返回 200；但等待 2.5 秒后页面仍为纯白，没有 PDF 内容、loading 或错误提示。控制台两次警告 `Dependent image isn't ready yet`。用户无法核对引用，citation 的核心信任链在本次生产构建/浏览器中不可用。
- **材料预览 UI 问题**：Drawer 标题用超长文件名并在窄标题栏截断；只保留下载、上一页、下一页、关闭图标，图标语义依赖 tooltip/AX。白屏时底部仍显示“教材材料 14 / 92”，造成“已定位成功”的假象。
- **通过（刷新读回）**：直接刷新 `/study` 后，3 个 Turn、已选 B、`回答正确 · 已记录`、折叠解析、citation chips、待确认 `schedule-1 -> in_progress` 均从后端恢复；确认应用后页面显示“计划已更新”，待确认卡消失。该范围支持普通刷新持久化。
- **恢复/a11y 问题**：刷新后的初始 AX 树再次遗漏三个 Assistant Turn 的正文，只保留动作、工具名、citation 和互动题；已提交题目的四个 radio 只暴露为无名称的 `0/1/0/0`。随后点击“确认应用”触发重渲染，正文和 radio 描述又全部出现。相同持久化数据在 hydration 前后提供不同的可访问名称，说明问题不是模型字段缺失，而是前端初始渲染/可访问性同步不稳定。
- **状态文案观察**：刷新后顶栏从旧的“学习计划已生成”恢复成“数据服务已连接”；确认进度后又变为“计划已更新”。这证明顶栏是一次性 action notice，不是稳定的 Session 状态，刷新会丢失上下文语义；页面另有“状态 待开始/已同步”，容易把网络、领域状态和 toast 式结果混在一起。

### Persona Spectrum

- **测试输入**：新建空草稿，要求精确 4 张卡片；关键词限定 Eleanor、严谨温和的 Shakespeare 阅读导师、称呼“小林”、事实/解释分离、引用原文、不编页码、纯师生关系、无共同经历、苏格拉底追问和不泄题。
- **通过（模型契约）**：一次真实 M3 请求约 16.4 秒后返回精确 4 张卡片；摘要、关系、称呼与 4 个插槽均可应用到当前编辑区，手工补名称后创建为用户 Persona `Eleanor`，列表即时读回。
- **通过（边界遵循）**：输出明确保持纯师生关系、拒绝虚构共同经历，称呼为“小林”；教学方式覆盖逐行细读、事实/解释两栏、苏格拉底追问与不泄题，和用户要求高度一致。
- **语义扩写风险**：模型把“以文本为证”强化成“以原典为唯一权威”，并主动加入 Johnson、Arden、Cambridge、Norton 等版本/注释体系。它们并非输入所需，在当前无联网能力证据、也没有绑定具体版本的场景中，会制造不必要的权威感和未来不可兑现的“当场一起查版本”承诺。Persona 生成应区分必要人格特征与未经请求的领域装饰。
- **分类质量问题**：四张卡中有两张都标为 `教学方法`，把“逐行引证规范”和“苏格拉底式追问”堆在同类；“鼓励与纠错风格”只映射为 `鼓励策略`，纠错维度没有独立槽。精确数量通过不等于覆盖维度合理。
- **UI 问题**：点击“应用到当前编辑区”回填摘要、关系、称呼和插槽，但名称仍为空；结果正文和摘要已经反复使用 `Eleanor`，用户仍需滚回基本设定手工补名才能保存。建议提案显式提供可接受/可编辑的名称，或在应用时给出明确未填字段提示并聚焦该字段。
- **UI/UX 密度问题**：页面同时展开基本设定、5+ 插槽/运行时完整提示词、生成卡片、生成结果、卡片库，主次动作（AI 重写、新建、复制、重新载入、保存、清空、添加、整理、导入/导出）集中出现。Persona 库虽默认折叠，Card Library 默认展开；独立体验仍显著过密，`UX-DENSITY-PERSONA-001` **不能关闭**。
- **UI 缺少选择性应用**：生成结果只有一个“应用到当前编辑区”，无法逐卡接受/拒绝、合并重复分类或查看 diff。旁边的“应用前清空摘要、关系、称呼、参考提示和全部插槽”是高影响批量行为，却与普通生成控件同层级，仅以 checkbox 表达；误选后缺少应用前摘要。
- **文案问题**：空草稿提示“填写名称后保存即可创建”，但真实保存还包含摘要/关系/称呼/插槽的大量隐式默认与生成内容；“即可”弱化了用户需要审查人格运行时提示词和外部权威陈述的责任。

### Scene Setup

- **测试输入**：要求生成“深夜山顶天文台”，只允许两层（观测室、资料室）；观测室指定望远镜/红色弱光灯/可移动星图架，资料室“只有纸质星图与记录桌”；窗外阴天、不可见星星；禁止第三空间、人物行为、魔法和未知设备；层级偏好=2。
- **通过（结构）**：一次真实 M3 请求约 39.5 秒返回 `MiniMax-M3 · 2 节点`，场景名、摘要和两层均正确；没有添加第三层、地下室、屋顶或人物行为，也没有声称能看见星星。应用后使用“另存为新场景”成功保存为“深夜山顶天文台”，按钮切换为“更新已保存场景”。
- **严重约束遵循问题**：资料室要求“只有纸质星图与记录桌”，模型仍添加 `暖黄台灯`、`抽屉柜`，并在记录桌内部再加入台灯、铅笔筒和空白记录页；观测室又添加 `穹顶开启缝`、`观测控制台`。其中控制台属于明确禁止的未知设备扩写。层级数量正确掩盖了物体白名单违约。
- **语义一致性问题**：输入说“窗外阴天，不能直接看见星星”，摘要和穹顶节点能保持云层遮蔽；但又写“保持暗适应以备云缝开合”和“穹顶可开缝”，引入没有必要的未来可见性叙事。模型倾向把静态场景补成完整世界设定，弱化用户的最小约束。
- **生成预览问题**：应用前的结果卡只显示名称、摘要和“2 节点”，不展示 9 个物体、规则或标签。用户无法在覆盖当前编辑树前发现多出的控制台、台灯和抽屉柜；只有全量应用后才能审查。应提供结构 diff、物体计数和约束冲突摘要。
- **UI/UX 密度问题**：默认场景载入后 5 层/5 物体全部展开，根节点编辑器也展开；每层重复“添加子层/添加物体/加入节点库/删除/展开编辑器”，随后还有场景元数据、生成器、节点库和已保存场景。虽然可复用节点库与已保存场景默认折叠、删除已实现独立流程，但初始页面仍极长，缺少搜索/筛选和结构总览，`UX-DENSITY-SCENE-001` **不能关闭**。
- **危险动作层级问题**：每个层和物体的“删除”按钮与普通“加入节点库/展开编辑器”等动作并排重复出现；即使最终删除使用模态，入口仍没有视觉危险色/次级菜单分层的证据。为避免真实删除，本轮未执行最终确认。
- **状态文案问题**：进入页面显示“已加载本地保存场景”，但隔离数据中载入的是名为“审计测试教室”的预置/兼容示例；普通用户无法判断这是示例、自动草稿还是自己的已保存记录。

### Tavern Workspace

- **创建/持久化通过**：使用 Aurora + Eleanor、已保存场景“深夜山顶天文台”和一条边界开场白创建房间 `Macbeth 文本证据研讨`；创建后 revision=0、开场白作为导演消息 #1，房间列表显示两位参与者。隔离 Room ID `tavern-6563d154e5ee`。
- **空状态恢复缺陷**：首次进入 Tavern 时房间列表明确为 0，页面却短暂请求浏览器残留的旧 room ID `tavern-0b2e4caa7f74`，Room/runs/recovery 三个 GET 均 404，随后同时显示合理空状态和“无法打开这个酒馆，请稍后重试”。旧选中房间不存在时应静默清除指针并回到空状态，不应对全新后端显示失败。
- **单聊通过**：Aurora 一次真实调用约 4.2 秒完成。她明确说 Tavern 无法直接核对教材原文、不会为页码背书；保持“两间房/阴天没有星光/无共同过去”约束，并能读到当前场景的两个房间与物体。
- **边界优点**：与 Study 不同，Tavern 没有 Document 绑定；模型没有假装拥有原文访问权限。这条事实边界比 Study 的页码高置信错误更可靠。
- **场景扩写传播问题**：Aurora 忠实复述了 Scene 快照里多出的控制台、暖黄台灯和抽屉柜。Tavern 对已提交 Scene 的忠实并不能纠正 Scene 生成时的白名单违约；UI 需要在上游保存前支持审查，否则扩写会自然传播为“世界事实”。
- **Facilitated 调度通过（基础）**：选择两位目标后，UI 明确显示 `Aurora → Eleanor`，服务器按名册顺序分别提交 #5/#6，revision 从 1 到 2，Reliability Details 保持 0 待恢复。生成中可见每位状态，且“取消接收结果”如实说明已发出的 provider 请求可能继续到超时。
- **Facilitated 时延**：Aurora 步约 6.2 秒，Eleanor 步约 20.5 秒；两步串行总等待约 26.8 秒。不同角色同模型/短输出的尾延迟差异明显，页面只展示当前角色，不展示已耗时或下一步预计。
- **严重对话顺序问题**：隐藏引导要求“Eleanor 先区分事实与扩写，Aurora 再给建议”，但服务器固定调度为 Aurora → Eleanor。Aurora 先说“Eleanor 区分事实与扩写之后，我跟一步……”，把尚未发生的发言当作已发生；Eleanor 随后才分类，并在末尾又要求 Aurora 接下一步，但本轮已经结束。模型服从引导文本胜过真实 schedule，造成明显时序错乱。Composer 应在引导与已选 schedule 冲突时提示/重写，或把明确顺序作为 server-owned prompt truth。
- **严重来源归属错误**：用户要求区分“最初明确给出”与“生成器额外补出”，但 Room 只有提交后的 Scene snapshot，没有原始生成输入/字段 provenance。Eleanor 仍把“圆顶穹顶、穹顶开启缝”归为用户最初给出，实际上用户没有给出；又把“资料室整套家具”归为扩写（这部分正确）。系统让模型回答它没有证据的 provenance 问题，且没有触发“不知道”。
- **动作一致性问题**：Eleanor 的动作是“把星图架旁的铅笔轻放回桌面”，Scene 只把铅笔筒放在资料室记录桌，星图架在观测室；动作跨房间移动物体且暗示了未发生的拿起/归还。场景 grounding 仍不足以约束细粒度动作连续性。
- **轮询/重复请求候选**：Facilitated 运行期间后端日志在多个轮询周期内出现紧邻的重复 `GET /tavern/rooms/{id}/runs?limit=50`，并伴随 diagnostics POST。需用浏览器 network trace 定量确认是否同一页面存在两个 polling owner；本轮不据此关闭或直接判定 `PERF-WEB-DEDUPE-001`。
- **UX 优点**：Tavern Block 命名与信息结构较清晰；Participant Roster 的目标顺序、生成中/已回应状态、Reliability Details、消息序号和 revision 都比 Study 的跨阶段状态更可解释。

### Sensory Tools

- **可见契约**：生产页面显示 Planning 5/6、Study 31/32；图像页范围工具因当前模型未启用多模态而禁用并给出理由，其余工具按练习、记忆、会话、关系、计划、感官、场景分组。
- **UI/UX 密度问题**：37 个工具及说明全部在首屏后的单一长页展开，没有搜索、筛选、只看关闭/不可用、按风险筛选或分组折叠。用户查找 `write_session_memory` 对应开关需人工滚过大量项目；`UX-DENSITY-SENSORY-001` **不能关闭**。
- **批量动作风险**：每个分组都把“全开/全关”放在普通标题旁，没有批量影响计数、二次确认、撤销或保存状态说明；Study 的 `删除物体` 等有状态/危险能力与只读工具一样仅用普通 checkbox 表示。批量/危险动作没有与普通编辑分层。
- **状态表达问题**：不可用的图像工具 checkbox 仍显示 Value=1（已选但运行时不可用），分组计数显示 5/6、31/32；“用户偏好启用”和“当前运行能力不可用”混在一个控件，用户无法一眼判断模型切换后会自动生效还是需要重新保存。
- **术语负担**：`投射 PDF 图形候选`、`归一化坐标`、`当前投射 PDF` 等实现术语直接暴露给一般用户；页面缺少按学习任务解释“何时会用、成本/风险、是否需确认”的渐进披露。

### Model Usage

- **当前真实账单投影**：页面显示 18 次记录、197.2K total tokens（168.0K input / 29.2K output）。按功能：Planning 3 次 / 48.9K；Study Chat（包含 Tavern）13 次 / 141.4K；Setting Assist 2 次 / 6.9K。
- **成本问题（Planning）**：首个 5 天短书计划一次用户动作使用 48.9K tokens，其中最终无工具轮单次 27.3K（15.5K in / 11.8K out）。对 92 页儿童/青少年改编读物而言成本和 84 秒最终轮明显偏高。
- **成本问题（Study）**：初始化对话 2 次合计约 22.2K；一次取证+互动题问题 3 次合计约 36.4K；仅提交正确答案后的自动反馈又用 5 次、约 **67.9K tokens**。答题反馈成本约为最初整次 Planning 的 1.39 倍，且用户在提交前看不到会触发这一链路。
- **成本问题（Tavern）**：一轮 direct 约 3.9K；两角色 facilitated 分别约 5.1K / 5.9K，总计约 11.0K。该短对话尚未接近 `PERF-TAV-LIVE-001` 要求的六人格、四目标、长对话，不能关闭该票。
- **审计遗漏**：Settings 中真实执行的代表请求（Planning 1 次、Study+Tavern 2 次、Persona/Scene 1 次，共观察到 4 次 completion）没有出现在逐次调用明细或 18 次总计中。页面把“调用次数/总 Token”呈现为全局审计，但排除了连接验证的真实 provider 消耗；需要明确范围或纳入账务。
- **分类问题**：Tavern 的三次 provider 调用全部计入“章节对话”，逐次明细无法区分 Study 与 Tavern，和产品页面/领域边界不一致；用户不能评估 Tavern 成本。
- **日期/时区问题**：当前本地时间为 09/13 03:xx（Asia/Shanghai），逐次明细显示 2026/09/13，但日汇总柱状图与表格归入 `2026-09-12` / `09-12`。UTC 日界线与本地明细混用且无时区标签，会误导每日预算。
- **UI 优点**：图表有可访问名称与分段 token 文本，表格列清晰，逐次记录按时间倒序，真实 provider reported token 能被用户检查。
- **UI 可用性问题**：页面没有刷新按钮、时间范围/功能筛选、导出或成本估算；长明细表在单页无限延伸。对探索测试或排查异常调用，只能手工扫描。
- **数学/法文请求后的刷新复核**：页面现显示 34 次记录、**463.0K tokens**（414.8K input / 48.2K output）。Planning 为 19 次 / 314.7K，正好覆盖 Macbeth 48.9K + Tao 两次 211.9K + 法文 53.9K；这证明 Tao 第一次最终 502 的 3 次 provider call 仍逐次计费并进入审计，失败请求没有被总量漏掉。
- **“调用”口径仍不完整**：逐次明细能完整列出生成/repair 的 provider calls，却没有 operation/request ID、round、tool/repair/失败状态或所属 plan；用户必须用时间戳手工推断 03:49 的三条属于失败请求、03:50–03:51 的十一条属于成功重试。34 次“调用次数”是 provider completions，不是 34 次用户动作，标题与帮助文案应明确。
- **实时刷新行为观察**：页面没有显式刷新按钮，但重新导航到 Model Usage 会重新取数并显示最新两次法文 Planning；这属于整页进入时刷新，不支持原地观察长任务成本增长。

### 用户手册对照

- **覆盖优点**：网页手册有稳定目录与直达链接，覆盖 mock/real、Document/Planning/Study、Persona/Scene/Sensory、Tavern、恢复、数据隐私、桌面安装和校验；明确真实模型会发送教材片段/对话/角色设定并可能产生费用，也如实说明桌面签名/OCR 尚未完成。
- **流程过时**：手册说“查看计划，创建并打开章节对话”，实际本轮生成计划后系统自动创建 Session 并执行隐藏 prelude，且 Plan 页在这一阶段锁住多个操作。手册没有说明该自动行为、额外模型调用和等待成本。
- **功能状态过时**：手册仍称“计划的整体修订、差异确认与回滚尚未提供”，当前 Plan Workspace 已显示 `修订计划 · 版本 0`，仓库也有 Plan revision/CAS 功能。需要按当前实现核对到底哪些修订/回滚能力可用，避免把已提供功能写成缺失。
- **引用说明不足**：手册只说“点击引用查看对应教材页”，没有解释 PDF 页序与书内印刷页码可能不同，也没有说明 citation title 可能来自 OCR Section。当前 Material Preview 白屏会直接阻断手册承诺的路径。
- **设置说明不足**：首次真实模型路线只写模型名/API Key/地址/保存/拉取能力，没有解释三个模型槽的继承、三种“验证模型与当前功能”、能力未知时如何决定多模态/联网开关，以及验证请求本身会产生 provider 调用但当前不进用量审计。
- **恢复说明不足**：手册对“结果未确认前不要重发”讲得清楚，但没有覆盖本轮见到的 stale Tavern room 指针 404、Study hydration 丢可访问名称、citation PDF 白屏，以及正确答题后评分已记录但后续自动生成仍在运行的双阶段状态。
- **关闭结论**：本轮完成真实浏览器下的 Settings、教材、Plan、Study、Persona、Scene、Tavern、Sensory、Usage 与 manual 对照，但尚未完成桌面安装、全平台和 mock 主流程，且手册有上述过时/缺口；`DOC-USER-001` **保持开放**。

### 中文扫描 PDF / 切页持续性、超时与 Debug 可观察性

- **真实样本**：`巴别塔之后 语言及翻译面面观 (乔治·斯坦纳) (z-library.sk, 1lib.sk, z-lib.sk).pdf`，297 个 PDF 页、约 23.6 MB；`pypdf` 抽查前 30 页均无文本层，属于真实全扫描长文档。隔离 Document ID `doc-8d354803bd`。
- **通过（后端切页持续）**：约 03:34:32 从 Plan Workspace 启动处理，切换到 Model Usage 后，同一后端 `request_id=4c3bf3117b144bb787157cf22a91ded0` 仍约每 6–9 秒连续产生处理事件；03:39 后 `GET /documents` 仍显示 `status=processing`。页面导航没有中止服务器侧 OCR，也没有观察到第二个处理请求，基础“离页继续”成立。
- **严重恢复/可见性问题**：返回 Plan Workspace 后，运行中的中文文档及“正在解析教材”状态完全消失；教材文件控件为空，生成按钮禁用，页面只显示旧 Macbeth 计划。学习目标文本还在，但计划场景从本次明确选择的“不使用场景库场景”恢复成旧值“深夜山顶天文台”。用户看不到后台仍在运行、已耗时、是否可安全等待或如何重新绑定结果，并可能误以为任务丢失后重复上传/处理。
- **状态所有权问题**：文件选择、目标、Persona、Scene 和后台 operation 的恢复行为不一致：目标与 Persona 保留，文件和 operation 丢失，Scene 回退旧值。表单局部持久化制造了“这是同一个未完成任务”的假象，但实际缺少 document/operation identity。
- **Debug 严重可观察性问题**：返回 Plan 后打开全局 Debug，当前页面诊断已累计 1,000+ 条事件，首屏主要是大量低层 `request_started/response_headers/request_finished`；`调试总览`仍固定显示旧 Macbeth 文档、旧的已完成 Process/Plan stream，完全没有正在 OCR 的 `doc-8d354803bd`、297 页总数、当前页、OCR 速度、已耗时或取消入口。即使后端任务确实持续，普通用户和调试者都无法从 UI 关联它。
- **Debug 信息架构问题**：浮窗“当前页面”混入 server `page_path=null` 的请求，并把事件 JSON 默认展开在文档总览之前；每次返回 Plan 又产生多组近同时的 GET/diagnostics 事件。对长流程而言，transport 噪声淹没了 operation/stage 进度，应优先呈现 active flow/operation，再按需展开 HTTP 事件。
- **OCR 进度缺口**：启动处理时 Plan 只显示“正在解析教材…”，`Document` API 在处理中保持 `page_count=0`、`debug_ready=false`。对于 297 页扫描件，没有总页数、已完成页数、OCR fallback 状态、速率、预计时间或警告；当前实现只能靠后端日志心跳判断活性。
- **多次离页/并发持续证据**：随后又在 Plan、Model Usage 之间切换，并并发完成 Tao 解析/两次 Planning 与法文 736 页解析/Planning；中文同一 stream 仍从 180/297 推进到 270/297，没有新 operation，也没有因其它模型调用停住。服务器持续性较强，但该事实仍只在 API/SQLite evidence 中可见。
- **原页视觉基准**：抽查 PDF 1、5、10、15、20：PDF 1 是中英双语扉页；PDF 5 为“第二版序”且使用罗马页码 viii/ix；PDF 10 右页是目录，列出六章、后记、参考书目、索引；PDF 15 为第一章正文印刷 8/9，PDF 20 为印刷 18/19，正文夹有英文引文。样本同时包含封面、序言、目录、正文、脚注和双语引文，适合检查 parser/模型是否把材料类型与页码体系混为一谈。
- **严重终态失败（全部 OCR 后才超时）**：Process 从 03:34:32 运行到 04:15:17，约 **40 分 45 秒**。它已完成 297/297 页 OCR，随后成功报告 `margin_patterns_detected`、96 个 heuristic Sections 与 816 chunks；仅在最终 Harness lifecycle 阶段触发 `harness_runtime_wall_time_budget_exceeded`，stream 以 error 终止。昂贵且不可增量复用的逐页工作全部完成后，固定 operation wall-time gate 才否决产物。
- **严重数据/恢复影响**：失败后 Document 从 `processing/pending` 变成 `failed/failed`，但权威投影仍为 `page_count=0`、`chunk_count=0`、`study_unit_count=0`、`debug_ready=false`；`document_debug_records` 没有该 Document。也就是说 297 页 OCR、96 Sections、816 chunks 对 UI、Debug、Planning 都不可读，无法从终点续做 cleanup/commit，只能再次从第 1 页开始付出同样成本。同配置重试很可能再次撞同一 wall-time gate，本轮不做无意义重试。
- **预算设计问题**：wall-time budget 把“供应商/模型执行上限”和“本地 297 页 OCR 总时长”放在同一 operation 生命周期内，却没有按页 checkpoint、阶段独立预算或在 admission 时依据页数预判不可完成。对真实长扫描件，系统允许用户等待 40 分钟并显示持续心跳，最后才告知整个请求不可能提交。
- **错误语义不足**：stream 只返回内部码 `harness_runtime_wall_time_budget_exceeded`，Document 只显示泛化 `failed`；没有告诉用户 297 页其实已读取、失败发生在提交边界、结果未保存、重试大概率仍失败、建议拆分 PDF/调整 OCR 路线或联系管理员。原本已缺失的进度 UI 因最终失败变得更危险。
- **中文语义测试被基础设施阻断**：由于没有 committed debug/planning context，本轮不能诚实声称已验证中文 OCR 内容、作者正文/第二版序/目录/双语引文区分或 M3 中文 Planning。该未覆盖不是模型内容通过，而是 Document workflow 对 297 页真实扫描样本不可用。
- **真实 UI 失败可见性**：OCR 失败后返回 Plan Workspace，仍只显示空教材控件、保留的中文学习目标和当前法文计划，没有中文 Document 名、40 分钟耗时、297/297、失败原因或重试建议。顶部反而显示另一条 Study decoder 的“历史学习会话格式异常”，跨领域错误覆盖了 Document 失败；用户无法知道中文任务已经终止。

### 英文全文本数学 PDF / Document 解析与 Planning

- **样本选择更正**：按用户确认改用 Terence Tao 的 `Higher Order Fourier Analysis`；202 个 PDF 页、约 2.3 MB。抽查 PDF 10/30/100 页均有约 1.9K–2.3K 可提取字符，视觉页包含正文、公式、Remark/Exercise 与印刷页码，适合作为与全扫描中文书互补的全文本数学样本。`The Elements of Real Analysis` 抽查除封面外无文本层，不再作为本轮“全文本”对照。
- **通过（解析性能）**：真实 production backend 从 `parser_started` 到 committed terminal 约 8.94 秒；202/202 页覆盖，489 chunks，Harness generate/decode/validate/commit 全通过，`section_source=toc`，未使用 OCR。即使中文扫描 OCR 同时运行，文本 PDF 仍能快速完成，基础并发没有阻塞该流程。
- **状态语义错误**：所有抽查正文页均 `extraction_source=text`、`used_ocr=false`，Document 最终却返回 `ocr_status=failed`。对不需要 OCR 的成功文档，“failed”会让用户/Debug 误判降级失败；应有 `not_required`/`not_used` 等独立状态，而不是把 OCR 未执行表达为失败。
- **严重结构降级**：PDF 自带目录清楚列出 §1.1–§1.7 与 §2.1–§2.3，解析器也报告 `toc_section_count=9`，但 course outline 只保留 9 个一级入口（封面、前言、Chapter 1、Chapter 2、文献等），所有十个数学小节都没有成为子 Section。最终只有两个可规划 Study Unit：Chapter 1 为 PDF 12–139（128 页），Chapter 2 为 140–189（50 页），`subsection_titles=[]`。这会迫使 Planning 用页段工具重新发现教材内部结构，并削弱精确目标定位。
- **数学文本质量问题**：提取结果能保留大部分变量和公式，但出现不可见控制字符（如 `n \u0002→ e(ξn)`、求和符号附近的 `\u0003/\u0004`）、字符间异常空格、上下标线性化及断词；例如正文被投影为 `n \u0002→ e ( ξn )`，公式块与自然语言混排。普通检索词仍可工作，但逐字引用、公式朗读、变量绑定和模型对表达式的精确解释存在风险。
- **文件名边界说明**：本样本通过真实 `/documents` multipart API 注入隔离 production backend，临时上传名为 `vibe-m3-hofo.pdf`，因此标题显示为 `vibe-m3-hofo`；这不是产品从原文件名推断标题的结果，不将其计入 UI 文件名质量。
- **Planning 第一次真实请求失败**：目标限定 4×45 分钟、只学 §1.1、每次含定义/命题、公式解释和练习，并要求区分 PDF/印刷页码、不得假装覆盖整章。M3 第 1 轮 3.16 秒，合理调用 `get_study_unit_detail` + `read_page_range_content`；第 2 轮 5.52 秒返回内容但 `plan_proposal_schema_invalid`；随后 strict repair 禁用工具，13.92 秒后仍为 `plan_model_invalid_json`，stream 以 502 / `not_committed` 结束。
- **模型可靠性/成本问题**：上述一次用户动作共 3 次真实 provider call，分别 5,679、9,865、11,508 tokens，总计 **27,052 tokens**，最终没有计划产物。严格修复调用的 token 最大，却仍无法产出 JSON；当前一次 bounded repair 对 M3 的格式漂移不够可靠。
- **失败证据可观察性问题**：失败 operation 有完整 stream terminal 和 `not_committed` evidence，但 `GET /documents/{id}/planning-trace` 返回 `has_trace=false`、round_count=0、tool_call_count=0。Debug 无法查看模型实际无效输出、schema 字段错误或修复输出，只暴露根路径 `$` 与 `invalid_json`，不足以区分 Markdown 包裹、截断、控制字符污染或契约理解错误。
- **受控重试成功但方差极大**：完全相同目标只更换 `client_request_id` 后成功提交 plan `plan-52907a8ba5`。这次共 **11 轮、14 次工具调用、约 80.1 秒**；工具为 `get_study_unit_detail`×3、`read_page_range_content`×8、`estimate_plan_completion`×2、`revise_study_units`×1。第一次请求 2 个工具后即尝试输出并两次 JSON 失败，第二次却连续取证到第 10 轮才输出；相同输入的控制流、成本和结果可靠性差异很大。
- **严重成本问题**：成功重试产生 11 次 provider call，累计 178,468 input + 6,374 output = **184,842 tokens**。加上第一次失败的 27,052 tokens，同一学习目标直到获得一个计划共消耗 **211,894 tokens**。成功请求每一轮都重新携带增长后的上下文，末轮单次输入达到 21,806 tokens；对只覆盖约 19 个印刷页的四次课计划明显过度。
- **工具灵活性优点与风险**：M3 能识别 parser 把十个小节压成两个大 Unit 的问题，主动调用 `revise_study_units`，把目标范围细分为 4 个可规划单元（PDF 12–30），并排除 Chapter 2/文献。这是本轮最强的自适应工具行为证据；但该工具会真实修改 Document：`updated_at` 从 19:45:36 变为 19:51:41，原 4 个 Study Unit 被 7 个 LLM Unit 替换，Section 投影也随之变化。Planning 的取证动作因此不仅生成计划，还改变后续所有计划/Study 的共享教材结构，UI 没有预览、diff 或独立确认。
- **Study Unit 修订仍不准确**：新 Unit 把 `§1.1.2 Single-scale` 标为 PDF 24–30 / 印刷 13–19，但原书该节实际从 PDF 22 / 印刷 11 开始；修订遗漏定义与开头两页，却在 PDF 30 纳入已经开始的 §1.1.3。所有新 Unit（包括 Front Matter、Bibliography）又都写成 `unit_kind=chapter`。模型成功修订结构不等于边界和分类正确。
- **计划语义优点**：最终四次课严格聚焦 §1.1，能区分 PDF 页序与印刷页码（稳定差 11 页），覆盖 linear/quadratic phase、渐近等分布、Weyl 分解、recurrence 和 single-scale；绝大多数命题/练习编号在对应实际页段可核对，未假装覆盖整章。
- **计划语义错误**：第 1 次课锚定 PDF 12–13，却要求完成实际位于 PDF 15 的 Exercise 1.1.1，并把定义等式 `(1.1)`称为“Weyl 等式”；真正的 Weyl criterion 是后面的 `(1.2)`。第 4 次课又跳过 §1.1.2 的 PDF 22–23 开头定义，却声称学习 single-scale regime。来源页段与任务并未完全闭合。
- **公式精度问题**：Exercise 1.1.23 原文下界含 `≫_{d,s} ε^{O_{d,s}(1)}N`，计划简写成 `≫_{d,s,ε}N`，把 ε 的量化依赖吸收到下标；对概念摘要尚可，但不满足用户“一个公式解释/不要杜撰公式”的精确教学口径。应明确标为 schematic bound，或保留原式。
- **内部一致性问题**：today task 要画“只有四格”的关系图，却列出 `linear phase → quadratic phase → asymptotic → single-scale → recurrence` 五个节点；四次课也都没有给出可核查的 45 分钟内部时间分配，只在 Overview 声称“4×45 分钟”。
- **Plan Workspace 数学呈现问题**：production UI 可完整读回该 API 生成计划，历史切换正常；但每课把页码、定义、长公式、练习和复盘压成一整段混排文本，公式只用 Unicode/ASCII 线性化，无独立公式块或可复制原式。宽桌面仍是窄单栏，数学符号密集段落换行后难扫描，且用户不能逐条核对“定义/公式/练习/时间”。

### 法文内嵌 OCR 文本层 PDF / Document 解析

- **真实对照样本**：`Groupes Algebriques Tome 1 Geometrie Algebrique- Generalites- Groupes Commutatifs (M.Demazure- P. Gabriel) (z-library.sk, 1lib.sk, z-lib.sk).pdf`，736 个 PDF 页、约 36 MB；页面肉眼清楚，但文本层本身来自质量不稳定的 OCR。隔离 Document ID `doc-7ea56bf13a`，Process stream `stream-daf3bfe4f7d9`。
- **通过（吞吐与基本结构）**：真实 production backend 约 83.9 秒完成，生成 1,460 chunks、102 个 heuristic Sections、44 个 Study Units，其中 42 个可规划。绝大多数页走内嵌 `text`，第 3 页因低质量再次触发运行时 OCR；说明混合来源与单页 fallback 路径可以完成，而不是整书失败。
- **严重文本质量问题**：内嵌 OCR 把法文重音、希腊字母、结构符号和箭头大量误认；肉眼可读的代数几何页面进入规划上下文后已不是可靠的逐字材料。该样本比“无文本层扫描件”更危险：系统会优先信任既有文本层，但“存在文本”不等于“文本可信”。
- **严重结构语义问题**：解析结果产生大量由正文碎片或 OCR 噪声构成的伪标题，例如 `Si la projection`、`Josn Irs`、`Gx Gx`、`Re M,, donc que`、`3 Hx Sp, k. Alors Go`，甚至把人名 `MICHIEL HAZEWINKEL` 当成章节。42 个可规划 Unit 的数量和覆盖校验均通过，但用户会在 Outline、Planning 与 citation title 中把这些字符串误认为教材结构。
- **Unit 投影自相矛盾**：多个 Unit 的权威 `page_start/page_end` 与摘要内声称的页段不一致，例如 Unit 17 为 255–266、summary 却称 255–258；Unit 23 为 359–373、summary 称 359–366；Unit 29 为 506–534、summary 称 506–529；Unit 38 为 650–665、summary 称 650–657。模型若同时看到结构字段与自然语言摘要，会得到互相冲突的来源边界。
- **Harness 证据边界**：generate/decode/validate/commit 的结构检查全部通过，只证明产物形状、页覆盖与提交成立，不能证明标题是真实标题、重音/公式忠实或 Unit 边界语义正确。Debug/UI 应把结构有效与内容置信度分开，不应以绿色 lifecycle 状态暗示 OCR 语义已验收。
- **下一步窄范围取证**：选择视觉上可核对的 `2.1 Définition` 附近页段做 M3 Planning/Study，对照原页检查法文重音与术语恢复、公式/箭头忠实度、PDF 页序与印刷页码，以及模型是否会拒绝或显式标注 OCR 噪声。
- **原页基准**：已用原 PDF 视觉核对 PDF 100–102。Définition 2.1 的正文在 PDF 100 / 印刷 70；其后关于 sous-schéma ouvert 与 “Par abus de langage” 的结尾在 PDF 101 / 印刷 71；Proposition 2.2 已从 PDF 101 / 印刷 71 开始；Corollaire 2.3 已从 PDF 102 / 印刷 72 开始。原书在 structural morphism 处使用自身记号 `Sp k`，纤维积是以基底对象为下标的 `X ×_Y Y′`，不是以 morphism `g` 为下标。
- **真实 M3 Planning（成功提交）**：用法文目标明确限定 PDF 100–103 / 印刷 70–73、两次 30 分钟、保留重音/箭头、噪声不确定即声明、不得修订 Study Units。M3 第 1 轮 4.67 秒调用 `read_page_range_content` 与 `get_study_unit_detail`，第 2 轮约 30.09 秒直接输出；无 repair，plan `plan-4528baba97` committed，Document 的 44 Units 未被改写。
- **成本与上下文膨胀**：仅两轮就消耗 20,128+884 与 24,749+8,166，共 **53,927 tokens**。在模型调用前，heuristic baseline 已为整本 736 页/42 个可规划 Units 建出 84 个 schedule、132 个 schedule chapter，尽管用户只要求 4 页；最终 committed plan 又完整携带全部 44 个 Study Units 与 42 条 unit_progress。窄范围计划仍被整书结构显著放大。
- **模型恢复噪声的优点**：能从伪标题 `Si la projection` 背后的页段找回真正的 `n° 2 Schémas algébriques` 与 Définition 2.1；法文重音如 `algébrique`、`présentation finie`、`fidèlement` 基本保留；正确区分 PDF 100/印刷 70 和 PDF 101/印刷 71；也遵守“不调用 `revise_study_units`”。
- **严重公式/记号忠实度问题**：原书写 structural morphism 到 `Sp k`，模型一边把 `Sp k`列为待核疑点，一边在标题、任务与解释中统一改成现代记号 `Spec k`，却没有标注这是规范化而非逐字原文。原书纤维积为 `X ×_Y Y′`，模型反复写成 `X ×_g Y′`，把 morphism 名当作基底下标；这恰好违反用户要求的“符号/箭头不确定就不发明”。
- **工具验证名不副实**：模型确实调用了 `read_page_range_content`，但拿到的仍是污染后的内嵌 OCR chunk：`produit fibré X xg Y)’`、`py: zX > Sp k`、`25x / zd` 等。它没有调用页面图像工具，最终却在 thinking 中声称“Now I have a clear picture”。对于“文本层存在但不可靠”的样本，重复读取同一文本层不是独立核验；需要让模型知道来源质量，并允许/引导按原页图像交叉验证。
- **严重页码定位错误**：计划称 produit fibré 段落在 PDF 101 / 印刷 71，实际已在 PDF 100 / 印刷 70 底部；称 Proposition 2.2 位于 PDF 102、Corollaire 2.3 从 PDF 103 开始，实际分别从 PDF 101 / 印刷 71、PDF 102 / 印刷 72 开始。M3 修复了大段 OCR 文本，却仍在用户明确要求双页码的情况下产生系统性一页偏移。
- **约束/教学结构问题**：用户要求“两次 30 分钟”，最终 schema 只有 **1 个 schedule**；两次课被塞进一个长 `focus`，`today_tasks` 的最后一项只写“Session 2 的准备”，没有第二次课独立任务、状态或 30 分钟内部时间分配。标题还把 `1.11 Proposition` 作为第一个 schedule chapter，虽称上下文，却超出“仅学习 n° 2”的窄范围。
- **语言体验观察**：用户用法文提出目标，最终计划主体是中法混排（中文指导语 + 法文术语），而非保持法文学习界面；这可能来自中文产品/persona 默认，不一定是事实错误，但需要明确语言偏好与输出语言控制。长 `focus` 里又用英文拼写 `exercise`，降低语言一致性。
- **验证边界再次暴露**：strict schema 和 `plan_grounding_and_references` 均通过，因为全部 chapter 都引用了父 Unit 允许的同一个粗粒度 Section ID、页码也落在 Unit 100–146 范围内；这些检查未能发现纤维积下标错误、`Sp`→`Spec` 未标注规范化、双页码偏移或“两次课被压成一次 schedule”。
- **真实 Plan Workspace 呈现**：刷新历史后法文计划即时出现并可切换，重音字符在 AX/视觉中没有乱码；但页面进度直接显示 `0 / 1`，把“两次课”投影成一个可开始/完成的原子任务。两次课的拆分只藏在同一段超长 `focus` 中，用户不能分别推进。历史卡又把中法混排 Overview 截断，关键的 OCR 不确定性与页码声明落在省略号之后。
- **法文 Study 首轮可靠性失败**：为该计划创建 Session `session-81abbe14f9` 后，发出法文取证问题，要求逐字引用 Définition 2.1、精确抄写纤维积和两条箭头、区分确定/不确定文本并提供 citation。真实 M3 在约 26.6 秒内做了 3 次 completion，后两次 output 都恰好达到 3,072 tokens，最终为 `chat_model_invalid_payload`；operation 返回 `uncertain`、`safe_to_retry=false`、`not_committed`，Session revision 仍为 0 且无 Turn。Harness 只有一个 generate failed attempt、无 checks、无 repair evidence，无法看出原始输出差在哪个字段。
- **失败成本**：上述没有任何可见回复的请求仍消耗 **34,425 tokens**（9,156 + 13,820 + 11,449）。两次输出撞到相同上限强烈提示复杂工具/严格嵌套输出容易因截断而失效；但用户和 Debug 只看到笼统 `invalid_payload`，看不到 token cap、截断或字段路径。
- **uncertain UI 首段表现较好**：进入 Study 后先显示“回复校验失败，已停止更新页面以保护会话记录”，随后显示“本次对话需要确认”“请查询本次请求，不要重复执行”，Composer 禁用。点击查询后仍诚实显示“暂时无法确认……请稍后继续查询，不要重新发送”，没有把失败内容当成功 Turn。
- **严重恢复冲突/额外费用**：离开 Study 再返回时，前端却在同一个空 Session 上自动发起新的 `study-prelude-*` operation；它绕过了仍为 terminal `uncertain / safe_to_retry=false` 的原请求，以相同 admitted revision=0 成功提交 revision=1。自动 prelude 又调用 M3 两次、约 **21.9K tokens**。即用户遵守“不要重复发送”，页面恢复本身仍产生新的 provider side effect 与费用，operation fencing 只挡 same-key replay，没有挡同 Session 的不同 key 自动续接。
- **错误传播为权威陈述**：自动 prelude 从错误 plan theme 继承 `Spec k` 与 `X ×_g Y′`，再次告诉用户“`Sp k` 其实应当是 `Spec k`”，并用两条 citation 支撑。原页视觉检查证明书中就是 `Sp k`、纤维积下标为基底 `Y`；Planning 阶段的 OCR 误判进入 committed Plan 后被 Session system prompt 和后续教师回复反复放大，形成跨工作流的高置信错误链。
- **前后端契约/恢复严重问题**：prelude 在后端已 committed，API 可读回 revision=1、Turn sequence=1、两个工具调用和两条 citation；但返回 Study 页面时前端报“历史学习会话格式异常，已停止载入以保护记录”，显示“创建会话”并完全隐藏这条已提交 Turn。Debug 只有 `GET 200` 后的 `decode_failed`，route=null、无字段路径/decoder contract/response 摘要，无法定位是哪一投影不兼容。由此形成“后端有已提交对话，前端认为暂无会话”的分裂状态。
- **累计审计**：完成法文 Study 失败与自动 prelude 后，Model Usage 从 34 次 / 463.0K 上升为 **39 次 / 519.3K**；五次新调用合计约 56.3K，全都归类为“章节对话”，但审计无法区分一次失败用户请求和一次页面恢复自动请求。

## 待继续覆盖

- 中文内容语义、Planning 与 Study：必须先解决/调整 297 页 OCR 的 operation wall-time gate，或提供可恢复 checkpoint；当前同配置重试只会重复 40 分钟成本。
- 桌面安装包、Tauri shell、退出/重启、系统 PDF viewer、IME 与跨平台焦点顺序；本轮验收的是 production Web build，不外推到桌面制品。
- Tavern 的六 Persona、四 target、长 transcript、停止/重试和真实 live-provider 性能门；本轮只覆盖 direct 与双 Persona facilitated。
- Material Preview 需在至少另一浏览器/桌面壳独立复核白屏；当前 in-app browser 证据足以判定本环境失败，但不是跨平台结论。
- 对本报告中的模型语义结论做独立复放/人工双人核对，尤其是数学公式、法文原书旧记号与 Tavern 调度顺序。

## 综合判定

- **核心 happy path 有条件成立**：production build、真实设置、短英文 Document→Plan→Study、Persona、Scene、Tavern、Sensory、Usage、历史读回均能走通；M3 能组合多种 Planning/Study 工具，也会在结构过粗时主动修订 Study Units。
- **不满足“真实教材可信教学”整体放行**：Macbeth citation 页码系统性偏移且预览白屏；Tao 同目标先失败后以 211.9K tokens 成功、公式与页段仍错；法文计划把 OCR 错符号写入 committed Plan 并跨工作流强化；中文长扫描在 297/297 后整体超时丢失产物。
- **模型/契约可靠性不足**：同输入 Planning 控制流方差大；复杂 Study 问题连续输出触顶后 `invalid_payload`；strict schema/Harness grounding 多次通过却不覆盖公式、页码、语言、课次或教材结构语义。
- **成本与用户控制不足**：本轮可见审计到 519.3K tokens；一次正确互动题续接约 67.9K，一次 4 页法文 Plan 53.9K，一次无可见回复的法文 Study 34.4K，页面恢复又自动花约 21.9K。UI 缺少动作前成本提示、按 user operation 聚合、round/repair/失败归因和可靠取消边界。
- **恢复有亮点但存在关键裂缝**：Session/Turn 刷新读回、Tavern 持久化和 uncertain 防重复文案有明确优点；但 Plan 离页丢活动 Document、uncertain 后页面重入自动发起不同 key prelude、后端 committed Turn 被前端 decoder 拒绝、Debug 无字段路径，都会造成“后端状态与用户所见分裂”。

## TODO 复核结论

- 本轮**没有修改 `TODO.md`，没有关闭任何条目**。
- `UX-DENSITY-PERSONA-001`：默认折叠有进展，但缺搜索/筛选、选择性应用、危险批量动作分层与完整焦点验证，保持开放。
- `UX-DENSITY-SCENE-001`：复用区折叠与删除模态存在，但默认树仍过长、缺搜索/结构总览，删除入口层级与生成 diff 不足，保持开放。
- `UX-DENSITY-SENSORY-001`：分组清楚，但 31/32 Study 工具、全开/全关、不可用能力与危险能力仍混层，缺搜索/筛选，保持开放。
- `DOC-USER-001`：Web 手册覆盖面较广，但自动 prelude/费用、当前 revision 能力、页码体系、Settings 验证和失败恢复说明与实现不一致，且未做桌面安装验收，保持开放。
- `STUDY-OP-RECOVERY-UX-001` 与 `REL-DESKTOP-001` 的相关风险得到新证据，但本轮没有覆盖各自完整关闭标准；不应借 smoke test 部分通过提前关闭。

## 状态口径

- `通过` 只表示本轮明确覆盖的具体检查通过，不外推到其他样本、平台或模型。
- `观察` 是可复现或现场可见的改进候选；后续按证据补严重度、步骤和影响。
- 历史 M3 报告只作为背景，不计入本轮通过分母。
