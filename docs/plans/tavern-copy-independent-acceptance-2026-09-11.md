# Tavern 文案独立验收（2026-09-11）

结果：**5 项生产 Chromium 独立验收全部通过，4.2 秒**；`npm run check:web` 通过。支持关闭 `TAV-UX-COPY-001` 中本次 partial/failed/blocked 与错误代码分层的限定文案范围。本智能体只修改浏览器测试和验收报告，未修改产品组件或文案 contract。

## 环境

- 生产构建 `kdGcFhfhMHkFwdndKUgdC`，使用主智能体构建后的真实 Next 页面；临时服务 `127.0.0.1:3417`。
- Playwright Chromium；每项新 browser context。业务 API 全部由浏览器 route fixture 截获，不接触用户数据库或真实 provider。
- fixture 有3个角色，partial时分别 completed/failed/blocked；failed时首个角色 failed、后续角色 blocked。真实点击 Interaction Composer 发送按钮，接收严格解码的 terminal response，随后读取 runs/recovery。
- 命令：`npm exec --workspace @vibe-learner/web -- playwright test tests/browser/tavern-copy-independent.spec.ts`。

## 实际覆盖

| 场景 | 独立断言 |
| --- | --- |
| partial | 主提示明确部分角色回应未完成、已保存回应不重复生成、只恢复未完成角色；对话保留已完成角色回复 |
| failed | 主提示为本轮角色回应未完成并提供恢复方向，不使用裸错误码；没有虚构已完成角色回复 |
| blocked（两种run内分别验证） | Participant Roster 显示“上一轮尚未执行”，不显示“角色失败/回应失败”；展开 Reliability Details 显示“因前序回应未完成而暂未执行” |
| raw分层 | 注入run和step原始error_code，Reliability Details默认折叠；主页面可见正文无原始code，Roster/Composer/Notice无tavern错误标识；恢复按钮启用 |
| 归档 | 主提示只读，Interaction Composer禁用，placeholder明确归档只读 |
| retry上下文改变 | 仅一次retry POST，显示“房间内容或角色设定已变化，不能继续旧恢复任务。”；已提交回复保留，不泄露`tavern_retry_context_changed` |
| 未知retry错误码 | 注入`UNKNOWN_INDEPENDENT_PRIVATE_CODE`，显示通用可读恢复说明，未在主页面露出原始码，也不出现“当前叶节点”等内部实现词 |

[机器可读结果与可见文案快照](../acceptance/tavern-copy-independent-2026-09-11.json) 保存最终5项结果、时长及partial/failed/重试错误的可见正文。测试在 `apps/web/tests/browser/tavern-copy-independent.spec.ts`。所有5项首跑通过；临时Next服务由Playwright自动停止。

## 结论边界

- blocked是 **Speaker Step状态**，不是独立Run状态。本次分别在partial与failed运行下检查blocked，未构造非法“blocked Run”。
- 原始代码可保留在调试投影；测试证明它不进入默认可见主UI，没有要求在可读Reliability Details中强制展示raw码，也未认证Debug全部展现行为。
- cancel与stale文案虽属于统一contract的静态覆盖范围，本轮独立浏览器未运行取消真实provider请求、超时或续轮anchor变更场景，不能将5项文案验收扩大为这些生命周期的运行时证明。
- 这不是完整Tavern可访问性、原生平台或真实provider质量/性能验收。其余相关TODO继续独立管理。
