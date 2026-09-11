# Study Question 可访问性独立验收（2026-09-11）

结果：**5 项生产 Chromium 浏览器验收全部通过，4.7 秒**。本智能体只修改浏览器测试和验收报告，未修改组件、Hook、模型或契约；产品修改由主智能体完成。本报告支持 `UX-A11Y-STUDY-QUESTION-001` 中当前单选/填空题的浏览器语义、键盘、忙碌状态和焦点范围收口。

## 范围核对

现有契约只支持 `multiple_choice` 与 `fill_blank`。其中 `multiple_choice` 的服务端 grading specification 只有一个 `correct_option_key`，提交答案为一个字符串，实际是**单选**，不是多选。此次使用原生 radio 与“选择题（单选）”明确表达，未引入 checkbox 或扩展模型契约。填空题提供可访问名称“你的答案”。

审计原实现发现选择按钮没有原生选中语义，填空依赖 placeholder，反馈没有状态/错误语义，解析按钮缺少展开属性。新实现用 fieldset/legend、radio、显式 label、status/alert、`aria-busy`、`aria-expanded`/`aria-controls` 与受当前焦点归属限制的反馈焦点恢复；验证没有提前把服务端评分信息带入尚未提交的 UI。

## 执行环境

- 生产构建：`lOa0l7HmPxReUDGEkx1dQ`，主智能体在产品修改后构建。
- Next production 服务 `127.0.0.1:3417`；Playwright Chromium，每项全新 browser context。
- 全部业务 API 由浏览器拦截为合成合法 Session/Question/Attempt 响应；没有真实数据库或模型写入。
- 故障注入包括 attempt HTTP 409、attempt 成功后阻塞 Session GET、离开 Study 页面后释放 GET。
- 命令：`npm exec --workspace @vibe-learner/web -- playwright test tests/browser/study-question-a11y-independent.spec.ts`。
- 项目快捷入口：`npm --workspace @vibe-learner/web run test:study:question:browser`。
- `npm run check:web` 通过。既有 `diagnostics-live.spec.ts` 两个选择按钮定位同步为 radio，仅类型检查；本轮没有运行其整套真实 backend 验收。

## 独立浏览器结果

| 场景 | 实际断言 |
| --- | --- |
| 单选键盘与触控 | 2 个 radio、0 checkbox；Space 选择，ArrowDown/ArrowUp 改变唯一 checked 项；Tab 移至提交；390×844 视口中选项 label 为 328×44，提交为 72×44，再来一题为 70×44 |
| 等待持久读回 | attempt POST 成功后阻塞 Session GET：fieldset busy=true，radio/提交禁用，未显示成功反馈或解析；释放合法 committed Session 后才显示反馈、busy=false并聚焦反馈；解析展开状态与控制目标一致 |
| 填空失败 | input 有显式可访问名称和题干说明、高44px；Enter只发送一次；409后保留答案、显示alert、焦点返回错误反馈，输入说明关联错误，允许手动重试 |
| 离页迟到 | 在Session GET阻塞时导航Settings并聚焦目标链接；释放迟到读回后不显示旧题反馈，也不抢目标焦点 |
| 同页移开焦点 | 等待保存时主动聚焦其他控件，结果到达正常显示反馈，同时保留用户新焦点 |

最终 [JSON结果与触控量测](../acceptance/study-question-a11y-independent-2026-09-11.json) 保留5项状态、时长和控件实际尺寸；可复跑测试位于 `apps/web/tests/browser/study-question-a11y-independent.spec.ts`。临时生产服务由 Playwright 自动停止。

## 结论边界

- 这里验证的是浏览器可访问树中的名称/role/状态、原生键盘行为与DOM焦点，不等于已实际听取 VoiceOver/NVDA 播报。真实辅助技术与各原生平台仍按专门验收安排。
- 390×844 是本次题目控件触控尺寸量测，不认证整页手机布局。真实IME设备、Wi-Fi切换和系统休眠不在本次范围。
- 严格的持久读回顺序在真实浏览器中通过受控API故障验证；数据库原子性与评分私密性继续依赖既有服务端契约/恢复门，本次没有重复宣称真实后端端到端验证。
- 没有多选需求实现或认证，也没有扩展 Study Question 的评分/提交流程。
