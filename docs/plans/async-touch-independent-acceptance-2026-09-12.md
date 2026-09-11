# 四页触控与异步反馈独立验收（2026-09-12）

最终结果：**24项生产 Chromium 测试全部通过，12.4秒**。其中19项为本次独立验收，5项为既有 Tavern 文案回归。支持关闭 `UX-A11Y-ASYNC-TOUCH-001` 的四页浏览器触控尺寸、可访问名称、异步反馈及错误焦点范围。验收智能体仅修改浏览器测试和证据；产品修复由主线及 Scene 实现智能体负责。

## 环境与证据

- Next production build：`BWV5UeFVRL5_Bb8zvDB48`；源码 HEAD `f592c4b0c941ea5179fc250bc3f54c14c6b6226d` 加本次未提交修改。
- 390×844，Playwright Chromium；生产服务 `127.0.0.1:3417`，合成业务 API `127.0.0.1:18999`。所有写入响应均为测试夹具，无真实模型调用或业务数据库写入。
- 执行命令：`npm exec --workspace @vibe-learner/web -- playwright test tests/browser/async-touch-independent.spec.ts tests/browser/tavern-copy-independent.spec.ts`。
- [机器结果与逐控件尺寸/可访问树](../acceptance/async-touch-independent-2026-09-12.json)。主线另报告最终 `npm run build:web` 和 `npm run check` 通过。

## 控件覆盖

| 页面 | 默认/展开控件观察数 | 实际检查 |
| --- | ---: | --- |
| Persona Spectrum | 32 / 37 | 添加插槽，系统约束，长文本上传，卡片搜索，人格库已有角色，AI 重写比例弹层 |
| Scene Setup | 42 / 42 | 默认层级字段；真实点击添加物体后检查物体字段、重写强度弹层、长文本上传、展开节点库/场景库 |
| Sensory Tools | 4 / 4 | 有实际工具的阶段/分类；全开、全关、工具复选框 |
| Tavern Workspace | 13 / 13 | 有三名参与者的房间；Header、Interaction Composer、Participant Roster、房间切换 |

两状态观察会重复同一控件，不是独立功能数。所有观察到的可见按钮、输入、选择框、文本区均有可访问名称，实际宽高均至少44px。复选框以关联 label 的真实可点击范围计量。Scene 默认与物体状态均检查 textarea 名称。卡片库采用空库搜索控件，不据此声称所有生成卡片操作均验收。

## 异步反馈与焦点

四页均通过延迟请求下的 `role=status` pending、失败 `role=alert`、触发控件仍拥有交互时错误聚焦且进入视口，以及用户主动移到其他可用控件后不抢焦点。移焦用例在释放响应前实际断言焦点已转移。

成功路径验证 Persona 创建的回读记录和状态、Scene 完整合法保存 DTO 和成功状态、Sensory 已保存状态和工具开关回读。Tavern 验证 partial 响应中已提交 actor 消息经后续读取显示；它是部分成功，不是完整三角色生成成功或真实数据库持久性证明。

另验证 Sensory/Tavern 初载 GET 失败显示告警而保留用户导航焦点；Persona 先产生真实空关键词生成校验错误，再保存成功，不将焦点转到告警。该错误可能因草稿 scope 改变而清理，此例不证明旧错误持续留在 DOM 时的行为。

## 独立发现与复验

初次量测发现大量28–38px控件和未命名输入。实现后，独立延迟失败测试进一步发现 Persona/Sensory 控件禁用后焦点落到 BODY、恢复 enabled 后错误定位失效；Persona 成功消息未进入主 status。主线修复后四页 success/failure/主动移焦均通过。

扩大深层检查发现 Scene 层级/物体 textarea 的隐式 label 被重写按钮干扰，Persona 系统约束、长文本文件及两类搜索缺少名称；均已修复。Scene 44px按钮还存在真实遮挡：移动列布局被 sidebar 压缩，添加物体点击落到场景名称输入。没有使用 force click 绕过，修复内容高度后正常 pointer click 通过。

中间失败也包含夹具问题：Tavern pending 文案匹配遗漏、错误匹配遗漏、试图聚焦 busy 时禁用的输入，以及错误地要求被 scope 清理的旧错误持续存在。分别按实际业务语义修正；最终24项在同一冻结产品 build 上完整通过。

## 截图与边界

验收智能体实际查看了 [Persona](../acceptance/async-touch-persona-spectrum-2026-09-12.png)、[Scene](../acceptance/async-touch-scene-setup-2026-09-12.png)、[Sensory](../acceptance/async-touch-sensory-tools-2026-09-12.png)、[Tavern](../acceptance/async-touch-tavern-2026-09-12.png) 截图。Persona/Scene 截图是内部滚动区当前视图，未将一张截图当作整页全部内容可见证明。

这是浏览器 DOM、几何、实际 pointer 交互和焦点验收，不是 VoiceOver/NVDA 听觉播报、真实移动触屏或 Tauri 原生平台认证。未覆盖所有工具目录、所有卡片内容、全部错误组合和真实 provider/数据库链路。Playwright 生产测试服务已自动停止。
