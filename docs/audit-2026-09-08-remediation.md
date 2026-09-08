# 复审残留问题修复（2026-09-08）

对应 `audit-2026-09-08-review.md` 的 R01–R05，修复基线为 `63372db`。
复审报告和原始复现脚本保留；本文记录后续实现及验证。

## 修复

- **R01 / Tavern**：在数据库事务内先取得 Room 写入权，再检查历史引用。已有
  Message 或 Run Step 引用的 Participant 不允许删除或改变 display order，返回
  原有结构化 `tavern_participant_history_conflict` 409。拒绝时事务回滚，Room revision
  和历史提交投影保持有效；无历史房间仍能重排，有历史房间仍能修改标题。
- **R02 / Settings**：离页时若旧快照正在保存，记录 flush 请求；当前请求结束后继续
  提交最新待保存快照，不依赖已卸载页面重新运行 effect。旧请求失败也会处理更新的
  快照，但不无限重试失败请求。撤回未发送修改会清除 pending；保存期间撤回仍会排队
  恢复原值。
- **R03 / Settings**：页面生命周期和 debounce effect 不再依赖 Effect Event 的函数
  身份；普通重新渲染不会执行离页 flush 或重置保存计时。
- **R04 / Persona**：新增原模型响应 DTO `PersonaCardBatchContentProposalV1`，在
  文本、关键词和 web-search 返回路径统一严格校验整个 batch。摘要、关系、称呼
  拒绝错误类型、缺字段和伪造元数据；合法字符串通过后才去除首尾空白。
- **R05 / Document**：移除将 parser 总耗时复制给四个子阶段的代码。未单独测量的
  `duration_ms` / `attempt_count` 使用 `null` 表示未知；Study Unit 清理记录实际调用
  次数及累计耗时。保留对旧数值证据的读取兼容。

## 验证

- `npm run check:release` 完整通过：518 个后端测试；Web 163 通过、2 个 live case
  明确跳过；shared contracts、Harness PR eval、Web 类型和生产构建均通过。
- 新增定向回归覆盖：Tavern 重排拒绝后的 revision、Participant 顺序及真实 committed
  projection；Persona 三条生成路径的错误类型、缺字段、伪造字段及合法输出；文档
  未测阶段为空与清理实际计时。
- 5 个 Settings 生命周期回归执行生产函数/effect 的源码，控制计时、渲染依赖、卸载
  和异步请求完成顺序，覆盖防抖、离页排空、失败、撤回与保存中撤回。
- `git diff --check` 通过。

以上关闭本次列出的实现缺陷，不扩大成全部独立验收完成声明。Settings 测试使用受控
生命周期，不是完整 React 浏览器测试；硬关闭浏览器/进程不保证异步请求落盘。文档
各子阶段真实计时采集仍待接入，当前证据明确为未知。真实浏览器慢网、PostgreSQL
并发、桌面安装/退出和外部 provider 的验收范围继续沿用原审计中的开放项。
