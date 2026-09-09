# 前端测试边界

前端重构按模块运行测试；生产构建和浏览器验收作为独立流程。后端故障注入与进程中断门继续使用原入口，不通过前端测试重复启动数据库。

| 入口 | 边界 |
| --- | --- |
| `npm run test:web:debug` | 完整 React 组件的 Debug 发布、更新、卸载清理；无学习 controller/API |
| `npm run test:web:workspace` | 快照查询、草稿生命周期与生成 Hook；注入依赖，无网络 |
| `npm --workspace @vibe-learner/web run test:workspace:data` | 只运行首次加载、刷新竞争、失效与重试模块 |
| `npm --workspace @vibe-learner/web run test:workspace:generation` | 完整生成 Hook 的取消、过期请求、卸载、视图切换、Scene 快照和文档成功流程 |
| `npm run test:web:reliability` | 领域 decoder/recovery 单元测试与组件测试 |
| `npm run check:web` | Web 类型约束 |
| `npm run build:web` | 生产 Web 构建 |
| `npm run test:acceptance:web-routes` | 构建后启动独立本机服务，以 Chromium 验证路由请求和用户导航 |

首次运行浏览器验收先执行 `npm exec --workspace @vibe-learner/web -- playwright install chromium`。测试启动 `127.0.0.1:3417` 的生产 Web，所有 API 请求均由浏览器截获并返回契约合法的合成响应，不访问运行数据库。结束后测试服务自动退出。

路由请求基线在 `apps/web/tests/browser/route-request-contract.ts`：默认教师、无 Document/Plan/Session/Room、关闭 Debug 展开。每个路由初次请求必须与其清单一致，一次 focus 后每种资源最多请求两次；只能 GET。显式 Debug 展开、已存在资源读回、用户提交和离页取消不属于这份初始清单，需单独验证。

2026-09-10 已通过 12 项生产 Chromium 测试：十个顶级路由（含 404）、Plan/Study 共用 owner 和离开后的 focus 隔离，以及目标/PDF 草稿经 Settings 返回后的可见恢复。每次运行的 JSON 报告写入 `/tmp/vibe-learner-route-report.json`，包含 API 请求记录附件；失败 trace 位于 `/tmp/vibe-learner-browser-results`。这不是完整桌面或有历史数据的恢复认证；历史 Plan/Session、在途请求和设备级 UX 仍在专项计划/TODO 中跟踪。
