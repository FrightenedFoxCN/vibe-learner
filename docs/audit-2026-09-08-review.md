# 2026-09-07 修复复审（2026-09-08）

审查提交：`63372dbaf0f786e8cd074b90f2391a8e4e754965`，父提交 `8f5ff0f`。
结论：修复有实质进展，发布门禁通过，但 A05、A09、A12 仍存在可复现遗漏，A04
阶段执行计时仍不准确，不能将 A01–A16 整体关闭。本轮仅审查，未修改产品代码。

## 发现

### R01 · P1 · A05 仍允许名册重排破坏历史提交证据

`services/ai/app/persistence/tavern_repository.py:1300` 只检查被移除的 persona ID。
在双角色 facilitated Run 完成后，将 `[A, B]` 改为 `[B, A]` 不触发保护，PATCH
返回 200。`_build_participants` 会重写 `display_order`，历史提交验证却仍使用当前
Participant 顺序重建旧 Run 的 schedule。

独立临时 SQLite/API 复现：生成返回 200；重排前 committed projection 校验成功；
重排返回 200；再次使用 `get_actor_commit_read_back` 的数据构建投影，得到
`ValueError: tavern_commit_schedule_display_order_mismatch`。

应保留历史调度所需的不可变名册证据，或在更新事务中拒绝会破坏历史 schedule 的
顺序变化；不能仅对角色删除做保护。该发现证明历史证据失效，不声称本轮已复现
后续正常聊天失败。

### R02 · P2 · A12 保存进行中离页仍丢失最新修改

`apps/web/components/settings/use-settings-controller.ts:260` 在 `savingRef.current`
为真时直接跳过 flush。保存 A 尚未返回时编辑为 B 并离开 Settings，卸载清理只会
返回。A 完成后没有继续消费 pending B；已卸载组件也不会再次运行 debounce effect。

抽取当前源码中的 `persistSnapshot` 和 `flushPendingSave`，注入可控制完成时间的
保存函数：调用记录仅为 `[A]`，A 完成后 B 仍留在 pending ref。此为函数级时序
复现，不是完整浏览器验收。应让待保存队列在当前请求结束后继续排空，并使其生命周期
覆盖页面卸载。

### R03 · P2 · A12 新增 effect 依赖导致非卸载时也执行 flush

`apps/web/components/settings/use-settings-controller.ts:276` 把 `useEffectEvent`
返回的 `flushPendingSave` 放入依赖数组。仓库安装的 React DOM `updateEvent`
每次渲染返回一个新包装函数，因此每次重新渲染都会清理并重新注册这个 effect。
设置编辑安排 pending 快照并触发状态渲染后，清理可能立即提交快照，绕过 900ms
debounce；它并非仅在注释声称的路由卸载时执行。

依据是当前锁定运行依赖和 effect 控制流，未冒充浏览器请求数量实测。应将页面生命周期
effect 与 Effect Event 的函数身份分开，且补验连续输入时的保存次数。

### R04 · P2 · A09 顶层 Persona 输出仍在严格校验前被强制转换

`services/ai/app/api/routes.py:1207` 校验的结果已在
`services/ai/app/services/model_provider.py:1967` 和 `:2011` 经 `str(...)` 转换。
本次收紧了卡片和插槽，但没有收紧摘要、关系和称呼。

独立注入合法卡片及 `summary={"bad": true}`、`relationship=["bad"]`、
`learner_address=77`，调用真实 provider 方法并经真实 Persona Harness runtime 后，
得到 `trace.status=passed`，三个字段分别变成 `"{'bad': True}"`、`"['bad']"`、
`"77"`。应在原模型返回处严格验证整个响应，再做允许的文本清理。

### R05 · P2 · A04 四个子阶段计时仍使用同一个完整 parser 耗时

`services/ai/app/services/documents.py:182` 将整个 `parser.parse()` 耗时同时写入
page extraction、section detection、chunk building 和 OCR 的 `duration_ms`。
这些阶段的观察值被标为 `observed_runtime`，但无法代表各自真实耗时；无须 OCR 时
也会得到完整 parser 时间。`attempt_count` 仍默认 1，而非来自各阶段执行记录。

失败 outcome 转成失败 trace 的修复有效，但不能据此认定原阶段的耗时、次数和执行
边界已经准确。应在真实阶段周围收集证据，或明确只保留 parser 总耗时，不把总耗时
复制为子阶段耗时。这是 A04 未完成的实现部分，与独立 live-wire 验收缺口分开。

## 本次验证

- `npm run check:release`：退出 0；后端 515 个测试通过，Web 158 通过、2 个 live
  case 跳过；shared contracts、Harness PR eval、Web production build 通过。
- `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check`：通过。
- `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml --locked --offline`：通过。
- 重跑原审计 `repro-goal-only.py`：同步和流式纯目标计划接口均返回 200。
- R01：真实临时 SQLite 与 TestClient；mock provider，无真实上游调用。
- R02：执行从当前源码抽取的函数，控制异步完成顺序。
- R04：真实 provider 方法、错误类型注入、真实 Harness runtime。

复现脚本保存在 `audit-2026-09-08-evidence/`。它们没有连接业务数据库。
R03、R05 为代码证据；不将它们写成浏览器或阶段计时的动态验收。

## 关闭判断

- A02：本轮独立重跑原故障接口已通过。
- A05、A09、A12：局部修复有效，但上述反例仍失败，不能关闭。
- A04：失败状态修复有效；阶段真实执行/计时证据仍未完成。
- A01、A03、A10、A11、A13、A16：实现和静态路径已审阅，但本轮未完成真实浏览器
  正常网速、慢网、快速切换与卸载矩阵，不新增独立 UX 验收通过声明。
- A06：显式退出清理已接入、Rust 检查通过；真实安装包进程树与退出验收仍开放。
- A07、A08、A14：相关后端回归包含在本轮通过的完整门禁中，不声称覆盖全部真实教材。
- A15：打包和发布已依赖新增 release gate；未在本轮触发 GitHub 发布 workflow。

工作树原有 `apps/desktop/src-tauri/icons/icon.icns` 修改保留，未纳入审查修复。
