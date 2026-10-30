# 前端测试边界

前端重构按模块运行测试；生产构建和浏览器验收作为独立流程。后端故障注入与进程中断门继续使用原入口，不通过前端测试重复启动数据库。

| 入口 | 边界 |
| --- | --- |
| `npm --workspace @vibe-learner/web run test:tavern:controller` | 完整 Tavern controller 和展示组件行为，注入 API、时钟和草稿存储；切房、迟到结果、分页竞争、轮询清理、终态单调性、取消/恢复交错和幂等身份 |
| `npm --workspace @vibe-learner/web run test:tavern:controller:browser` | 开发服务与截获 API 的 Tavern partial/failed/archive/retry 文案、名册顺序、移动 DOM 流与完成后焦点；无需全量构建 |
| `npm --workspace @vibe-learner/web run test:tavern:order:live` | 真实临时 SQLite/mock 后端：逆序多选、generating 房间刷新、partial 后 child retry，比较预览、名册、服务端 Steps、消息链及 provider 回调次数 |
| `npm run test:web:debug` | 完整 React 组件的 Debug 发布、更新、卸载清理；无学习 controller/API |
| `npm run test:web:workspace` | 快照查询、草稿生命周期与生成 Hook；注入依赖，无网络 |
| `npm --workspace @vibe-learner/web run test:workspace:data` | 只运行首次加载、刷新竞争、失效与重试模块 |
| `npm --workspace @vibe-learner/web run test:resources:live` | 有历史 Room/Run 的真实临时后端：连续 focus、Plan/Study 共享 owner、跨页返回、慢轮询与丢失响应恢复；原始时序和 before/after 见[请求边界 v1](performance/web-resource-reads-v1.md) |
| `npm --workspace @vibe-learner/web run test:workspace:checkpoints` | 保存进度严格解码、结果丢失后的 child 查询、持久身份和切换/卸载 fencing |
| `npm --workspace @vibe-learner/web run test:workspace:checkpoints:browser` | 开发服务上的 OCR 保存片段、刷新、模糊续跑结果、GET 恢复和提交后继续规划入口 |
| `npm --workspace @vibe-learner/web run test:workspace:page-scope` | 物理页输入、非法范围、独立印刷标签 DTO、实际 HTTP 请求序列化与 Setup 提交行为 |
| `npm --workspace @vibe-learner/web run test:workspace:page-scope:browser` | 开发服务上的页范围草稿导航/刷新恢复及物理 100–103 与印刷 70–73 分开显示 |
| `npm --workspace @vibe-learner/web run test:workspace:generation` | 完整生成 Hook 的取消、过期请求、卸载、视图切换、Scene 快照和文档成功流程 |
| `npm --workspace @vibe-learner/web run test:settings:decode` | Settings、工具配置、模型探测、用量统计的严格解码与真实 API 诊断归属；错误读回不重放写请求 |
| `cd services/ai && uv run python -m unittest tests.test_settings_response_contracts` | 临时后端当前 HTTP DTO 交给 Node 中的生产 decoder 验证；Python/TS 共享版本与枚举 fixture |
| `cd apps/web && npx playwright test --config playwright.settings-decode.config.ts` | 开发服务上的畸形响应界面：Settings 不初始化自动保存、字符串 false 不启用工具、用量非法计数不显示为零 |
| `npm --workspace @vibe-learner/web run test:settings:save` | 保存协调器的队列/防抖/失败/恢复原值；完整 Hook 的 pagehide 与卸载，不读取或切片源码 |
| `npm --workspace @vibe-learner/web run test:scene:generation` | Scene 候选生成的文件读取竞争、旧错误、草稿变更、卸载与输入校验；不启动数据库或模型 |
| `npm --workspace @vibe-learner/web run test:scene:dialog` | 生产 Chromium 的模态焦点、Tab/Escape、背景 inert、取消与确认删除后的焦点；需先构建 |
| `npm --workspace @vibe-learner/web run test:scene:draft` | Scene 编辑状态、导入作用域、localStorage 防抖/离页保存；注入存储与时钟 |
| `npm --workspace @vibe-learner/web run test:scene:draft:browser` | Scene 立即离页、返回和完整刷新后的草稿恢复 |
| `npm --workspace @vibe-learner/web run test:browser` | 聚合独立生产浏览器模块；先构建 |
| `npm --workspace @vibe-learner/web run test:scene:rewrite` | Scene 字段重写与草稿协作，覆盖撤销保护、旧错误、切换/导入/卸载与失败不重放；注入模型 port |
| `npm --workspace @vibe-learner/web run test:scene:library` | 场景库读取与本地提交对账、删除 tombstone、选择时序、并发写守卫与卸载；注入 API port |
| `npm --workspace @vibe-learner/web run test:scene:components` | 场景树展示按钮事件隔离、禁用态与编辑内容投影；不初始化领域 controller |
| `npm --workspace @vibe-learner/web run test:persona:generation` | Persona 卡片候选生成、文件竞争、切换/卸载、显式回填与去重、清空确认和数量边界 |
| `npm --workspace @vibe-learner/web run test:persona:generation:browser` | 真实数量输入的名称、1–24 上下限与可选语义；不检查源码字符串 |
| `npm --workspace @vibe-learner/web run test:persona:draft` | Persona 草稿/基线/身份、迟到初始化、未保存确认与事件监听清理 |
| `npm --workspace @vibe-learner/web run test:persona:draft:browser` | 未保存 Persona 输入在拒绝离页后保留，确认后正常导航 |
| `npm --workspace @vibe-learner/web run test:persona:assist` | Persona 单插槽/整体辅助、锁定插槽、提示词手动接受、过期请求与失败不重放 |
| `npm --workspace @vibe-learner/web run test:scene` / `test:persona` | 分别聚合该领域全部无网络 Hook/组件模块；浏览器流程单独运行 |
| `npm --workspace @vibe-learner/web run test:persona:library` | Persona 库查询版本、并发提交对账、后续权威刷新、失败/重复写与离页广播 |
| `npm --workspace @vibe-learner/web run test:persona:persistence` | Persona 保存/重载/删除与草稿实例、后续编辑和 revision 的协作；注入持久化 port |
| `npm --workspace @vibe-learner/web run test:persona:persistence:browser` | 创建请求在途时继续编辑，服务端读回绑定记录并保留新输入 |
| `npm --workspace @vibe-learner/web run test:persona:components` | Persona 库卡片插入、拖拽、载入、内置删除边界及 pending 禁用态；不初始化领域 controller |
| `npm --workspace @vibe-learner/web run test:workspace:mutations` | Plan/Study Unit 写入验证、资源级并发守卫、busy、反馈归属、最新导航回调与卸载 |
| `npm --workspace @vibe-learner/web run test:workspace:recovery` | 操作身份存储/重试策略、完整查询恢复 Hook、过期回复、卸载和 revision 单调性 |
| `npm --workspace @vibe-learner/web run test:workspace:recovery:browser` | 历史 Plan/Session、uncertain 刷新恢复、POST 在途离页后只查询原请求；先构建 |
| `npm --workspace @vibe-learner/web run test:workspace:sessions` | 历史 Session、重复创建、串行章节切换、Scene 快照与导航/卸载边界 |
| `npm --workspace @vibe-learner/web run test:workspace:messages` | learner 发送与恢复协作、lookup 期间去重、revision/附件、admission 拒绝、过期 POST 和自动身份查询 |
| `npm --workspace @vibe-learner/web run test:workspace:commits` | 答题和计划确认的去重、持久化读回、自动续问前置条件、revision 与导航边界 |
| `npm --workspace @vibe-learner/web run test:workspace:continuation` | 自动预处理/续问、注入时钟的 follow-up、暂停/取消、恢复优先与在途答题回调消费 |
| `npm --workspace @vibe-learner/web run test:workspace:libraries` | 学习域 Persona/Scene 库刷新归属、失败保留、实时选择与事件订阅清理 |
| `npm run test:web:reliability` | 领域 decoder/recovery 单元测试与组件测试 |
| `npm run check:web` | Web 类型约束 |
| `npm run style:check` | ESLint/Ruff 既有问题基线及新增/修改代码格式；规则和 CI 见[代码风格门](code-style.md) |
| `npm run build:web` | 生产 Web 构建 |
| `npm run test:acceptance:web-routes` | 构建后启动独立本机服务，以 Chromium 验证路由请求和用户导航 |

首次运行浏览器验收先执行 `npm exec --workspace @vibe-learner/web -- playwright install chromium`。测试启动 `127.0.0.1:3417` 的生产 Web，所有 API 请求均由浏览器截获并返回契约合法的合成响应，不访问运行数据库。结束后测试服务自动退出。

路由请求基线在 `apps/web/tests/browser/route-request-contract.ts`：默认教师、无 Document/Plan/Session/Room、关闭 Debug 展开。每个路由初次请求必须与其清单一致，一次 focus 后每种资源最多请求两次；只能 GET。显式 Debug 展开、已存在资源读回、用户提交和离页取消不属于这份初始清单，需单独验证。

浏览器运行报告写入 `/tmp/vibe-learner-route-report.json`，包含 API 请求记录；失败 trace 位于 `/tmp/vibe-learner-browser-results`。历史 Plan/Session 与在途请求由 `learning-recovery.spec.ts` 单独覆盖。真实设备、IME、屏幕阅读和桌面安装验收见根 TODO。
