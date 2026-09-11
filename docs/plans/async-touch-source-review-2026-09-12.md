# UX-A11Y-ASYNC-TOUCH-001 源码复核

日期：2026-09-12。范围：共享 `AsyncFeedback`、Persona Spectrum、Sensory Tools、Tavern Workspace 的异步提示、焦点与控件命名，以及 Scene Setup 的对应改动。

本复核者未编写共享反馈和其余三页的实现；参与了 Scene Setup 实现，因此 Scene 部分是开发者复核，独立浏览器验收由另一智能体执行。本报告不是原生读屏认证，也不以源码检查替代浏览器验收。

## 源码发现及修正复核

- 初始加载曾把 `document.body` 当作操作来源，失败可能自动聚焦。共享组件现排除 body 来源；Sensory 的 pending 仅表示保存，初载只播报。Persona 初载 `loadError` 独立使用 alert。
- 任意新错误曾依据最近点击控件聚焦，可能把 Tavern 自动恢复失败当作用户操作失败。共享组件现要求 pending 期间新出现的错误，或调用方明确指定的同步错误；Tavern 未开启同步错误自动定位。Persona 仅明确指定保存验证错误。
- pending 开始时保留真实操作控件，监听期间的 `focusin`。用户移动到其他控件后，失败不会从该控件或其后失焦的 body 抢回焦点。操作控件被禁用而失焦至 body 时，可定位到失败提示。成功只通过 status 播报。
- Persona 自定义 option 曾错误覆盖实际选项名称，权重滑块曾误标为“保留原文比例”；现保留选项实际文本，滑块名称为“插槽 N 权重”。
- 四页交互控件采用至少 44px 的有效区域。Scene 的关键词、长文本文件、重写强度，以及四个层级和两个物体文本框具有明确名称。文本框同时使用显式 id/htmlFor，避免同一 label 中的重写按钮截取隐式关联。
- Scene 删除对话框原有取消优先、焦点恢复保持；重写弹层补 Escape 返回触发按钮。Scene 复用库初载错误不参与局部错误聚焦。
- 独立浏览器发现 Scene 紧凑列布局中树 Panel 被 flex 压缩、内容覆盖后续区域。现使用 `flex: 0 0 auto` 按内容占位；普通点击与遮挡复验以独立浏览器报告为准。

## 已执行的开发验证

`npm --workspace @vibe-learner/web run test:scene`：26 项通过，包括生成 5、草稿 7、重写 5、库 6、树组件 3。

`npm --workspace @vibe-learner/web run check`：初次 Scene 改动和局部同步错误定位改动后通过。此后文本框命名、紧凑布局和共享 actionRef 接线是后续修正，最终类型与构建检查由主线统一执行，不把早先检查冒称为最终检查。

## 证据边界

源码复核未发现上述修正之外的新阻断问题。最终关闭需结合另一智能体对四页实际浏览器的成功/失败反馈、焦点保持、可访问名称、44px 尺寸和普通点击结果。没有执行 macOS VoiceOver、Windows NVDA、真实移动设备读屏或 Tauri 原生辅助技术验收；浏览器可访问树和 live-region 属性不能证明这些平台的实际朗读体验。
