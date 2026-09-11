# Planning 修订前端独立验收（2026-09-11）

最终结果：**8 项生产 Chromium 验收全部通过，4.4 秒**。覆盖修订差异、拒绝、接受、冲突刷新、离页迟到结果、POST 丢失后的 GET-only 恢复、明确接纳拒绝、查询不存在后的显式清除，以及真实临时 SQLite 的回滚保留当前进度。支持关闭 `PLAN-REV-UX-001` 当前限定交互范围；不代表真实模型质量、全部原生平台或任意网络生命周期均通过。

## 独立性与过程

本验收智能体没有参与 Plan Revision Panel 的初始实现。先独立审计 UI/DTO 并编写对抗场景，发现问题交给主智能体修复。其后按主智能体明确分工，直接修复了 decoder 的长度限制、admission 绑定及派生投影一致性。因此 **UI 浏览器验收与 backend 投影发现属于独立复核；decoder 四项测试属于修改者自测**，不得将后者包装为第三方独立认证。

发现并修复的问题：

1. 接受/拒绝 POST 响应不明后按钮仍可再次提交。增加 outcome-unknown 栅栏；查询得到确证前禁止再次决定。
2. create response 原来仅绑定 plan/request ID，未绑定 base revision、instruction、rollback action；proposal 长度和非空任务检查与后端不一致。已补严格绑定，按 Unicode code point 计数对齐 Python。
3. 确认接纳拒绝后及 GET 404 恢复缺少可操作出口。明确拒绝释放未接纳身份；GET 404 提供用户显式清除本地记录，不自动重发。
4. **真实 HTTP 验收发现**：合法 legacy Plan 的默认进度字段在普通 Plan GET 中已派生，却在 revision `base_plan` 中保持默认零值，导致 strict decoder 拒绝 preview。后端改用共享进度投影；接受时派生标签随 schedule focus/order 更新，前端严格对照此投影。测试 seed 继续保留 legacy 默认进度，未预填以绕过缺陷。

搭建临时服务时另有测试 fixture 错误：复用的后端单元 fixture 缺少前端要求的 schedule chapters、activity 枚举不符、同 Study Unit 有重复 schedule；已仅修正种子到合法单 schedule，未修改产品 decoder。以上基础 fixture 失败不计产品缺陷。自动审批一次清理命令超时，重试成功；没有因此遗留验收阻碍。

## 最终环境与命令

- 当前工作区生产构建 `vf_-c0WZscfkYPSKNEqde`，由主智能体完成进度投影修复后的 `npm run build:web`；源码包含本次未提交的修订实现。
- Next production `127.0.0.1:3417`，Playwright Chromium，每项独立 browser context。
- 7 项故障用例拦截业务 API 为隔离 fixture。
- 1 项真实 HTTP 用例使用 `tests.plan_revision_browser_server`：`TemporaryDirectory` 下独立 SQLite/data、强制 `MockModelProvider`、禁用 OCR。未访问用户业务数据或真实模型。结束后正常关闭并自动清理临时目录。
- 浏览器命令：

```bash
PLAN_REVISION_TEST_API_URL=http://127.0.0.1:18997 npm exec --workspace @vibe-learner/web -- playwright test tests/browser/plan-revision-independent.spec.ts tests/browser/plan-revision-live.spec.ts
```

先在 `services/ai` 启动可复跑临时 backend：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python -m tests.plan_revision_browser_server
```

实时测试每次要求全新临时 backend；它会推进 seed 的 revision。缺少 `PLAN_REVISION_TEST_API_URL` 时 live 用例明确跳过，不能计作通过。

## 已执行证据

| 场景 | 断言 |
| --- | --- |
| 差异与拒绝 | 显示历史/修订标题；拒绝后 source plan 完全不变 |
| 生成 POST 丢响应 | 禁止新生成；刷新后按原 ID GET 恢复 preview；只有 1 个 POST |
| 接受 POST 丢响应 | 接受/拒绝均不可再次提交；GET 读取已提交结果后刷新版本；只有预览和首次决定 2 个 POST |
| 并发更新 | 外部推进 plan revision，刷新后旧预览接受按钮禁用，未追加决定 POST |
| 在途离页 | 生成 POST 阻塞，导航 Settings，再释放迟到响应；Settings 不渲染修订；回 Plan GET 原 ID，未重发 POST |
| 明确 admission 409 | 提示刷新重试，清理未接纳本地身份；不自动提交新请求 |
| GET 404 | 继续禁新生成，只有用户点清除按钮后恢复；清除本身没有 POST |
| 真实 HTTP 接受/回滚 | 默认进度 legacy import → v1 接受 → PATCH 完成进度成为 v2 → UI 预览/接受回滚到 v0 内容成为 v3；HTTP 对照确认 overview 恢复，而 schedule 状态、progress events、summary、Study Unit progress 和 Study Units 保留 |

[机器可读结果与真实 HTTP 各版本投影](../acceptance/planning-frontend-independent-2026-09-11.json) 保留最终 8 项状态、时长，以及 live 请求清单和 original/accepted/progressed/rolledBack 完整合成计划。原始临时 Playwright 报告在 `/tmp/vibe-learner-route-report.json`。

四项 decoder 自测使用 `node --experimental-strip-types --test apps/web/tests/plan-revision-decode.test.ts`：admission 绑定、schema 长度/任务边界、身份/target/effect tamper、focus 派生字段绑定。`check:web` 通过，新增 `.ts`/`.spec.ts` 均在 Web TypeScript 检查范围。

## 不扩大的结论

- 真实 provider 生成质量和实际断网/设备/原生生命周期仍按专门 TODO 验收；mock-provider 成功不能替代。
- live 用例证明单 schedule 的实际进度持久化与回滚，重排/多 schedule 及 Session 并发绑定证据应结合单独 backend 独立验收报告。
- 本次没有重新认证整个 Plan Workspace 的触控布局、屏幕阅读器或所有路由；这里只关闭上述明确修订交互范围。
