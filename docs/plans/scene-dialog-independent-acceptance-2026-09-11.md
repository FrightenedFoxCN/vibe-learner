# Scene 删除 Dialog 独立验收（2026-09-11）

结论：`UX-A11Y-SCENE-DIALOG-001` 的条目要求在本机生产 Chromium 范围内通过独立复核，可以关闭该条目。本次由独立子智能体读取要求后补充测试并执行，没有修改产品代码。

## 范围与隔离

主智能体对当前工作树重新执行 `npm run build:web` 通过后，使用该 Next.js 生产构建复跑（`apps/web/.next/BUILD_ID` 时间 2026-09-11 15:34:06），独立 `127.0.0.1:3428` 服务，Node 26.8.1、Playwright 1.63.0；检视 HEAD 为 `5117bc3c64425e1777cb6ce795700f4db91a5e2f`，构建 ID 为 `R4NvcnDWh8WLl9x6TOx9t`。新构建包含本次工作树及 TypeScript 构建检查。每个测试使用全新 Playwright 浏览器上下文；所有业务 API 由 `observeRequests` 拦截至测试 fixture 地址 `127.0.0.1:18999`，编辑的是默认临时草稿，未访问或变更用户业务数据库。新增取消/确认测试还断言没有非诊断业务写请求。

## 执行与证据

在 `apps/web` 目录启动服务，另一个终端运行：

```bash
npm run start -- --hostname 127.0.0.1 --port 3428
npx playwright test --config playwright.scene-independent.config.ts
```

最终结果：**5 passed (1.4s)**（新构建复跑；此前已有构建为 5 passed / 2.0s）。JSON 结果位于 `/tmp/vibe-scene-independent-report.json`。原有测试为 `tests/browser/scene-dialog.spec.ts` 的 2 项，独立新增 `tests/browser/scene-dialog-independent.spec.ts` 的 3 项。

| 要求或独立边界 | 实际观察 | 结果 |
| --- | --- | --- |
| 初始焦点 | 鼠标与 Enter 开启后，焦点位于取消按钮 | 通过 |
| 双向键盘循环 | 原有首尾循环；新增每次开启连续 4 次 Tab、4 次 Shift+Tab，重复开启 3 次，焦点始终属于 Dialog | 通过 |
| Escape / 取消 | Escape 和聚焦取消后 Enter 都关闭；原有鼠标取消也关闭 | 通过 |
| 取消后焦点及内容 | 每次返回原启用删除按钮，层级删除按钮数量未变，无业务写入 | 通过 |
| 背景 inert | 原生 `:modal` 生效；对背景导航程序 focus 无法转移焦点；鼠标点击背景导航坐标不触发其 click、不发生路由跳转 | 通过 |
| 确认及恢复 | Shift+Tab 聚焦确认后 Enter，移除子树，删除入口数量减少，焦点落在存活的 Scene 标题；原有鼠标确认亦通过 | 通过 |
| 解除模态 | Escape / 确认后背景导航可以重新获得焦点 | 通过 |
| 窄视口和语义 | 390×844 下 Dialog 在视口内；可访问名称及删除范围描述存在；两按钮均至少 44×44px | 通过 |

## 失败记录与限制

首次受限环境不能监听端口或启动 Chromium（EPERM / Mach bootstrap permission），经工具审批后运行成功，不属于产品失败。新增测试首轮误把禁用的世界根节点删除控件当作可执行入口，造成 2 项断言失败；检查实际 DOM 后改为选择启用控件，并在确认前等待初始焦点。修正测试后全部通过，产品代码没有变化。

这份证据限于本机 Chromium、生产构建、fixture API 的 Scene 本地草稿操作，不声明 Safari/Firefox、Tauri WebView、真实 VoiceOver 播报或后端删除持久化已验收。该 TODO 要求的 Dialog 键盘及模态行为均有直接浏览器证据；上述平台及持久化不属于此次关闭声明。
