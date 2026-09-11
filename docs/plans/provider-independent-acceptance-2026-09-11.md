# Provider ownership 独立验收（2026-09-11）

结论：`PERF-WEB-PROVIDER-001` 的现有路由 ownership 和恢复范围通过独立复核，可以关闭这一项；不据此关闭平台/网络综合恢复、真实模型质量或 Planning 修订待办。

独立验收智能体未参与既有产品实现，复查路由清单和 layout 所有权，复跑已有浏览器证据，并新增两项对抗场景。没有修改产品代码、访问用户业务数据库或调用真实模型。

## 环境与证据

- 源码 HEAD：`5117bc3c64425e1777cb6ce795700f4db91a5e2f`。
- 主智能体在当前 HEAD 完成 `npm run build:web`（含 TypeScript）后，独立智能体在新生产构建 `R4NvcnDWh8WLl9x6TOx9t` 上重新运行限定 18 项；manifest 包含 `/manual/page`。先前既有构建的通过记录被这次新构建验收替代。新增 `.spec.ts` 在 Web tsconfig 的 `**/*.ts` 范围内，纳入 `check:web` 及构建类型门。
- 独立 Next 生产服务 `127.0.0.1:3417`，Playwright Chromium，每测试全新 browser context。业务 API `127.0.0.1:18999` 全部由浏览器拦截为合成契约数据，无业务服务连接。
- 命令：`npm exec --workspace @vibe-learner/web -- playwright test tests/browser/route-ownership.spec.ts tests/browser/learning-recovery.spec.ts tests/browser/provider-independent.spec.ts`。
- 最终结果：**18 passed，15.1 秒**。原始请求与测试结果见 [JSON 证据](../acceptance/provider-independent-2026-09-11.json)。完整临时 Playwright 报告为 `/tmp/vibe-learner-route-report.json`。
- 首次新测试误以为 Plan 有手册直达链接，两个测试因此等待超时；已修正为实际 Navigation Home → Manual 导航后通过，不是产品缺陷。最初 sandbox 禁止本机监听，获自动授权后运行。

## 核对与覆盖

`LearningWorkspaceProvider` 仅位于 `(learning)/layout.tsx`，根布局持有不初始化学习数据的缓存及独立 Debug Provider。扫描实际 page 文件得到 10 个顶级页面；请求清单全部覆盖，加 404 共 11 个入口。旧 TODO “十个顶级页面”口径已过时：旧测试含 404，新增手册后共 11 个测试入口。

| 场景 | 实际验证 |
| --- | --- |
| 11 个入口逐一冷启动及 focus | 请求集合精确等于冻结清单；全部 GET；focus 后每资源最多 2 次；无 pageerror。包括 `/manual`，只请求 runtime settings |
| Plan → Study → Settings | 共用学习 owner，不重复初始化；离开后 focus 不请求学习数据 |
| Plan 草稿经 Settings 返回 | 学习目标和 PDF 草稿可见保留 |
| 历史 goal-only Plan/Session | 已提交回复、计划及未发送草稿跨路由恢复，无新生成 POST |
| 未准备章节 + uncertain + 刷新 | 查询原操作，发送禁用；手动查询 committed 后恢复 Session，清除 pending，无 POST |
| 聊天 POST 在途离页 | 服务端提交后返回只查询原 client request ID；全程只有首次 1 个 POST |
| 新独立场景：迟到学习快照 | 阻塞 documents GET，Plan → Home → Manual 后再释放响应；连续 3 次 focus 无请求；返回 Plan 正常，无 POST |
| 新独立场景：恢复查询失败 | uncertain 经 Plan → Home → Manual → Study；离页 focus 无请求；操作查询注入 internetdisconnected 后保留同一身份、禁用发送；完整刷新再查询 committed，只 GET 并清除 pending |

允许资源列表的唯一源为 `apps/web/tests/browser/route-request-contract.ts`。本次没有为迁就实现放宽任何清单；新增可复跑场景在 `apps/web/tests/browser/provider-independent.spec.ts`。

## 明确边界

- 冷启动清单使用默认教师及空业务数据，Debug 保持关闭；已存在资源另由恢复场景覆盖。没有将用户操作、Debug 展开、流取消请求混入冷启动白名单。
- uncertain 是 **Study Chat 操作**在 Plan/Study 共享 owner 及离页时的恢复。没有宣称独立验收了 Learning Plan generation operation 的 uncertain 全矩阵。
- 网络失败是浏览器路由故障注入，不能代替真实 Wi-Fi 切换、后台休眠、IME、WebKit/Firefox 或 Tauri 原生生命周期验收；相应 TODO 继续保留。
- 此报告不证明真实 backend/provider 的 exactly-once、PostgreSQL 恢复或模型质量；现有 primary-output-only/uncertain 边界不变。
